from __future__ import annotations

from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.adapters.process_adapter import run_cli_agent
from agenthub.domain.run import RunContext


class ClaudeCodeAdapter:
    def __init__(
        self,
        agent_id: str = "claude_code",
        name: str | None = None,
        capabilities: list[str] | None = None,
        skills: list[str] | None = None,
        **_: object,
    ) -> None:
        self.id = agent_id
        self.name = name or "Claude Code"
        self.capabilities = capabilities or ["code", "review", "refactor"]
        self.skills = skills or []

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        return run_cli_agent(
            agent_id=self.id,
            name=self.name,
            task=task,
            context=context,
            env_command_key="CLAUDE_CODE_COMMAND",
            skills=self.skills,
        )
