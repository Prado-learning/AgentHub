from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Message:
    id: str
    conversation_id: str
    role: str
    content: str
    sender: str | None = None
    format: str = "markdown"
    artifact_ids: list[str] = field(default_factory=list)
    attachment_ids: list[str] = field(default_factory=list)

