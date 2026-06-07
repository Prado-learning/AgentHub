from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    mode: str = "group"
    agent_ids: list[str] = field(default_factory=list)

