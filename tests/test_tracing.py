"""Tests for the per-stage FlowTracer and HarnessRunner integration."""

from __future__ import annotations

import pytest

from agenthub import HarnessRunner
from agenthub.domain.run import RunContext
from agenthub.tracing import FlowTracer, StageRecorder
from agenthub.tracing.tracer import _NullRecorder


def test_flow_tracer_disabled_by_default() -> None:
    """Without AGENT_DEBUG, the tracer reports no stages and stays cheap."""

    tracer = FlowTracer()
    assert tracer.enabled is False
    assert tracer.stages == []
    assert tracer.record_lifecycle("run.started", "Run started", {"k": 1}) is None


def test_flow_tracer_explicit_enabled_records_lifecycle() -> None:
    tracer = FlowTracer(enabled=True)

    trace = tracer.record_lifecycle(
        "run.started",
        "Run started",
        {"conversation_id": "conv_1"},
    )

    assert trace is not None
    assert trace.stage_id == "run.started"
    assert trace.stage_name == "Run started"
    assert trace.inputs == {"conversation_id": "conv_1"}
    stages = tracer.stages
    assert len(stages) == 1
    assert stages[0].stage_id == "run.started"


def test_flow_tracer_begin_stage_measures_cost_and_finalizes() -> None:
    tracer = FlowTracer(enabled=True)

    with tracer.begin_stage("step_1", "Execute step 1") as st:
        assert isinstance(st, StageRecorder)
        assert not isinstance(st, _NullRecorder)
        st.set_input({"task": "build a page"})
        st.set_branch("ui_generation")
        st.set_raw_api({"status": "ok"})
        st.set_output({"artifact_count": 3})
        st.set_final(True, reason="conclusive answer")

    stages = tracer.stages
    assert len(stages) == 1
    final = stages[0]
    assert final.stage_id == "step_1"
    assert final.branch_hit == "ui_generation"
    assert final.inputs == {"task": "build a page"}
    assert final.raw_api_data == {"status": "ok"}
    assert final.outputs == {"artifact_count": 3, "final_reason": "conclusive answer"}
    assert final.final is True
    assert final.cost_ms >= 0


def test_flow_tracer_disabled_begin_stage_returns_noop_recorder() -> None:
    tracer = FlowTracer(enabled=False)

    with tracer.begin_stage("step_1", "Execute step 1") as st:
        assert isinstance(st, _NullRecorder)
        # All setter calls must be silent no-ops
        st.set_input({"x": 1})
        st.set_raw_api({"y": 2})
        st.set_branch("branch")
        st.set_output({"z": 3})
        st.set_error("err")
        st.set_final(True, reason="r")

    assert tracer.stages == []


def test_harness_runner_run_with_tracer_disabled_yields_empty_debug_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default behavior: AGENT_DEBUG unset → debug_trace is empty (zero overhead)."""

    monkeypatch.delenv("AGENT_DEBUG", raising=False)
    runner = HarnessRunner()
    runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="hello",
            history=[],
            selected_agents=["orchestrator"],
        )
    )

    # Lifecycle events still flow into the front-end-facing event stream.
    assert [event.type for event in runner.events[:2]] == ["run.started", "run.planned"]
    # But the debug_trace stage log is empty (no overhead, no data).
    assert runner.debug_trace == []


def test_harness_runner_run_with_tracer_enabled_populates_debug_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AGENT_DEBUG=1 → run.started / run.planned / run.completed land in debug_trace."""

    monkeypatch.setenv("AGENT_DEBUG", "1")
    runner = HarnessRunner()
    runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="Build a React Todo page",
            history=[],
            selected_agents=["orchestrator", "ui_builder", "code_reviewer"],
        )
    )

    stage_ids = [trace.stage_id for trace in runner.debug_trace]
    # Lifecycle events anchor the trace; step/tool stages fill in the
    # middle as Phase 2 wired them through ``begin_stage``.
    assert stage_ids[0] == "run.started"
    assert "run.planned" in stage_ids
    # The trailing lifecycle can be either ``run.completed`` (older
    # harness) or ``run.metrics`` once Phase 3 monitoring is enabled.
    assert stage_ids[-1] in {"run.completed", "run.metrics"}
    # We expect at least one step-level stage and one tool-level stage
    # because ui_builder / file_reader run inside begin_stage blocks.
    assert any(sid.startswith("step_") for sid in stage_ids), stage_ids
    assert any(".preview_tool" in sid or ".file_reader_tool" in sid for sid in stage_ids), stage_ids

    planned = next(trace for trace in runner.debug_trace if trace.stage_id == "run.planned")
    assert planned.inputs["step_count"] >= 1
    assert "ui_builder" in {step["agent_id"] for step in planned.inputs["steps"]}
    # Planner must have inferred an authority per step.
    assert all("authority" in step for step in planned.inputs["steps"])

    completed = next(
        trace for trace in runner.debug_trace if trace.stage_id == "run.completed"
    )
    assert completed.inputs["status"] == "success"
    assert completed.inputs["artifact_count"] >= 1
    assert "authority_tiers" in completed.inputs


def test_harness_runner_explicit_tracer_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passing a tracer explicitly beats the environment default."""

    monkeypatch.delenv("AGENT_DEBUG", raising=False)
    runner = HarnessRunner(tracer=FlowTracer(enabled=True))
    runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="hello",
            history=[],
            selected_agents=["orchestrator"],
        )
    )
    stage_ids = [trace.stage_id for trace in runner.debug_trace]
    assert stage_ids[0] == "run.started"
    assert stage_ids[-1] in {"run.completed", "run.metrics"}
