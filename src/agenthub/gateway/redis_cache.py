"""Redis-backed :class:`CacheBackend` implementation.

The ``redis`` package is imported lazily so the harness stays usable
in environments that have not installed it. Connection failures are
surfaced as :class:`RedisCacheError` — callers (typically
:func:`build_default_gateway`) decide whether to fall back to
:class:`NoopCache` or to refuse to start.

Keys live in a dedicated namespace (``agenthub:gateway:<sha>``) so
they never collide with the rest of the application's Redis usage.
Values are JSON-encoded, matching :func:`agenthub.gateway.cache.cache_key`'s
hashing strategy.
"""

from __future__ import annotations

import json
from typing import Any

from agenthub.gateway.cache import CacheBackend


class RedisCacheError(RuntimeError):
    """Raised when the Redis backend cannot be reached or configured."""


class RedisCache:
    """Production-grade :class:`CacheBackend` backed by Redis.

    The constructor performs a single ``PING`` so misconfiguration
    surfaces immediately. ``key_prefix`` lets two AgentHub
    deployments share one Redis without colliding; the default names
    the values by the AgentHub gateway so they sit next to each other
    in ``redis-cli --scan``.
    """

    KEY_PREFIX = "agenthub:gateway:"

    def __init__(self, url: str, *, key_prefix: str | None = None) -> None:
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RedisCacheError(
                "The 'redis' package is not installed; run `pip install redis`."
            ) from exc

        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._key_prefix = key_prefix if key_prefix is not None else self.KEY_PREFIX
        try:
            self._redis.ping()
        except Exception as exc:  # pragma: no cover - network dependent
            raise RedisCacheError(f"Cannot reach Redis at {url!r}: {exc}") from exc

    def _full_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    def get(self, key: str) -> dict[str, Any] | None:
        raw = self._redis.get(self._full_key(key))
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        payload = json.dumps(value, ensure_ascii=False, default=str)
        self._redis.set(self._full_key(key), payload, ex=ttl_seconds)

    def clear(self) -> None:
        """Drop every AgentHub gateway key. Useful for tests and admin tools."""

        cursor = 0
        while True:
            cursor, keys = self._redis.scan(cursor=cursor, match=f"{self._key_prefix}*", count=200)
            if keys:
                self._redis.delete(*keys)
            if cursor == 0:
                break
