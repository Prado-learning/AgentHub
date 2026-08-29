"""Run limits enforced by the HarnessRunner scheduling loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from agenthub.policies import RunPolicy


@dataclass
class RunLimits:
    """Safety net bounds for one multi-agent run.

    ``max_steps`` caps how many plan steps a single run may execute; planners
    already bound their own plans, so this limit only kicks in for plans that
    grew past it (e.g. a misbehaving planner response).
    """

    max_parallel_steps: int = 4
    run_policy: RunPolicy = field(default_factory=lambda: RunPolicy(max_steps=12))

    def allows_step(self, executed_steps: int) -> bool:
        return self.run_policy.allows_step(executed_steps)
