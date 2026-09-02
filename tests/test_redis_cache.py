"""Tests for the Redis-backed cache and gateway wiring.

We use ``fakeredis`` so the suite runs without a live Redis instance.
The aim is to confirm the gateway behaves identically whether the
cache backend is in-process or Redis — the CacheBackend Protocol is the
contract; the storage layer is interchangeable.
"""

from __future__ import annotations

import importlib

import fakeredis
import pytest

from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.domain.run import RunContext
from agenthub.gateway import (
    GatewayDispatch,
    InMemoryCache,
    NoopCache,
    build_default_gateway,
)
from agenthub.gateway.gateway import CachingGateway, NoopGateway


class _CountingAdapter:
    """Counts invocations so we can prove cache hits short-circuit the adapter."""

    id = "counter"
    name = "Counter"
    capabilities: list[str] = []

    def __init__(self) -> None:
        self.calls = 0

    def run(self, task: AgentTask, _context: RunContext) -> AgentResult:
        self.calls += 1
        return AgentResult(
            agent_id=self.id,
            status="success",
            messages=[{"role": "agent", "sender": self.id, "content": task.instruction}],
        )


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    """Patch the ``redis.Redis.from_url`` factory so it returns fakeredis."""

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *_a, **_kw: fake)
    return fake


def test_redis_cache_roundtrip(fake_redis) -> None:
    cache_module = importlib.import_module("agenthub.gateway.redis_cache")
    cache = cache_module.RedisCache("redis://localhost:6379/0", key_prefix="test:")

    assert cache.get("missing") is None
    cache.set("k", {"answer": 42}, ttl_seconds=60)
    assert cache.get("k") == {"answer": 42}


def test_redis_cache_clear_only_drops_namespaced_keys(fake_redis) -> None:
    cache_module = importlib.import_module("agenthub.gateway.redis_cache")
    cache = cache_module.RedisCache("redis://localhost:6379/0", key_prefix="test:")

    cache.set("a", {"x": 1}, ttl_seconds=60)
    # Drop something unrelated into the same fake instance.
    fake_redis.set("other:key", "leave me alone")

    cache.clear()
    assert cache.get("a") is None
    assert fake_redis.get("other:key") == "leave me alone"


def test_redis_cache_set_with_zero_ttl_is_noop(fake_redis) -> None:
    cache_module = importlib.import_module("agenthub.gateway.redis_cache")
    cache = cache_module.RedisCache("redis://localhost:6379/0", key_prefix="test:")

    cache.set("k", {"v": 1}, ttl_seconds=0)
    assert cache.get("k") is None


def test_redis_cache_raises_when_package_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the ``redis`` package is not installed, ``RedisCache`` should
    raise :class:`RedisCacheError` instead of an opaque ImportError."""

    cache_module = importlib.import_module("agenthub.gateway.redis_cache")

    # ``import redis`` is invoked inside ``__init__`` so we poison the
    # import system for that name rather than mutating the module.
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("simulated missing package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(cache_module.RedisCacheError):
        cache_module.RedisCache("redis://localhost:6379/0")


def test_redis_cache_raises_on_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis,
) -> None:
    """If ``ping`` fails, ``RedisCache`` should surface that as a typed error."""

    cache_module = importlib.import_module("agenthub.gateway.redis_cache")

    # Substitute a fake ``redis.Redis.from_url`` whose returned client
    # raises on ping — the cache should rewrap as RedisCacheError.
    def _explode(*_a, **_kw):
        class _Boom:
            def ping(self):
                raise ConnectionError("nope")

        return _Boom()

    monkeypatch.setattr("redis.Redis.from_url", _explode)

    with pytest.raises(cache_module.RedisCacheError):
        cache_module.RedisCache("redis://localhost:6379/0")


def test_caching_gateway_with_redis_dedupes(fake_redis) -> None:
    """The CachingGateway with a Redis cache should short-circuit repeats."""

    cache_module = importlib.import_module("agenthub.gateway.redis_cache")
    cache = cache_module.RedisCache("redis://localhost:6379/0", key_prefix="gw:")
    gateway = CachingGateway(cache=cache)

    adapter = _CountingAdapter()
    dispatch = GatewayDispatch(
        endpoint="adapter:counter",
        task=AgentTask(agent_id="counter", instruction="hi"),
        context=RunContext(
            conversation_id="c1", message="x", history=[], selected_agents=["counter"]
        ),
        cache_ttl_seconds=60,
    )

    gateway.dispatch(adapter, dispatch)
    gateway.dispatch(adapter, dispatch)
    gateway.dispatch(adapter, dispatch)

    assert adapter.calls == 1


def test_build_default_gateway_picks_redis_when_url_set(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis,
) -> None:
    """When ``REDIS_URL`` is configured, ``build_default_gateway`` must
    return a real :class:`CachingGateway` over Redis."""

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    gateway = build_default_gateway()
    assert isinstance(gateway, CachingGateway)
    # The wired backend should hit the fake Redis instance.
    assert gateway.cached().get("anything") is None
    gateway.cached().set("k", {"v": 1}, ttl_seconds=60)
    assert gateway.cached().get("k") == {"v": 1}


def test_build_default_gateway_explicit_cache_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit cache injection beats REDIS_URL — useful in tests."""

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    in_memory = InMemoryCache()
    gateway = build_default_gateway(cache=in_memory)
    assert isinstance(gateway, CachingGateway)
    assert gateway.cached() is in_memory


def test_build_default_gateway_disabled_returns_noop(monkeypatch) -> None:
    """``enabled=False`` is the kill switch — no Redis, no caching."""

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    gateway = build_default_gateway(enabled=False)
    assert isinstance(gateway, NoopGateway)
    # The NoopGateway we ship uses NoopCache when nothing is injected.
    assert isinstance(gateway.cached(), NoopCache)


def test_build_default_gateway_without_redis_falls_back_to_noop_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no cache configured at all, the wiring stays inert."""

    monkeypatch.delenv("REDIS_URL", raising=False)
    gateway = build_default_gateway()
    # NoopGateway wrapping a NoopCache — never hits, never stores.
    assert isinstance(gateway, NoopGateway)
    assert isinstance(gateway.cached(), NoopCache)
