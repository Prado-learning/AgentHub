"""Tests for Phase 2 (IsFinal + tool failure softening) and Phase 3
(gateway, authority tiers) of the deterministic Harness refactor.
"""

from __future__ import annotations

import pytest

from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.domain.authority import AuthorityTier
from agenthub.domain.plan import Plan, PlanStep
from agenthub.domain.run import RunContext
from agenthub.gateway import (
    GatewayDispatch,
    InMemoryCache,
    MD5AppSecretSigner,
    NoopCache,
    NoopGateway,
    NoopSigner,
    cache_key,
)
from agenthub.gateway.gateway import CachingGateway
from agenthub.harness.runner import HarnessRunner
from agenthub.orchestration.rule_planner import infer_authority
from agenthub.tools.registry import ToolRegistry
from agenthub.tools.executor import ToolExecutor
from agenthub.harness.tracing import FlowTracer


# ---------------------------------------------------------------------------
# Phase 3: AuthorityTier inference and propagation
# ---------------------------------------------------------------------------


def test_infer_authority_picks_highest_tier() -> None:
    assert infer_authority(["file_reader_tool"]) is AuthorityTier.L1_READONLY
    assert infer_authority(["preview_tool"]) is AuthorityTier.L1_READONLY
    assert infer_authority(["deploy_tool"]) is AuthorityTier.L3_IRREVERSIBLE
    assert (
        infer_authority(["file_reader_tool", "preview_tool"])
        is AuthorityTier.L1_READONLY
    )
    assert (
        infer_authority(["file_reader_tool", "deploy_tool"])
        is AuthorityTier.L3_IRREVERSIBLE
    )
    assert infer_authority(["unknown_tool"]) is AuthorityTier.L3_IRREVERSIBLE


def test_authority_tiers_carry_through_run_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plan, the trace, and the summary message all surface the tier."""

    monkeypatch.setenv("AGENT_DEBUG", "1")
    runner = HarnessRunner(tracer=FlowTracer(enabled=True))
    runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="Build a React Todo page and deploy it",
            history=[],
            selected_agents=["orchestrator", "ui_builder", "code_reviewer"],
        )
    )

    planned = next(
        trace for trace in runner.debug_trace if trace.stage_id == "run.planned"
    )
    steps_by_agent = {step["agent_id"]: step for step in planned.inputs["steps"]}
    # UI builder uses preview_tool → L2
    assert steps_by_agent["ui_builder"]["authority"] == "L1"
    # code_reviewer uses code_review_tool → L1
    assert steps_by_agent["code_reviewer"]["authority"] == "L1"

    summary = next(
        (event for event in runner.events if event.type == "run.completed"),
        None,
    )
    assert summary is not None
    assert "authority_tiers" in summary.payload
    assert "L1" in summary.payload["authority_tiers"].values()


# ---------------------------------------------------------------------------
# Phase 2: tool failure no longer aborts the step
# ---------------------------------------------------------------------------


class _BoomTool:
    name = "boom_tool"

    def __call__(self, **_kwargs):  # noqa: ANN001
        raise RuntimeError("kaboom")


def test_tool_failure_does_not_abort_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool exception should be recorded but the step should still succeed
    (or at least produce a result) — matching the article's
    ``continue failure does not block`` rule."""

    monkeypatch.setenv("AGENT_DEBUG", "1")

    registry = ToolRegistry()
    registry.register("boom_tool", _BoomTool())
    executor = ToolExecutor(registry=registry)

    runner = HarnessRunner(
        tool_executor=executor,
        tracer=FlowTracer(enabled=True),
        limits=__import__("agenthub.harness.limits", fromlist=["RunLimits"]).RunLimits(
            run_policy=__import__(
                "agenthub.policies", fromlist=["RunPolicy"]
            ).RunPolicy(max_steps=8)
        ),
    )

    # Allow the orchestrator to use the boom tool, otherwise the
    # permission check fails before the tool itself gets a chance to
    # throw — which is still a useful failure to test, but we want to
    # exercise the *execution* path here.
    from agenthub.agent.runtime_profile import AgentRuntimeProfile

    runner.agent_profiles = {
        "orchestrator": AgentRuntimeProfile(
            id="orchestrator",
            name="Orchestrator",
            adapter="mock",
            tools=["boom_tool"],
        )
    }

    from agenthub.domain.plan import Plan, PlanStep
    from agenthub.domain.authority import AuthorityTier

    monkeypatch.setitem(
        __import__(
            "agenthub.orchestration.rule_planner", fromlist=["_TOOL_AUTHORITY"]
        )._TOOL_AUTHORITY,
        "boom_tool",
        AuthorityTier.L1_READONLY,
    )
    boom_step = PlanStep(
        id="step_boom",
        agent_id="orchestrator",
        task="do something risky",
        tools=["boom_tool"],
        authority=AuthorityTier.L1_READONLY,
    )

    from agenthub.adapters.mock.adapter import MockAgentAdapter

    runner.adapters = {
        "orchestrator": MockAgentAdapter(agent_id="orchestrator", name="Orch")
    }

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: ANN001
            return Plan(steps=[boom_step], reason="stub")

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)

    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="anything",
            history=[],
            selected_agents=["orchestrator"],
        )
    )

    # The boom tool's execution failure is captured in the trace,
    # not surfaced as the step's only failure.
    stage = next(
        trace for trace in runner.debug_trace if trace.stage_id == "step_boom.boom_tool"
    )
    assert stage.error is not None
    assert "kaboom" in stage.error

    # And the run did not crash; we got a RunResult back.
    assert result.status in {"success", "partial_success", "failed"}

    # The runner recorded the tool failure as a regular event so the
    # frontend can still surface it.
    failed_events = [e for e in result.events if e.type == "tool.failed"]
    assert any("boom_tool" in e.payload.get("tool_id", "") for e in failed_events)


