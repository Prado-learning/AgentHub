from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    name: str
    description: str = ""
    permissions: list[str] = field(default_factory=list)

