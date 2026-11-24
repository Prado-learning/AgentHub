"""Authority is checked before execution and bound to the exact resumed action."""

from dataclasses import replace
import pytest
from agenthub.domain.authority import AuthorityTier as Tier
from agenthub.domain.plan import Plan, PlanStep
from agenthub.domain.run import RunContext
from agenthub.adapters.base import AgentResult
from agenthub.harness.runner import HarnessRunner
from agenthub.harness.authority_gate import (
    AuthorityGate,
    StrictAuthorityGate,
    GateAction,
    GateDecision,
)


class Counter:
    id = "orchestrator"

    def __init__(self):
        self.calls = 0

    def run(self, task, context):
        self.calls += 1
        return AgentResult(agent_id=self.id)


def context():
    return RunContext(
        conversation_id="c",
        message="task",
        history=[],
        selected_agents=["orchestrator"],
    )


def step(tier):
    return PlanStep(id="s", agent_id="orchestrator", task="task", authority=tier)


@pytest.mark.parametrize("tier", list(Tier))
def test_gate_checks_before_dispatch(tier):
    expected = (
        GateAction.PROCEED
        if tier == Tier.L1_READONLY
        else GateAction.REQUEST_CONFIRMATION
    )
    assert AuthorityGate().before_dispatch(step(tier)).action == expected
    assert (
        AuthorityGate()
        .after_dispatch(step(tier), result=AgentResult(agent_id="orchestrator"))
        .action
        == GateAction.PROCEED
    )


@pytest.mark.parametrize("tier", list(Tier))
def test_strict_gate(tier):
    expected = {
        Tier.L1_READONLY: GateAction.PROCEED,
        Tier.L2_REVERSIBLE: GateAction.REQUEST_CONFIRMATION,
        Tier.L3_IRREVERSIBLE: GateAction.REFUSE,
    }[tier]
    assert StrictAuthorityGate().before_dispatch(step(tier)).action == expected


@pytest.mark.parametrize("tier", [Tier.L2_REVERSIBLE, Tier.L3_IRREVERSIBLE])
def test_approval_resumes_exact_step_once(tier):
    adapter = Counter()
    runner = HarnessRunner(adapters={adapter.id: adapter})
    pending = runner.run(context(), plan=Plan(steps=[step(tier)], reason="test"))
    assert pending.status == "waiting_approval" and adapter.calls == 0
    fingerprint = pending.checkpoint["pending_confirmations"][0]["fingerprint"]
    done = runner.run(
        context(), checkpoint=pending.checkpoint, approvals={"s": fingerprint}
    )
    assert done.status == "success" and adapter.calls == 1
    again = runner.run(
        context(), checkpoint=done.checkpoint, approvals={"s": fingerprint}
    )
    assert again.status == "success" and adapter.calls == 1


def test_changed_context_invalidates_approval():
    adapter = Counter()
    runner = HarnessRunner(adapters={adapter.id: adapter})
    first = runner.run(
        context(), plan=Plan(steps=[step(Tier.L2_REVERSIBLE)], reason="test")
    )
    fingerprint = first.checkpoint["pending_confirmations"][0]["fingerprint"]
    changed = runner.run(
        replace(context(), message="different task"),
        checkpoint=first.checkpoint,
        approvals={"s": fingerprint},
    )
    assert changed.status == "waiting_approval" and adapter.calls == 0


def test_rejected_dependency_is_never_executed():
    adapter = Counter()
    runner = HarnessRunner(adapters={adapter.id: adapter})
    plan = Plan(
        steps=[
            step(Tier.L2_REVERSIBLE),
            replace(step(Tier.L1_READONLY), id="child", depends_on=["s"]),
        ],
        reason="test",
    )
    result = runner.run(context(), plan=plan, rejected={"s"})
    assert adapter.calls == 0
    assert all(
        value["status"] == "skipped"
        for value in result.checkpoint["step_results"].values()
    )


def test_custom_gate_can_request_l1_before_execution():
    class Ask(AuthorityGate):
        def before_dispatch(self, step):
            return GateDecision(GateAction.REQUEST_CONFIRMATION, "review")

    adapter = Counter()
    result = HarnessRunner(adapters={adapter.id: adapter}, authority_gate=Ask()).run(
        context(), plan=Plan(steps=[step(Tier.L1_READONLY)], reason="test")
    )
    assert result.status == "waiting_approval" and adapter.calls == 0


def test_strict_refusal_does_not_dispatch():
    adapter = Counter()
    result = HarnessRunner(
        adapters={adapter.id: adapter}, authority_gate=StrictAuthorityGate()
    ).run(context(), plan=Plan(steps=[step(Tier.L3_IRREVERSIBLE)], reason="test"))
    assert result.status == "failed" and adapter.calls == 0
