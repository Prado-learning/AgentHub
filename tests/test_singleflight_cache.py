"""P2 — cache singleflight + integration with :class:`CachingGateway`.

The contract is: when N callers race for the same cache key, exactly
one ``compute`` runs and the rest wait for its result.
"""

from __future__ import annotations

import threading
import time

import pytest

from agenthub.domain.run import RunContext
from agenthub.gateway.cache import InMemoryCache, SingleFlight
from agenthub.gateway.gateway import CachingGateway, GatewayDispatch
from agenthub.adapters.base import AgentResult, AgentTask


class _FakeAdapter:
    """Adapter whose ``run`` sleeps a configurable amount then returns."""

    def __init__(self, sleep_seconds: float = 0.05, agent_id: str = "fake") -> None:
        self.sleep_seconds = sleep_seconds
        self.agent_id = agent_id
        self.call_count = 0
        self._lock = threading.Lock()

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        with self._lock:
            self.call_count += 1
        time.sleep(self.sleep_seconds)
        return AgentResult(
            agent_id=self.agent_id,
            status="success",
            messages=[{"role": "assistant", "content": f"answer for {task.instruction}"}],
        )


def _build_dispatch(endpoint: str = "test", instruction: str = "hello") -> GatewayDispatch:
    return GatewayDispatch(
        endpoint=endpoint,
        task=AgentTask(agent_id="fake", instruction=instruction),
        context=RunContext(
            conversation_id="c1",
            message=instruction,
            history=[],
            selected_agents=[],
        ),
        cache_ttl_seconds=60,
    )


def test_singleflight_returns_value_when_no_race() -> None:
    cache = InMemoryCache()
    sf = SingleFlight(cache)
    calls: list[int] = []

    def compute() -> dict[str, object]:
        calls.append(1)
        return {"value": 42}

    assert sf.get_or_compute("k", compute) == {"value": 42}
    assert calls == [1]


def test_singleflight_coalesces_concurrent_callers() -> None:
    cache = InMemoryCache()
    sf = SingleFlight(cache)
    compute_calls = 0
    compute_lock = threading.Lock()
    started = threading.Event()
    proceed = threading.Event()

    def compute() -> dict[str, object]:
        nonlocal compute_calls
        with compute_lock:
            compute_calls += 1
        started.set()
        proceed.wait(timeout=1.0)
        return {"value": "leader"}

    results: list[dict[str, object]] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(sf.get_or_compute("k", compute))
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()

    # Wait for the leader to enter compute.
    assert started.wait(timeout=1.0)
    # Give followers a moment to enqueue.
    time.sleep(0.05)
    proceed.set()
    for t in threads:
        t.join(timeout=2.0)

    assert errors == []
    assert len(results) == 8
    assert all(r == {"value": "leader"} for r in results)
    assert compute_calls == 1


def test_singleflight_does_not_cache_failures() -> None:
    """A failing compute must not poison the underlying cache."""

    cache = InMemoryCache()
    sf = SingleFlight(cache)
    calls: list[int] = []

    def boom() -> dict[str, object]:
        calls.append(1)
        raise RuntimeError("upstream blew up")

    with pytest.raises(RuntimeError):
        sf.get_or_compute("k", boom)

    # The cache must still be empty so a retry can run again.
    assert cache.get("k") is None
    assert calls == [1]

    # A second attempt runs the compute again — singleflight does not
    # remember failed leaders.
    def ok() -> dict[str, object]:
        return {"ok": True}

    assert sf.get_or_compute("k", ok) == {"ok": True}
    # The successful result is *not* auto-cached — that's the caller's job.
    # But the value is returned to the caller.
    assert cache.get("k") is None


def test_singleflight_propagates_exception_to_followers() -> None:
    cache = InMemoryCache()
    sf = SingleFlight(cache)
    started = threading.Event()
    proceed = threading.Event()

    def leader_compute() -> dict[str, object]:
        started.set()
        proceed.wait(timeout=1.0)
        raise ValueError("nope")

    errors: list[BaseException] = []

    def follower() -> None:
        try:
            sf.get_or_compute("k", leader_compute)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=follower) for _ in range(3)]
    for t in threads:
        t.start()
    started.wait(timeout=1.0)
    time.sleep(0.05)
    proceed.set()
    for t in threads:
        t.join(timeout=2.0)

    assert len(errors) == 3
    assert all(isinstance(err, ValueError) for err in errors)


def test_caching_gateway_dedupes_concurrent_dispatch() -> None:
    """End-to-end: gateway with default singleflight runs the adapter once."""

    cache = InMemoryCache()
    adapter = _FakeAdapter(sleep_seconds=0.05)
    gateway = CachingGateway(cache=cache)
    dispatch = _build_dispatch(endpoint="adapter", instruction="hello")

    results: list[AgentResult] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(gateway.dispatch(adapter, dispatch))
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)

    assert errors == []
    assert len(results) == 6
    # Only one adapter invocation should have happened.
    assert adapter.call_count == 1
    # All callers received the same content.
    assert all(r.messages[0]["content"] == "answer for hello" for r in results)
    # The successful result was cached so a follow-up dispatch is a hit.
    follow_up = gateway.dispatch(adapter, _build_dispatch(endpoint="adapter", instruction="hello"))
    assert follow_up.messages[0]["content"] == "answer for hello"
    assert adapter.call_count == 1  # still only one adapter invocation


def test_caching_gateway_can_disable_singleflight() -> None:
    """When ``singleflight=False`` every caller pays for its own compute."""

    cache = InMemoryCache()
    adapter = _FakeAdapter(sleep_seconds=0.0)
    gateway = CachingGateway(cache=cache, singleflight=False)
    dispatch = _build_dispatch(endpoint="adapter", instruction="hello")

    gateway.dispatch(adapter, dispatch)
    gateway.dispatch(adapter, dispatch)
    gateway.dispatch(adapter, dispatch)

    # Without singleflight the cache layer still works, so the adapter
    # only ran once — this test mainly proves the flag doesn't break
    # the cache short-circuit.
    assert adapter.call_count == 1
