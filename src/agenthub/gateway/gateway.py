"""Cache only explicitly cacheable read operations using complete input identity."""

from __future__ import annotations
import hashlib
import os
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol
from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.domain.run import RunContext
from agenthub.gateway.cache import CacheBackend, NoopCache, SingleFlight, cache_key
from agenthub.gateway.signing import Signer, NoopSigner


@dataclass(frozen=True)
class GatewayDispatch:
    endpoint: str
    task: AgentTask
    context: RunContext
    cache_ttl_seconds: int = 0
    extra_key_parts: tuple[Any, ...] = ()


class Gateway(Protocol):
    def dispatch(self, adapter, dispatch: GatewayDispatch) -> AgentResult: ...
    def cached(self) -> CacheBackend: ...
    def signer(self) -> Signer: ...


class NoopGateway:
    def __init__(self, cache=None, signer=None):
        self._cache = NoopCache()
        self._signer = signer or NoopSigner()

    def dispatch(self, adapter, dispatch):
        return adapter.run(dispatch.task, dispatch.context)

    def cached(self):
        return self._cache

    def signer(self):
        return self._signer


def _dispatch_key(adapter, dispatch):
    provider = getattr(adapter, "provider", None)
    identity = {
        "class": f"{type(adapter).__module__}.{type(adapter).__qualname__}",
        "skills": getattr(adapter, "skills", []),
        "capabilities": getattr(adapter, "capabilities", []),
        "name": getattr(adapter, "name", None),
        "model": getattr(provider, "model", None),
        "base_url": getattr(provider, "base_url", None),
        "credential_identity": hashlib.sha256(
            str(getattr(provider, "api_key", "")).encode()
        ).hexdigest(),
    }
    return cache_key(
        [
            dispatch.endpoint,
            asdict(dispatch.task),
            asdict(dispatch.context),
            identity,
            list(dispatch.extra_key_parts),
        ]
    )


def _agent_result_to_cache(result):
    return asdict(result)


def _agent_result_from_cache(payload):
    return AgentResult(**payload)


class CachingGateway:
    def __init__(
        self, *, cache, signer=None, default_ttl_seconds=300, singleflight=True
    ):
        self._cache = cache
        self._signer = signer or NoopSigner()
        self._default_ttl_seconds = default_ttl_seconds
        self._singleflight = SingleFlight(cache) if singleflight else None

    def cached(self):
        return self._cache

    def signer(self):
        return self._signer

    def dispatch(self, adapter, dispatch):
        ttl = dispatch.cache_ttl_seconds
        if ttl <= 0 or getattr(adapter, "side_effecting", False):
            return adapter.run(dispatch.task, dispatch.context)
        key = _dispatch_key(adapter, dispatch)
        computed = False

        def compute():
            nonlocal computed
            computed = True
            result = adapter.run(dispatch.task, dispatch.context)
            payload = asdict(result)
            if result.status == "success":
                self._cache.set(key, payload, ttl)
            return payload

        try:
            if self._singleflight:
                payload = self._singleflight.get_or_compute(key, compute)
            else:
                payload = self._cache.get(key)
                if payload is None:
                    payload = compute()
        except Exception:
            # Cache outages must not hide an adapter error or repeat side effects.
            # Redis errors are handled in its backend, computation errors propagate.
            raise
        result = _agent_result_from_cache(payload)
        return replace(result, metrics={**result.metrics, "cache_hit": not computed})


def build_default_gateway(
    *, cache=None, signer=None, redis_url=None, cache_ttl_seconds=300, enabled=None
):
    if enabled is None:
        enabled = os.environ.get("GATEWAY_ENABLED", "true").lower() not in {
            "false",
            "0",
            "off",
        }
    if not enabled:
        return NoopGateway(signer=signer)
    if cache is None and (redis_url or os.environ.get("REDIS_URL")):
        try:
            from agenthub.gateway.redis_cache import RedisCache

            cache = RedisCache(redis_url or os.environ["REDIS_URL"])
        except Exception:
            import logging

            logging.getLogger(__name__).warning("Redis unavailable; caching disabled")
    return (
        CachingGateway(
            cache=cache, signer=signer, default_ttl_seconds=cache_ttl_seconds
        )
        if cache is not None
        else NoopGateway(signer=signer)
    )
