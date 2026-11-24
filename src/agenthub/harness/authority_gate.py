"""Approval is a precondition of dispatch, never a completion annotation."""

from dataclasses import dataclass
from enum import Enum
from agenthub.domain.authority import AuthorityTier
from agenthub.domain.plan import PlanStep
from agenthub.adapters.base import AgentResult


class GateAction(str, Enum):
    PROCEED = "proceed"
    REQUEST_CONFIRMATION = "request_confirmation"
    REFUSE = "refuse"


@dataclass(frozen=True)
class GateDecision:
    action: GateAction
    reason: str


class AuthorityGate:
    def before_dispatch(self, step: PlanStep) -> GateDecision:
        if step.authority != AuthorityTier.L1_READONLY:
            return GateDecision(
                GateAction.REQUEST_CONFIRMATION,
                "Review this exact action before it executes.",
            )
        return GateDecision(GateAction.PROCEED, "Automatic read-only step")

    def after_dispatch(self, step: PlanStep, result: AgentResult) -> GateDecision:
        return GateDecision(
            GateAction.PROCEED, "Dispatch authorization already checked"
        )


class StrictAuthorityGate(AuthorityGate):
    def before_dispatch(self, step: PlanStep) -> GateDecision:
        if step.authority == AuthorityTier.L3_IRREVERSIBLE:
            return GateDecision(GateAction.REFUSE, "L3 disabled by StrictAuthorityGate")
        return super().before_dispatch(step)


def permissive_gate() -> AuthorityGate:
    """Legacy factory name. It now returns the safe approval gate."""
    return AuthorityGate()
