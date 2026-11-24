"""Sandbox boundary policy: which authority tier gets which boundary.

Policy is data and the sandbox is its enforcer. This module holds the
data half — the mapping from an action's authority tier to the
environment it is allowed to run inside — so the boundary is stated once,
reviewable, and assertable in tests rather than being re-derived at each
call site.

The policy is consulted in two places:

* when the harness builds an approval card, so the approver sees what
  the environment will permit, not just what the step intends; and
* when a run's sandbox spec is assembled, so the strictest boundary
  demanded by any tier in the plan is the one that is applied.

Enforcement of a per-step boundary (rather than per run) requires
``SandboxLifetime.STEP``; that is the follow-up to per-run sandboxes and
is deliberately not pretended here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agenthub.domain.authority import AuthorityTier
from agenthub.sandbox.spec import NetworkPolicy


@dataclass(frozen=True)
class SandboxBoundary:
    """What the environment permits for one authority tier."""

    network: NetworkPolicy = NetworkPolicy.INHERIT
    allow_exec: bool = True
    allow_write: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "network": self.network.value,
            "may_start_processes": self.allow_exec,
            "may_write_files": self.allow_write,
            "note": self.note,
        }


_READONLY = SandboxBoundary(
    network=NetworkPolicy.INHERIT,
    allow_exec=True,
    allow_write=True,
    note="Reads and generated proposals; nothing is applied to the project.",
)

_REVERSIBLE = SandboxBoundary(
    network=NetworkPolicy.INHERIT,
    allow_exec=True,
    allow_write=True,
    note="Reversible effects, applied only after your approval.",
)

# A local static deployment has no reason to reach the network, so the
# irreversible tier is the one place the default policy tightens egress.
_IRREVERSIBLE = SandboxBoundary(
    network=NetworkPolicy.NONE,
    allow_exec=True,
    allow_write=True,
    note="Irreversible action; no network egress is permitted.",
)


@dataclass(frozen=True)
class SandboxPolicy:
    """Tier → boundary mapping, with a fail-closed default."""

    boundaries: dict[AuthorityTier, SandboxBoundary] = field(
        default_factory=lambda: {
            AuthorityTier.L1_READONLY: _READONLY,
            AuthorityTier.L2_REVERSIBLE: _REVERSIBLE,
            AuthorityTier.L3_IRREVERSIBLE: _IRREVERSIBLE,
        }
    )

    def boundary_for(self, tier: AuthorityTier) -> SandboxBoundary:
        return self.boundaries.get(tier, _IRREVERSIBLE)

    def describe(self, tier: AuthorityTier) -> dict:
        """The boundary as an approval card should present it."""
        return self.boundary_for(tier).to_dict()

    def strictest(self, tiers) -> SandboxBoundary:
        """The tightest boundary demanded by any tier in ``tiers``.

        Used when assembling a run's spec: a plan that contains an L3 step
        is held to the L3 boundary for the whole run rather than only for
        that step.
        """
        present = [tier for tier in tiers if tier in self.boundaries]
        if not present:
            return _IRREVERSIBLE
        if AuthorityTier.L3_IRREVERSIBLE in present:
            return self.boundaries[AuthorityTier.L3_IRREVERSIBLE]
        if AuthorityTier.L2_REVERSIBLE in present:
            return self.boundaries[AuthorityTier.L2_REVERSIBLE]
        return self.boundaries[AuthorityTier.L1_READONLY]
