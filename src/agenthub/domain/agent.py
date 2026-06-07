from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


AgentKind = Literal["system", "external_agent", "custom", "builtin"]


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    adapter: str
    description: str = ""
    kind: AgentKind = "builtin"
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    model_provider: str | None = None
    model_name: str | None = None

