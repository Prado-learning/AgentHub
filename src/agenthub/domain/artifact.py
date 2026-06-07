from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Artifact:
    id: str
    type: str
    title: str
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

