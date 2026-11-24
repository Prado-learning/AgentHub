"""P3 — ``run.metrics`` lifecycle event.

The harness emits a single ``run.metrics`` event after ``run.completed``
that rolls up counters for monitoring:

* steps planned / succeeded / failed / short-circuited
* llm calls + cache hits
* per-tier authority counts and per-agent call counts
* total + max stage cost

These tests build a small :class:`HarnessRunner` end-to-end and verify
the event is emitted with the right shape.
"""

from __future__ import annotations

from typing import Any

from agenthub.domain.authority import AuthorityTier
from agenthub.domain.plan import Plan, PlanStep
from agenthub.domain.run import RunContext
from agenthub.harness.runner import HarnessRunner
from agenthub.harness.tracing import FlowTracer


def _build_context() -> RunContext:
    return RunContext(
        conversation_id="conv_metrics",
        message="draft a release plan",
        history=[],
        selected_agents=["codex", "ui_builder"],
    )


def _success_plan() -> Plan:
    return Plan(
        steps=[
            PlanStep(
                id="s1",
                agent_id="codex",
                task="outline the release",
                tools=["file_reader_tool"],
                authority=AuthorityTier.L1_READONLY,
            ),
            PlanStep(
                id="s2",
                agent_id="ui_builder",
                task="compose release notes",
                tools=["file_writer_tool"],
                authority=AuthorityTier.L2_REVERSIBLE,
                depends_on=["s1"],
            ),
        ],
        reason="test plan",
    )


def _metrics_event(events: list[Any]) -> dict[str, Any] | None:
    for event in events:
        if event.type == "run.metrics":
            return event.payload
    return None


def test_run_metrics_event_is_emitted_after_run_completed() -> None:
    runner = HarnessRunner(adapters={}, tracer=FlowTracer(enabled=True))
    runner.run = runner.run  # type: ignore[attr-defined]
    result = runner.run(_build_context())  # type: ignore[arg-type]
    payload = _metrics_event(result.events)
    assert payload is not None, "run.metrics event should be present"


def test_run_metrics_aggregates_step_outcomes() -> None:
    plan = _success_plan()
    runner = HarnessRunner(adapters={}, tracer=FlowTracer(enabled=True))
    runner.run = runner.run  # type: ignore[attr-defined]
    # Stub the planner by patching the runner's planner; instead we just
    # pass a context and verify the *existing* code path produces a
    # metrics event with consistent counters.
    result = runner.run(_build_context())  # type: ignore[arg-type]
    payload = _metrics_event(result.events)
    assert payload is not None
    assert "steps_planned" in payload
    assert "steps_succeeded" in payload
    assert "steps_failed" in payload
    assert "authority_tier_counts" in payload
    assert "agent_call_counts" in payload
    # Counters must sum correctly.
    assert (
        payload["steps_succeeded"] + payload["steps_failed"]
        == payload["steps_planned"]
    )


def test_run_metrics_costs_include_stage_sum() -> None:
    runner = HarnessRunner(adapters={}, tracer=FlowTracer(enabled=True))
    result = runner.run(_build_context())  # type: ignore[arg-type]
    payload = _metrics_event(result.events)
    assert payload is not None
    assert payload["total_cost_ms"] >= 0
    assert payload["max_stage_cost_ms"] >= 0
    # If any stages had cost > 0, max must be >= total mean.
    if payload["total_cost_ms"] > 0:
        assert payload["max_stage_cost_ms"] <= payload["total_cost_ms"]


def test_run_metrics_records_run_id() -> None:
    runner = HarnessRunner(adapters={}, tracer=FlowTracer(enabled=True))
    result = runner.run(_build_context())  # type: ignore[arg-type]
    payload = _metrics_event(result.events)
    assert payload is not None
    assert payload["run_id"] == result.run_id
