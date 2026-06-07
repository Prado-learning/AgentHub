from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    id: str
    type: str
    title: str
    content: str
    language: str | None = None
    preview_url: str | None = None
    preview_html: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


