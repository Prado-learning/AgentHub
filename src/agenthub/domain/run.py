from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass(frozen=True)
class RunContext:
    conversation_id: str
    message: str
    history: list[dict]
    selected_agents: list[str]
    mode: Literal["single", "group"] = "group"
    pinned_context: list[dict] | None = None
    conversation_memories: list[dict] | None = None
    conversation_summary: dict | None = None
    attachments: list[dict] | None = None
    tool_preferences: dict | None = None
    workspace_dir: str = "agent-workspace"
    upstream_artifacts: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class RunEvent:
    type: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    conversation_id: str
    messages: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)
    debug_trace: list["StageTrace"] = field(default_factory=list)
    checkpoint: dict = field(default_factory=dict)


# Imported at module bottom to keep the public surface flat and avoid a
# circular import if the trace module ever needs to reference RunEvent.
from agenthub.domain.trace import StageTrace  # noqa: E402
