from __future__ import annotations

from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.adapters.process_adapter import run_cli_agent
from agenthub.domain.run import RunContext


class OpenCodeAdapter:
    def __init__(
        self,
        agent_id: str = "opencode",
        name: str | None = None,
        capabilities: list[str] | None = None,
        skills: list[str] | None = None,
        **_: object,
    ) -> None:
        self.id = agent_id
        self.name = name or "OpenCode"
        self.capabilities = capabilities or ["code", "review", "refactor"]
        self.skills = skills or []

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        return run_cli_agent(
            agent_id=self.id,
            name=self.name,
            task=task,
            context=context,
            env_command_key="OPENCODE_COMMAND",
            skills=self.skills,
        )
