from __future__ import annotations

from agenthub_harness.adapters.base import AgentResult, AgentTask
from agenthub_harness.core.context import RunContext


class MockAgentAdapter:
    def __init__(
        self,
        agent_id: str,
        name: str | None = None,
        capabilities: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> None:
        self.id = agent_id
        self.name = name or agent_id.replace("_", " ").title()
        self.capabilities = capabilities or []
        self.skills = skills or []

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        content = self._build_content(task, context)
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
            artifacts=self._build_artifacts() if self.id == "ui_builder" else [],
        )

    def _build_content(self, task: AgentTask, context: RunContext) -> str:
        if self.id == "orchestrator":
            return f"I planned the workflow for: {context.message}"
        if self.id == "ui_builder":
            return "I generated a TodoList React component."
        if self.id == "code_reviewer":
            return "The code is clear; add empty states and validation later."
        return f"{self.name} received task: {task.instruction}"

    def _build_artifacts(self) -> list[dict]:
        if self.id == "ui_builder":
            return [
                {
                    "id": "art_001",
                    "type": "code",
                    "title": "TodoList.tsx",
                    "language": "tsx",
                    "file_path": "TodoList.tsx",
                    "content": (
                        "export default function TodoList() { "
                        "return <div>Todo List</div>; "
                        "}"
                    ),
                },
            ]
        return []
