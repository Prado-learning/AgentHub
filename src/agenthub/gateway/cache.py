"""Cache backends for the unified gateway.

The article's pattern caches LLM-style calls by ``TaskID`` with a long
TTL (their example: 100h) so repeat requests become idempotent. We
generalise that to a content-hash key so any adapter call — not just
the ones keyed on a TaskID — benefits from caching.

The default cache is :class:`NoopCache` (zero storage, zero hits). Swap
in :class:`InMemoryCache` for tests or development; production
deployments should inject a Redis-backed implementation built on the
same protocol.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from concurrent.futures import Future
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Protocol


# Fields whose value should not contribute to cache-key identity.
# These are typically per-request metadata (timestamps, request ids,
# trace ids) that change every call but do not change the underlying
# semantic of the request — without this allowlist the cache would
# never hit for anything that captures timing data.
_NOISY_KEYS: frozenset[str] = frozenset(
    {
        "timestamp",
        "ts",
        "request_id",
        "trace_id",
        "run_id",
        "started_at",
        "updated_at",
        "created_at",
        "nonce",
        "request_ts",
        "received_at",
    }
)


def _strip_noisy(value: Any) -> Any:
    """Recursively strip noise keys while preserving list order.

    Dict keys are kept in their original insertion order so a request
    with fields ``[a, b]`` does not collide with ``[b, a]`` — that
    distinction is semantic, not noise. Only the explicit allowlist
    above is removed.
    """

    if isinstance(value, dict):
        return {
            str(key): _strip_noisy(item)
            for key, item in value.items()
            if str(key) not in _NOISY_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_strip_noisy(item) for item in value]
    return value


def cache_key(parts: list[Any]) -> str:
    """Build a stable cache key from arbitrary stringifiable parts.

    JSON-serialise the parts in order, then SHA256-hex the result. The
    sha is overkill for non-secret content but keeps keys uniform length
    regardless of how long the inputs are.
    """

    serialised = json.dumps(
        list(parts), sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def semantic_key(namespace: str, parts: list[Any], *, length: int = 32) -> str:
    """Build a cache key that ignores noise fields and includes a namespace.

    Unlike :func:`cache_key`, this:

    * Prefixes the hash with ``namespace`` so two adapters cannot
      collide on identical inputs.
    * Recursively drops fields named ``timestamp``, ``request_id`` and
      friends (see :data:`_NOISY_KEYS`) — those are per-call metadata
      that should not bust a semantic cache.
    * Preserves the order of the top-level ``parts`` list and the order
      of dict keys inside each part — a request ``[a, b]`` is still
      distinct from ``[b, a]`` even after noise removal.

    The default ``length`` is 32 hex chars (128 bits) — more than
    enough to avoid accidental collisions in a typical deployment while
    keeping keys short enough to log.
    """

    if not namespace or not namespace.strip():
        raise ValueError("namespace must be a non-empty string")
    if length < 8 or length > 64:
        raise ValueError("length must be between 8 and 64 hex chars")
    cleaned = [_strip_noisy(part) for part in parts]
    serialised = json.dumps(
        [namespace, *cleaned],
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest[:length]}"


class CacheBackend(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...

    def clear(self) -> None: ...


class NoopCache:
    """Always-miss cache used by default. Zero storage, zero overhead."""

    def get(self, key: str) -> dict[str, Any] | None:
        return None

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        return None

    def clear(self) -> None:
        return None


@dataclass
class _Entry:
    value: dict[str, Any]
    expires_at: float


class InMemoryCache:
    """LRU + TTL cache for tests and local development.

    Not thread-safe across processes — production deployments must use
    an external cache (Redis, Memcached) wired into the same protocol.
    """

    def __init__(self, max_entries: int = 1024) -> None:
        self._lock = threading.RLock()
        self._max = max_entries
        self._store: "OrderedDict[str, _Entry]" = OrderedDict()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.time():
                self._store.pop(key, None)
                return None
            # Refresh recency on read
            self._store.move_to_end(key)
            return deepcopy(entry.value)

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        with self._lock:
            if ttl_seconds <= 0:
                return
            self._store[key] = _Entry(
                value=deepcopy(value), expires_at=time.time() + ttl_seconds
            )
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class SingleFlight:
    """Followers retain a Future; removing a key cannot race an existing waiter."""

    def __init__(self, cache=None):
        self._cache = cache
        self._lock = threading.RLock()
        self._inflight: dict[str, Future] = {}

    def get_or_compute(self, key, compute):
        with self._lock:
            if self._cache is not None:
                value = self._cache.get(key)
                if value is not None:
                    return deepcopy(value)
            future = self._inflight.get(key)
            leader = future is None
            if leader:
                future = Future()
                self._inflight[key] = future
        if not leader:
            return deepcopy(future.result())
        try:
            value = compute()
            future.set_result(deepcopy(value))
            return value
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)
