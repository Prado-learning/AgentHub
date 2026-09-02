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

    serialised = json.dumps(list(parts), sort_keys=True, ensure_ascii=False, default=str)
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
    def get(self, key: str) -> dict[str, Any] | None:
        ...

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        ...

    def clear(self) -> None:
        ...


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
        self._max = max_entries
        self._store: "OrderedDict[str, _Entry]" = OrderedDict()

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.time():
            self._store.pop(key, None)
            return None
        # Refresh recency on read
        self._store.move_to_end(key)
        return dict(entry.value)

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        self._store[key] = _Entry(value=dict(value), expires_at=time.time() + ttl_seconds)
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()


class SingleFlight:
    """Coalesce concurrent ``compute`` calls for the same key.

    Without singleflight, a cache miss followed by N parallel calls to
    the same key would each fire the expensive ``compute`` callback —
    wasting the work for all but the first. This wrapper makes sure
    that within a process only one ``compute`` runs per key at a time;
    concurrent callers wait for the leader's result and reuse it.

    The implementation:

    * Holds an ``RLock`` so ``get_or_compute`` is safe to call
      re-entrantly from inside a ``compute`` callback.
    * Tracks in-flight futures in a dict keyed by cache key.
    * Cleans up the dict entry once the leader completes (success or
      failure) so a subsequent call starts fresh.
    * Does NOT touch the underlying cache — cache write/read policy is
      the caller's responsibility. This keeps SingleFlight composable
      with any ``CacheBackend`` and any caching decision (e.g. don't
      cache failures).
    """

    def __init__(self, cache: CacheBackend | None = None) -> None:
        self._cache = cache
        self._lock = threading.RLock()
        self._inflight: dict[str, "threading.Event"] = {}
        self._inflight_values: dict[str, dict[str, Any] | None] = {}
        self._inflight_errors: dict[str, BaseException | None] = {}

    def _wait_for(self, key: str) -> dict[str, Any]:
        event = self._inflight.get(key)
        if event is None:
            raise RuntimeError("singleflight: missing in-flight entry")
        event.wait()
        err = self._inflight_errors.get(key)
        if err is not None:
            raise err
        value = self._inflight_values.get(key)
        if value is None:
            # Leader stored nothing — treat as cache miss.
            raise KeyError(key)
        return value

    def _publish(self, key: str, value: dict[str, Any] | None, error: BaseException | None) -> None:
        with self._lock:
            self._inflight_values[key] = value
            self._inflight_errors[key] = error
            event = self._inflight.pop(key, None)
        if event is not None:
            event.set()

    def get_or_compute(
        self,
        key: str,
        compute: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a cached value or run ``compute`` exactly once per key.

        When a cached value is available in ``self._cache`` it is
        returned without ever invoking ``compute``. Otherwise the first
        caller becomes the leader, runs ``compute``, and the value is
        broadcast to any waiters via a ``threading.Event``.
        """

        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        with self._lock:
            if key in self._inflight:
                is_leader = False
            else:
                self._inflight[key] = threading.Event()
                is_leader = True

        if not is_leader:
            return self._wait_for(key)

        # Leader path — run the compute and broadcast to followers.
        try:
            value = compute()
        except BaseException as exc:
            self._publish(key, None, exc)
            raise

        self._publish(key, value, None)
        return value
