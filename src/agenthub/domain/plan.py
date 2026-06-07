from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlanStep:
    id: str
    agent_id: str
    task: str
    tools: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    can_run_parallel: bool = True


@dataclass(frozen=True)
class Plan:
    steps: list[PlanStep]
    reason: str

