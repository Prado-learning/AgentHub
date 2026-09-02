"""P0-2 — Authority gate contract and integration with the runner.

Two surfaces are covered:

1. **Unit tests** — :class:`AuthorityGate` returns the right verdicts
   for each tier, and :class:`StrictAuthorityGate` actually refuses L3.
2. **Runner integration** — wiring a stricter gate changes the
   ``authority.refused`` event flow and prevents the adapter from being
   called.
"""

from __future__ import annotations

import pytest

from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.adapters.mock.adapter import MockAgentAdapter
from agenthub.domain.authority import AuthorityTier
from agenthub.domain.plan import Plan, PlanStep
from agenthub.domain.run import RunContext
from agenthub.harness.authority_gate import (
    AuthorityGate,
    GateAction,
    GateDecision,
    StrictAuthorityGate,
    permissive_gate,
)
from agenthub.harness.runner import HarnessRunner
from agenthub.tracing import FlowTracer


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def _step(tier: AuthorityTier) -> PlanStep:
    return PlanStep(
        id=f"s_{tier.value.lower()}",
        agent_id="any",
        task="do the thing",
        tools=[],
        authority=tier,
    )


def _result(status: str = "success") -> AgentResult:
    return AgentResult(agent_id="any", status=status)


def test_default_gate_before_dispatch_always_proceeds() -> None:
    gate = AuthorityGate()
    for tier in AuthorityTier:
        decision = gate.before_dispatch(_step(tier))
        assert decision.action is GateAction.PROCEED, tier


def test_default_gate_after_dispatch_skips_failed_steps() -> None:
    gate = AuthorityGate()
    for tier in AuthorityTier:
        decision = gate.after_dispatch(_step(tier), _result(status="failed"))
        assert decision.action is GateAction.PROCEED, tier


def test_default_gate_after_dispatch_requests_confirmation_for_l2_l3() -> None:
    gate = AuthorityGate()
    for tier in (AuthorityTier.L2_REVERSIBLE, AuthorityTier.L3_IRREVERSIBLE):
        decision = gate.after_dispatch(_step(tier), _result(status="success"))
        assert decision.action is GateAction.REQUEST_CONFIRMATION, tier


def test_default_gate_after_dispatch_proceeds_for_l1() -> None:
    gate = AuthorityGate()
    decision = gate.after_dispatch(_step(AuthorityTier.L1_READONLY), _result())
    assert decision.action is GateAction.PROCEED


def test_strict_gate_refuses_l3_before_dispatch() -> None:
    gate = StrictAuthorityGate()
    assert (
        gate.before_dispatch(_step(AuthorityTier.L3_IRREVERSIBLE)).action
        is GateAction.REFUSE
    )
    # L1/L2 still proceed.
    assert (
        gate.before_dispatch(_step(AuthorityTier.L1_READONLY)).action
        is GateAction.PROCEED
    )
    assert (
        gate.before_dispatch(_step(AuthorityTier.L2_REVERSIBLE)).action
        is GateAction.PROCEED
    )


def test_strict_gate_still_requests_confirmation_after_dispatch() -> None:
    """Even when L3 is allowed to run (default path), the strict gate
    still asks for confirmation — refusal only kicks in before the
    adapter is called."""

    gate = StrictAuthorityGate()
    decision = gate.after_dispatch(_step(AuthorityTier.L3_IRREVERSIBLE), _result())
    assert decision.action is GateAction.REQUEST_CONFIRMATION


def test_permissive_factory_returns_default_gate() -> None:
    gate = permissive_gate()
    assert isinstance(gate, AuthorityGate)
    assert not isinstance(gate, StrictAuthorityGate)


def test_gate_decision_is_immutable() -> None:
    decision = GateDecision(action=GateAction.PROCEED, reason="x")
    with pytest.raises((AttributeError, Exception)):
        decision.action = GateAction.REFUSE  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


def _stub_runner_with_plan(
    monkeypatch: pytest.MonkeyPatch,
    plan: Plan,
    *,
    gate: AuthorityGate,
) -> HarnessRunner:
    monkeypatch.setenv("AGENT_DEBUG", "1")

    runner = HarnessRunner(
        tracer=FlowTracer(enabled=True),
        adapters={"any": MockAgentAdapter(agent_id="any", name="Any")},
        authority_gate=gate,
    )

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: ANN001
            return plan

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)
    return runner


