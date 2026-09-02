"""Unified outbound gateway for adapter calls.

Mirrors the article's ``CallLxAtomAPIs`` design:

- All adapter calls flow through a single :class:`Gateway` instance.
- Responses are cached by an injected :class:`CacheBackend` keyed on
  task + endpoint + content hash, so repeat calls become idempotent.
- Outbound requests are signed by an injected :class:`Signer` (the
  article's MD5(appid+secret+ts) recipe is provided as
  :class:`MD5AppSecretSigner`).

The default wiring is fully inert: :class:`NoopGateway` delegates
straight to the adapter, so production callers pay nothing until they
inject a real cache or signer.
"""

from agenthub.gateway.cache import (
    CacheBackend,
    InMemoryCache,
    NoopCache,
    cache_key,
)
from agenthub.gateway.gateway import (
    Gateway,
    GatewayDispatch,
    NoopGateway,
    build_default_gateway,
)
from agenthub.gateway.signing import (
    MD5AppSecretSigner,
    NoopSigner,
    Signer,
)

__all__ = [
    "CacheBackend",
    "Gateway",
    "GatewayDispatch",
    "InMemoryCache",
    "MD5AppSecretSigner",
    "NoopCache",
    "NoopGateway",
    "NoopSigner",
    "Signer",
    "build_default_gateway",
    "cache_key",
]


def __getattr__(name: str):  # pragma: no cover - lazy import helper
    # Lazy import for the optional Redis backend so projects without
    # the ``redis`` package still load this module.
    if name == "RedisCache":
        from agenthub.gateway.redis_cache import RedisCache

        return RedisCache
    if name == "RedisCacheError":
        from agenthub.gateway.redis_cache import RedisCacheError

        return RedisCacheError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

