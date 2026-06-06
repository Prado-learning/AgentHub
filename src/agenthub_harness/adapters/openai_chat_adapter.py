from __future__ import annotations

from agenthub_harness.adapters.base import AgentResult, AgentTask
from agenthub_harness.core.context import RunContext
from agenthub_harness.llm.openai_compatible_provider import OpenAICompatibleProvider


class OpenAIChatAdapter:
    def __init__(
        self,
        agent_id: str,
        name: str | None = None,
        model: str = "mock",
        capabilities: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> None:
        self.id = agent_id
        self.name = name or agent_id.replace("_", " ").title()
        self.capabilities = capabilities or ["text"]
        self.skills = skills or []
        self.provider = OpenAICompatibleProvider(model=model)

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        prompt = self._build_prompt(task, context)
        try:
            content = self.provider.complete(prompt)
        except Exception as exc:
            return AgentResult(
                agent_id=self.id,
                status="error",
                messages=[
                    {
                        "role": "agent",
                        "sender": self.id,
                        "content": f"LLM call failed: {exc}",
                        "format": "markdown",
                    }
                ],
                error=str(exc),
            )
        return AgentResult(
            agent_id=self.id,
            messages=[
                {
                    "role": "agent",
                    "sender": self.id,
                    "content": content,
                    "format": "markdown",
                }
            ],
            artifacts=self._build_artifacts(content),
        )

    def _build_artifacts(self, content: str) -> list[dict]:
        if self.id == "ui_builder":
            return [
                {
                    "id": "art_001",
                    "type": "code",
                    "title": "Generated UI Code",
                    "language": "tsx",
                    "file_path": "GeneratedUI.tsx",
                    "content": content,
                },
            ]
        return []

    def _build_prompt(self, task: AgentTask, context: RunContext) -> str:
        history = "\n".join(
            f"{item.get('sender') or item.get('role')}: {item.get('content')}"
            for item in context.history[-6:]
        )
        return (
            f"You are {self.name}.\n"
            f"Conversation mode: {context.mode}\n"
            f"Agent skills:\n{self._format_skills()}\n\n"
            f"Recent history:\n{history}\n\n"
            f"Current task:\n{task.instruction}"
        )

    def _format_skills(self) -> str:
        if not self.skills:
            return "No extra skills configured."
        return "\n\n".join(self.skills)
