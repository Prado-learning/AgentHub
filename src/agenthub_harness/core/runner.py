from dataclasses import dataclass, field

from agenthub_harness.core.context import RunContext
from agenthub_harness.core.events import RunEvent


@dataclass
class HarnessRunner:
    mode: str = "mock"
    events: list[RunEvent] = field(default_factory=list)

    def run(self, context: RunContext) -> dict:
        event = RunEvent(type="run.started", payload={"conversation_id": context.conversation_id})
        self.events.append(event)
        return {
            "status": "queued",
            "conversation_id": context.conversation_id,
            "message": context.message,
        }

