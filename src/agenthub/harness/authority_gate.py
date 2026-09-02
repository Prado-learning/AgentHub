"""Pluggable authority gate.

Sits between the planner and the adapter. For every step the gate
makes two kinds of decisions:

* ``before_dispatch`` — should this step run at all? L3 steps run so
  they can produce an SOP artifact (the article's "model gives SOP,
  human decides whether to apply" model), but custom gates can refuse
  when the surrounding context is wrong (e.g. an active incident, a
  paused deploy channel, a maintenance window).
* ``after_dispatch`` — once the adapter returned, do we still need
  confirmation? L2/L3 always do on success, even when the model was
  confident. L1 never does.

The default :class:`AuthorityGate` is fully backward compatible: it
lets every step run and only flags L2/L3 successes for confirmation.
Production deployments can swap in a stricter gate (or an async one)
without touching the harness internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agenthub.domain.authority import AuthorityTier
from agenthub.domain.plan import PlanStep
from agenthub.adapters.base import AgentResult


class GateAction(str, Enum):
    """What the runner must do next."""

    PROCEED = "proceed"
    REQUEST_CONFIRMATION = "request_confirmation"
    REFUSE = "refuse"


@dataclass(frozen=True)
class GateDecision:
    """One verdict returned by the gate."""

    action: GateAction
    reason: str


class AuthorityGate:
    """Default permissive gate.

    * ``before_dispatch`` always proceeds; L3 still runs to produce
      the SOP artifact the article requires. Override to add custom
      restrictions (maintenance windows, kill switches, RBAC).
    * ``after_dispatch`` requests confirmation for every successful
      L2 or L3 step. L1 and failed steps proceed without confirmation.
    """

    def before_dispatch(self, step: PlanStep) -> GateDecision:
        return GateDecision(
            action=GateAction.PROCEED,
            reason="default gate is permissive at dispatch",
        )

    def after_dispatch(
        self, step: PlanStep, result: AgentResult
    ) -> GateDecision:
        if result.status != "success":
            return GateDecision(
                action=GateAction.PROCEED, reason="failed steps skip confirmation"
            )
        if step.authority is AuthorityTier.L2_REVERSIBLE:
            return GateDecision(
                action=GateAction.REQUEST_CONFIRMATION,
                reason=(
                    "L2 step produced a reversible suggestion; "
                    "awaiting human confirmation before applying."
                ),
            )
        if step.authority is AuthorityTier.L3_IRREVERSIBLE:
            return GateDecision(
                action=GateAction.REQUEST_CONFIRMATION,
                reason=(
                    "L3 step emitted an SOP; irreversible actions are "
                    "never auto-applied. Awaiting human approval."
                ),
            )
        return GateDecision(action=GateAction.PROCEED, reason="L1 is auto-executable")


class StrictAuthorityGate(AuthorityGate):
    """Example stricter gate — refuses L3 outright.

    Useful for read-only / staging deployments where irreversible
    actions should not run at all. Override ``before_dispatch`` to
    wire in incident-driven kill switches, RBAC, or maintenance
    windows.
    """

    def before_dispatch(self, step: PlanStep) -> GateDecision:
        if step.authority is AuthorityTier.L3_IRREVERSIBLE:
            return GateDecision(
                action=GateAction.REFUSE,
                reason="L3 disabled by StrictAuthorityGate",
            )
        return super().before_dispatch(step)


def permissive_gate() -> AuthorityGate:
    """Shorthand factory — useful in tests and the default wiring."""

    return AuthorityGate()