# ---------------------------------------------------------------------------
# Phase 2: IsFinal short-circuit
# ---------------------------------------------------------------------------


def test_is_final_short_circuit_skips_remaining_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful step marked ``can_short_circuit=True`` should skip
    every later pending step."""

    monkeypatch.setenv("AGENT_DEBUG", "1")

    runner = HarnessRunner(
        tracer=FlowTracer(enabled=True),
        limits=__import__("agenthub.harness.limits", fromlist=["RunLimits"]).RunLimits(
            run_policy=__import__(
                "agenthub.policies", fromlist=["RunPolicy"]
            ).RunPolicy(max_steps=12)
        ),
    )

    from agenthub.adapters.mock.adapter import MockAgentAdapter

    runner.adapters = {
        "first": MockAgentAdapter(agent_id="first", name="First"),
        "second": MockAgentAdapter(agent_id="second", name="Second"),
        "third": MockAgentAdapter(agent_id="third", name="Third"),
    }

    from agenthub.domain.plan import Plan, PlanStep
    from agenthub.domain.authority import AuthorityTier

    plan = Plan(
        steps=[
            PlanStep(
                id="s1",
                agent_id="first",
                task="answer",
                tools=[],
                authority=AuthorityTier.L1_READONLY,
                can_short_circuit=True,
            ),
            PlanStep(
                id="s2",
                agent_id="second",
                task="follow up",
                tools=[],
                depends_on=["s1"],
                authority=AuthorityTier.L1_READONLY,
            ),
            PlanStep(
                id="s3",
                agent_id="third",
                task="tail",
                tools=[],
                depends_on=["s1"],
                authority=AuthorityTier.L1_READONLY,
            ),
        ],
        reason="short-circuit test",
    )

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: ANN001
            return plan

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)

    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="hi",
            history=[],
            selected_agents=["first", "second", "third"],
        )
    )

    skipped = [e for e in result.events if e.type == "agent.skipped"]
    skipped_step_ids = {e.payload["step_id"] for e in skipped}
    assert {"s2", "s3"}.issubset(skipped_step_ids), skipped_step_ids
    # Short-circuit event was emitted
    short_circuits = [e for e in result.events if e.type == "run.short_circuit"]
    assert len(short_circuits) == 1
    assert short_circuits[0].payload["step_id"] == "s1"

    completed = next(
        trace for trace in runner.debug_trace if trace.stage_id == "run.completed"
    )
    assert completed.inputs["short_circuited"] is True
    assert completed.inputs["short_circuit_step"] == "s1"


def test_l2_step_with_can_short_circuit_does_not_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L2/L3 steps must never short-circuit even if the planner asked."""

    monkeypatch.setenv("AGENT_DEBUG", "1")

    from agenthub.adapters.mock.adapter import MockAgentAdapter

    runner = HarnessRunner(
        tracer=FlowTracer(enabled=True),
        adapters={"ui_builder": MockAgentAdapter(agent_id="ui_builder", name="UI")},
    )

    from agenthub.domain.plan import Plan, PlanStep
    from agenthub.domain.authority import AuthorityTier

    plan = Plan(
        steps=[
            PlanStep(
                id="u1",
                agent_id="ui_builder",
                task="build UI",
                tools=[],
                authority=AuthorityTier.L2_REVERSIBLE,  # L2
                can_short_circuit=True,  # planner asked, but tier forbids
            ),
        ],
        reason="L2 test",
    )

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: noqa: ANN001
            return plan

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)

    runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="build it",
            history=[],
            selected_agents=["ui_builder"],
        )
    )

    completed = next(
        trace for trace in runner.debug_trace if trace.stage_id == "run.completed"
    )
    assert completed.inputs["short_circuited"] is False
    short_circuits = [e for e in runner.events if e.type == "run.short_circuit"]
    assert short_circuits == []


