from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from agenthub_harness.core.context import RunContext


@dataclass(frozen=True)
class AgentTask:
    agent_id: str
    instruction: str
    tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentResult:
    agent_id: str
    status: str = "success"
    messages: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None


class AgentAdapter(Protocol):
    id: str
    name: str
    capabilities: list[str]

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        ...

