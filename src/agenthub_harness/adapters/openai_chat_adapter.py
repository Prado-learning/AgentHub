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
        api_key: str | None = None,
        base_url: str | None = None,
        capabilities: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> None:
        self.id = agent_id
        self.name = name or agent_id.replace("_", " ").title()
        self.capabilities = capabilities or ["text"]
        self.skills = skills or []
        self.provider = OpenAICompatibleProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        prompt = self._build_prompt(task, context)
        try:
            if "vision" in self.capabilities:
                content = self.provider.complete_with_attachments(prompt, context.attachments or [])
            else:
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
            f"Pinned long-term context:\n{self._format_pinned_context(context)}\n\n"
            f"Current attachments:\n{self._format_attachments(context)}\n\n"
            f"Recent history:\n{history}\n\n"
            f"Current task:\n{task.instruction}"
        )

    def _format_skills(self) -> str:
        if not self.skills:
            return "No extra skills configured."
        return "\n\n".join(self.skills)

    def _format_pinned_context(self, context: RunContext) -> str:
        if not context.pinned_context:
            return "No pinned context."
        return "\n".join(
            f"- {item.get('sender') or item.get('role')}: {item.get('content')}"
            for item in context.pinned_context
        )

    def _format_attachments(self, context: RunContext) -> str:
        if not context.attachments:
            return "No attachments."
        sections: list[str] = []
        for attachment in context.attachments:
            extracted = str(attachment.get("extracted_text") or "").strip()
            preview = extracted[:3000] if extracted else "No extracted text."
            sections.append(
                f"- {attachment.get('filename')} ({attachment.get('mime_type')}):\n{preview}"
            )
        return "\n\n".join(sections)
