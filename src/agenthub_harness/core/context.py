from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RunContext:
    conversation_id: str
    message: str
    history: list[dict]
    selected_agents: list[str]
    mode: Literal["single", "group"] = "group"
    pinned_context: list[dict] | None = None
    workspace_dir: str = "agent-workspace"