def test_strict_gate_refuses_l3_step_and_skips_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = Plan(
        steps=[
            PlanStep(
                id="deploy",
                agent_id="any",
                task="deploy",
                tools=[],
                authority=AuthorityTier.L3_IRREVERSIBLE,
            ),
        ],
        reason="strict gate test",
    )

    class _ExplodingAdapter:
        agent_id = "any"
        calls = 0

        def run(self, task: AgentTask, context: RunContext) -> AgentResult:
            _ExplodingAdapter.calls += 1
            return AgentResult(agent_id=self.agent_id, status="success")

    runner = HarnessRunner(
        adapters={"any": _ExplodingAdapter()},
        authority_gate=StrictAuthorityGate(),
    )

    class _StubOrchestrator:
        def __init__(self, **_kwargs):  # noqa: ANN001
            pass

        def plan(self, _context):  # noqa: ANN001
            return plan

    monkeypatch.setattr("agenthub.harness.runner.Orchestrator", _StubOrchestrator)

    result = runner.run(
        RunContext(
            conversation_id="c",
            message="deploy",
            history=[],
            selected_agents=["any"],
        )
    )

    refused = [e for e in result.events if e.type == "authority.refused"]
    assert len(refused) == 1
    assert refused[0].payload["step_id"] == "deploy"
    assert "StrictAuthorityGate" in refused[0].payload["reason"]
    assert _ExplodingAdapter.calls == 0  # adapter never ran

    completions = [e for e in result.events if e.type == "agent.completed"]
    assert completions, result.events
    assert completions[-1].payload["status"] == "failed"
    assert completions[-1].payload["error"] is not None


def test_default_gate_lets_l3_run_but_requests_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = Plan(
        steps=[
            PlanStep(
                id="deploy",
                agent_id="any",
                task="deploy",
                tools=[],
                authority=AuthorityTier.L3_IRREVERSIBLE,
            ),
        ],
        reason="default gate lets L3 produce SOP",
    )

    runner = _stub_runner_with_plan(monkeypatch, plan, gate=AuthorityGate())

    result = runner.run(
        RunContext(
            conversation_id="c",
            message="deploy",
            history=[],
            selected_agents=["any"],
        )
    )

    # L3 ran (no refused event).
    assert [e.type for e in result.events].count("authority.refused") == 0
    completions = [e for e in result.events if e.type == "agent.completed"]
    assert completions[-1].payload["status"] == "success"

    # ...but confirmation is requested because L3 success → after_dispatch.
    confirmations = [e for e in result.events if e.type == "authority.requires_confirmation"]
    assert len(confirmations) == 1
    assert "SOP" in confirmations[0].payload["reason"]


def test_default_gate_l1_step_emits_no_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = Plan(
        steps=[
            PlanStep(
                id="read",
                agent_id="any",
                task="read",
                tools=[],
                authority=AuthorityTier.L1_READONLY,
            ),
        ],
        reason="L1 auto-executable",
    )

    runner = _stub_runner_with_plan(monkeypatch, plan, gate=AuthorityGate())

    result = runner.run(
        RunContext(
            conversation_id="c",
            message="read",
            history=[],
            selected_agents=["any"],
        )
    )

    assert (
        [e.type for e in result.events].count("authority.requires_confirmation") == 0
    )
    assert [e.type for e in result.events].count("authority.refused") == 0


def test_custom_gate_can_request_even_for_l1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom gates can override the default; a paranoid policy that
    asks for confirmation even on L1 must still work end-to-end."""

    class _ParanoidGate(AuthorityGate):
        def after_dispatch(self, step: PlanStep, result: AgentResult) -> GateDecision:
            if result.status == "success":
                return GateDecision(
                    action=GateAction.REQUEST_CONFIRMATION,
                    reason="paranoid policy requires approval for every success",
                )
            return super().after_dispatch(step, result)

    plan = Plan(
        steps=[
            PlanStep(
                id="read",
                agent_id="any",
                task="read",
                tools=[],
                authority=AuthorityTier.L1_READONLY,
            ),
        ],
        reason="paranoid",
    )

    runner = _stub_runner_with_plan(monkeypatch, plan, gate=_ParanoidGate())

    result = runner.run(
        RunContext(
            conversation_id="c",
            message="read",
            history=[],
            selected_agents=["any"],
        )
    )

    confirmations = [e for e in result.events if e.type == "authority.requires_confirmation"]
    assert len(confirmations) == 1
    assert confirmations[0].payload["authority"] == "L1"  # tier is still L1
    assert "paranoid" in confirmations[0].payload["reason"]