from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    path: str
    description: str = ""

