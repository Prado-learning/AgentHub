from __future__ import annotations

from agenthub.domain.run import RunContext


class AgentContextBuilder:
    def build_prompt_sections(self, context: RunContext) -> dict[str, object]:
        return {
            "history": context.history[-8:],
            "pinned_context": context.pinned_context or [],
            "attachments": context.attachments or [],
            "workspace_dir": context.workspace_dir,
        }