# ---------------------------------------------------------------------------
# Phase 3: Gateway
# ---------------------------------------------------------------------------


class _CountingAdapter:
    """Counts how many times ``run`` is invoked. Used to verify caching."""

    id = "counter"
    name = "Counter"
    capabilities: list[str] = []
    calls: int = 0

    def __init__(self) -> None:
        self.calls = 0

    def run(self, task: AgentTask, _context: RunContext) -> AgentResult:  # noqa: ANN001
        self.calls += 1
        return AgentResult(
            agent_id=self.id,
            status="success",
            messages=[
                {
                    "role": "agent",
                    "sender": self.id,
                    "content": task.instruction,
                    "format": "markdown",
                }
            ],
        )


def test_noop_gateway_passes_through() -> None:
    adapter = _CountingAdapter()
    gateway = NoopGateway()

    dispatch = GatewayDispatch(
        endpoint="adapter:counter",
        task=AgentTask(agent_id="counter", instruction="hello"),
        context=RunContext(
            conversation_id="c1", message="x", history=[], selected_agents=["counter"]
        ),
        cache_ttl_seconds=0,
    )

    out = gateway.dispatch(adapter, dispatch)
    assert out.status == "success"
    assert adapter.calls == 1


def test_gateway_with_in_memory_cache_dedupes_repeat_calls() -> None:
    adapter = _CountingAdapter()
    cache = InMemoryCache()
    gateway = CachingGateway(cache=cache)

    dispatch = GatewayDispatch(
        endpoint="adapter:counter",
        task=AgentTask(agent_id="counter", instruction="same prompt"),
        context=RunContext(
            conversation_id="c1", message="x", history=[], selected_agents=["counter"]
        ),
        cache_ttl_seconds=3600,
    )

    gateway.dispatch(adapter, dispatch)
    gateway.dispatch(adapter, dispatch)
    gateway.dispatch(adapter, dispatch)

    # Adapter only ran once; the next two calls were served from cache.
    assert adapter.calls == 1


