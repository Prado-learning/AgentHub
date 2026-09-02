"""Tiered authority for agent actions.

Implements the article's L1 / L2 / L3 confidence model:

- L1 (read-only): the harness may execute the action on its own —
  querying an atomic API, reading a file, recognising an image.
- L2 (reversible): the harness may produce a suggestion that affects
  non-destructive state — tagging, comment, generated script — but a
  human (or upstream business gate) must confirm before it is applied.
- L3 (irreversible): the harness may only emit a procedure (SOP); it
  must never auto-execute — auto-reject, auto-close, automatic writes.

The tier travels on the :class:`agenthub.domain.plan.PlanStep` so the
planner and the harness agree on the action's blast radius before it
runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuthorityTier(str, Enum):
    L1_READONLY = "L1"
    L2_REVERSIBLE = "L2"
    L3_IRREVERSIBLE = "L3"

    @property
    def auto_executable(self) -> bool:
        """``True`` only for L1; L2/L3 require confirmation or SOP-only."""

        return self is AuthorityTier.L1_READONLY

    @property
    def requires_user_confirmation(self) -> bool:
        return self is AuthorityTier.L2_REVERSIBLE

    @property
    def sop_only(self) -> bool:
        return self is AuthorityTier.L3_IRREVERSIBLE


@dataclass(frozen=True)
class AuthorityDecision:
    """Concrete decision recorded for one step after it runs.

    ``tier`` mirrors the step's planned tier. ``reason`` is a short
    human-readable explanation suitable for inclusion in the run
    summary. ``can_short_circuit`` is True when this step's successful
    output satisfies the run's stopping condition (IsFinal).
    """

    tier: AuthorityTier
    reason: str
    can_short_circuit: bool = False
