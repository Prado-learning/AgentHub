from dataclasses import dataclass


@dataclass(frozen=True)
class ToolResult:
    id: str
    type: str
    title: str
    content: str

