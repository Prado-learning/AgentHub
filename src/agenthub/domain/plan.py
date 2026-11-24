from __future__ import annotations

from dataclasses import dataclass, field

from agenthub.domain.authority import AuthorityTier


@dataclass(frozen=True)
class PlanStep:
    id: str
    agent_id: str
    task: str
    tools: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    can_run_parallel: bool = True
    authority: AuthorityTier = AuthorityTier.L1_READONLY
    can_short_circuit: bool = False
    kind: str = "agent"
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    steps: list[PlanStep]
    reason: str
