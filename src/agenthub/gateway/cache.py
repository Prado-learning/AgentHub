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
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Protocol


def cache_key(parts: list[Any]) -> str:
    """Build a stable cache key from arbitrary stringifiable parts.

    JSON-serialise the parts in order, then SHA256-hex the result. The
    sha is overkill for non-secret content but keeps keys uniform length
    regardless of how long the inputs are.
    """

    serialised = json.dumps(list(parts), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


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
