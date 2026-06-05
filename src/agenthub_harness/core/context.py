from dataclasses import dataclass


@dataclass(frozen=True)
class RunContext:
    conversation_id: str
    message: str
    selected_agents: list[str]