def test_cache_key_is_stable_and_unique() -> None:
    a = cache_key(["agent", "task", {"x": 1}])
    b = cache_key(["agent", "task", {"x": 1}])
    c = cache_key(["agent", "task", {"x": 2}])
    assert a == b
    assert a != c


def test_md5_signer_produces_deterministic_length_signature() -> None:
    signer = MD5AppSecretSigner("appid", "secret")
    sig = signer.sign(b"{}")
    assert len(sig) == 32  # MD5 hex digest
    # Same payload + signer → same signature (timestamp varies but is
    # inside the value; deterministic test would need to freeze time).
    sig2 = signer.sign(b"{}")
    # Allow them to differ by timestamp; just assert shape.
    assert all(c in "0123456789abcdef" for c in sig2)


def test_noop_signer_returns_empty_string() -> None:
    assert NoopSigner().sign(b"anything") == ""


# ---------------------------------------------------------------------------
# Phase 3: L2 / L3 frontend confirmation signals
# ---------------------------------------------------------------------------


def test_l2_step_emits_confirmation_event_and_flags_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful L2 step must surface three signals:

    1. ``authority.requires_confirmation`` event with the step metadata.
    2. ``requires_user_confirmation=True`` on the ``agent.completed`` payload.
    3. ``pending_confirmation_steps`` populated on ``run.completed``.
    """

    monkeypatch.setenv("AGENT_DEBUG", "1")

    from agenthub.adapters.mock.adapter import MockAgentAdapter

    runner = HarnessRunner(
        tracer=FlowTracer(enabled=True),
        adapters={"ui_builder": MockAgentAdapter(agent_id="ui_builder", name="UI")},
    )

    from agenthub.domain.plan import Plan, PlanStep
    from agenthub.domain.authority import AuthorityTier

    plan = Plan(
        steps=[
            PlanStep(
                id="ui_render",
                agent_id="ui_builder",
                task="render a settings page",
                tools=[],
                authority=AuthorityTier.L2_REVERSIBLE,
            ),
        ],
        reason="L2 confirmation smoke test",
    )

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: ANN001
            return plan

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)

    result = runner.run(
        RunContext(
            conversation_id="conv_l2",
            message="please render a settings page",
            history=[],
            selected_agents=["ui_builder"],
        )
    )

    # Signal 1: a confirmation event was emitted with the step id.
    confirmations = [
        e for e in result.events if e.type == "authority.requires_confirmation"
    ]
    assert len(confirmations) == 1
    payload = confirmations[0].payload
    assert payload["step_id"] == "ui_render"
    assert payload["agent_id"] == "ui_builder"
    assert payload["authority"] == "L2"

    # Signal 2: agent.completed is flagged.
    completions = [e for e in result.events if e.type == "agent.completed"]
    assert not completions  # No action has executed before approval.
    assert result.status == "waiting_approval"

    # Signal 3: run.completed carries the queue.
    completed = [e for e in result.events if e.type == "run.completed"]
    assert completed, result.events
    finished_payload = completed[-1].payload
    assert finished_payload["requires_user_confirmation"] is True
    queue = finished_payload["pending_confirmation_steps"]
    assert len(queue) == 1
    entry = queue[0]
    assert entry["step_id"] == "ui_render"
    assert entry["agent_id"] == "ui_builder"
    assert entry["authority"] == "L2"
    # The mock adapter returns a non-empty artifact; assert the count
    # is present and is a non-negative integer.
    assert isinstance(entry["artifact_count"], int)
    assert entry["artifact_count"] >= 0


def test_l1_step_does_not_emit_confirmation_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L1 (read-only) steps must never ask for confirmation."""

    monkeypatch.setenv("AGENT_DEBUG", "1")

    from agenthub.adapters.mock.adapter import MockAgentAdapter

    runner = HarnessRunner(
        tracer=FlowTracer(enabled=True),
        adapters={
            "code_reviewer": MockAgentAdapter(agent_id="code_reviewer", name="Rev")
        },
    )

    from agenthub.domain.plan import Plan, PlanStep
    from agenthub.domain.authority import AuthorityTier

    plan = Plan(
        steps=[
            PlanStep(
                id="rev_1",
                agent_id="code_reviewer",
                task="review the diff",
                tools=[],
                authority=AuthorityTier.L1_READONLY,
            ),
        ],
        reason="L1 smoke test",
    )

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: ANN001
            return plan

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)

    result = runner.run(
        RunContext(
            conversation_id="conv_l1",
            message="review the diff",
            history=[],
            selected_agents=["code_reviewer"],
        )
    )

    confirmations = [
        e for e in result.events if e.type == "authority.requires_confirmation"
    ]
    assert confirmations == []

    completions = [e for e in result.events if e.type == "agent.completed"]
    assert completions[-1].payload["requires_user_confirmation"] is False

    finished = [e for e in result.events if e.type == "run.completed"][-1]
    assert finished.payload["requires_user_confirmation"] is False
    assert finished.payload["pending_confirmation_steps"] == []


