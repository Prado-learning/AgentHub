"""Unified outbound gateway.

Wraps an :class:`agenthub.adapters.base.AgentAdapter` so every call
goes through the same path: optional cache lookup, signature header
attachment, then delegated execution. The default
:class:`NoopGateway` is a transparent pass-through, so production
callers pay nothing until a real :class:`CacheBackend` is injected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from agenthub.adapters.base import AgentAdapter, AgentResult, AgentTask
from agenthub.domain.run import RunContext
from agenthub.gateway.cache import CacheBackend, NoopCache, cache_key
from agenthub.gateway.signing import NoopSigner, Signer


@dataclass(frozen=True)
class GatewayDispatch:
    """Bundle describing one logical outbound call.

    The fields are normalised so :meth:`Gateway.dispatch` can pick a
    cache key and a signature without re-parsing the underlying
    adapter or task. ``cache_ttl_seconds`` is per-call so the harness
    can use a longer TTL for idempotent reads and a shorter one for
    stateful lookups.
    """

    endpoint: str
    task: AgentTask
    context: RunContext
    cache_ttl_seconds: int = 0
    extra_key_parts: tuple[Any, ...] = ()


class Gateway(Protocol):
    """Outbound interface every adapter call flows through."""

    def dispatch(
        self,
        adapter: AgentAdapter,
        dispatch: GatewayDispatch,
    ) -> AgentResult:
        ...

    def cached(self) -> CacheBackend:
        ...

    def signer(self) -> Signer:
        ...


class NoopGateway:
    """Transparent gateway — no cache, no signature, just delegate.

    This is the default. It satisfies the :class:`Gateway` protocol so
    callers can wire it in unconditionally and swap in a real gateway
    later without touching the harness.
    """

    def __init__(
        self,
        cache: CacheBackend | None = None,
        signer: Signer | None = None,
    ) -> None:
        self._cache: CacheBackend = cache or NoopCache()
        self._signer: Signer = signer or NoopSigner()

    def dispatch(
        self,
        adapter: AgentAdapter,
        dispatch: GatewayDispatch,
    ) -> AgentResult:
        # Honour a positive TTL by attempting the cache lookup, but the
        # default NoopCache misses every time, so this stays a
        # pass-through.
        key = cache_key([dispatch.endpoint, dispatch.task.instruction, *dispatch.extra_key_parts])
        hit = self._cache.get(key)
        if hit is not None:
            return _agent_result_from_cache(hit)
        result = adapter.run(dispatch.task, dispatch.context)
        if dispatch.cache_ttl_seconds > 0 and result.status == "success":
            self._cache.set(key, _agent_result_to_cache(result), dispatch.cache_ttl_seconds)
        # The signature is intentionally not consumed here — callers
        # that need to attach it to a real HTTP call should pull it
        # from ``self.signer()`` before issuing the request.
        _ = self._signer
        return result

    def cached(self) -> CacheBackend:
        return self._cache

    def signer(self) -> Signer:
        return self._signer


def _agent_result_to_cache(result: AgentResult) -> dict[str, Any]:
    return {
        "agent_id": result.agent_id,
        "status": result.status,
        "messages": list(result.messages),
        "artifacts": list(result.artifacts),
        "tool_calls": list(result.tool_calls),
        "error": result.error,
    }


def _agent_result_from_cache(payload: dict[str, Any]) -> AgentResult:
    return AgentResult(
        agent_id=str(payload.get("agent_id", "")),
        status=str(payload.get("status", "success")),
        messages=list(payload.get("messages") or []),
        artifacts=list(payload.get("artifacts") or []),
        tool_calls=list(payload.get("tool_calls") or []),
        error=payload.get("error"),
    )


def build_default_gateway(
    *,
    cache: CacheBackend | None = None,
    signer: Signer | None = None,
    redis_url: str | None = None,
    cache_ttl_seconds: int = 3_600_000,
    enabled: bool | None = None,
) -> Gateway:
    """Construct the default gateway from environment + overrides.

    Resolution order:

    1. If ``enabled`` is False, return :class:`NoopGateway` regardless
       of other settings. This is the kill switch — flip
       ``GATEWAY_ENABLED=false`` to bypass caching without code changes.
    2. If ``cache`` is supplied explicitly, use it as-is.
    3. If ``redis_url`` or ``REDIS_URL`` env var is set, attempt a
       :class:`RedisCache`. On import / connection failure, fall back
       to :class:`NoopCache` and warn via stderr — production
       deployments should monitor for that warning.
    4. Otherwise stay on :class:`NoopCache`.
    """

    if enabled is False:
        return NoopGateway(cache=cache, signer=signer)

    resolved_cache = cache
    if resolved_cache is None:
        url = redis_url if redis_url is not None else os.environ.get("REDIS_URL")
        if url:
            try:
                from agenthub.gateway.redis_cache import RedisCache
                resolved_cache = RedisCache(url)
            except Exception as exc:  # pragma: no cover - import/network dependent
                import sys
                print(
                    f"[agenthub.gateway] Redis cache unavailable ({exc}); using noopCache.",
                    file=sys.stderr,
                )
                resolved_cache = None

    if resolved_cache is None:
        # Stay inert: the NoopGateway will not store or hit anything.
        return NoopGateway(cache=NoopCache(), signer=signer)

    return CachingGateway(
        cache=resolved_cache, signer=signer, default_ttl_seconds=cache_ttl_seconds
    )


class CachingGateway:
    """Gateway that actually consults and updates a :class:`CacheBackend`.

    Used as soon as :func:`build_default_gateway` resolves a real
    cache (Redis in production, ``InMemoryCache`` in tests). The
    contract is identical to :class:`NoopGateway`; the only difference
    is whether repeat calls short-circuit at the cache layer.
    """

    def __init__(
        self,
        *,
        cache: CacheBackend,
        signer: Signer | None = None,
        default_ttl_seconds: int = 3_600_000,
    ) -> None:
        self._cache = cache
        self._signer = signer or NoopSigner()
        self._default_ttl_seconds = default_ttl_seconds

    def dispatch(
        self,
        adapter: AgentAdapter,
        dispatch: GatewayDispatch,
    ) -> AgentResult:
        key = cache_key(
            [dispatch.endpoint, dispatch.task.instruction, *dispatch.extra_key_parts]
        )
        hit = self._cache.get(key)
        if hit is not None:
            return _agent_result_from_cache(hit)
        result = adapter.run(dispatch.task, dispatch.context)
        ttl = dispatch.cache_ttl_seconds or self._default_ttl_seconds
        if ttl > 0 and result.status == "success":
            self._cache.set(key, _agent_result_to_cache(result), ttl)
        _ = self._signer  # Signature is consumed by callers issuing real HTTP.
        return result

    def cached(self) -> CacheBackend:
        return self._cache

    def signer(self) -> Signer:
        return self._signer
