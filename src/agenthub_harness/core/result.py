from dataclasses import dataclass, field

from agenthub_harness.core.events import RunEvent


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    conversation_id: str
    messages: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)