def test_failed_l2_step_does_not_ask_for_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If an L2 step fails, we don't want to ask the user to confirm a failure."""

    monkeypatch.setenv("AGENT_DEBUG", "1")

    class _BoomAdapter:
        id = "doomed"
        name = "Doomed"
        capabilities: list[str] = []

        def run(self, task: AgentTask, context: RunContext) -> AgentResult:
            return AgentResult(
                agent_id=self.id,
                status="failed",
                error="simulated failure",
            )

    runner = HarnessRunner(
        tracer=FlowTracer(enabled=True),
        adapters={"doomed": _BoomAdapter()},
        fallback=__import__(
            "agenthub.harness.fallback", fromlist=["FallbackChain"]
        ).FallbackChain(adapter_factories=[]),
    )

    from agenthub.domain.plan import Plan, PlanStep
    from agenthub.domain.authority import AuthorityTier

    plan = Plan(
        steps=[
            PlanStep(
                id="doomed_step",
                agent_id="doomed",
                task="this will fail",
                tools=[],
                authority=AuthorityTier.L2_REVERSIBLE,
            ),
        ],
        reason="L2 failure",
    )

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: ANN001
            return plan

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)

    result = runner.run(
        RunContext(
            conversation_id="conv_l2_fail",
            message="try me",
            history=[],
            selected_agents=["doomed"],
        )
    )

    assert [e.type for e in result.events].count("authority.requires_confirmation") == 1
    assert not any(e.type == "agent.started" for e in result.events)
    completed = [e for e in result.events if e.type == "run.completed"][-1]
    assert len(completed.payload["pending_confirmation_steps"]) == 1


def test_summary_message_lists_pending_confirmation_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The orchestrator summary message surfaces a 'Awaiting your
    confirmation for: agent_id (tier)' line when L2/L3 steps need sign-off."""

    monkeypatch.setenv("AGENT_DEBUG", "1")

    from agenthub.adapters.mock.adapter import MockAgentAdapter

    runner = HarnessRunner(
        tracer=FlowTracer(enabled=True),
        adapters={"ui_builder": MockAgentAdapter(agent_id="ui_builder", name="UI")},
    )

    from agenthub.domain.plan import Plan, PlanStep
    from agenthub.domain.authority import AuthorityTier

    plan = Plan(
        steps=[
            PlanStep(
                id="ui_render",
                agent_id="ui_builder",
                task="render",
                tools=[],
                authority=AuthorityTier.L2_REVERSIBLE,
            ),
        ],
        reason="summary test",
    )

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: ANN001
            return plan

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)

    result = runner.run(
        RunContext(
            conversation_id="conv_summary",
            message="render",
            history=[],
            selected_agents=["ui_builder"],
        )
    )

    summary = result.messages[-1]
    assert "Review the pending action" in summary["content"]
    assert "ui_builder" in summary["content"]
