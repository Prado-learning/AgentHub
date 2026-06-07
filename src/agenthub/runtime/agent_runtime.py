from __future__ import annotations

from agenthub.adapters.base import AgentAdapter, AgentResult, AgentTask
from agenthub.domain.run import RunContext


class AgentRuntime:
    """Executes one AgentDefinition through one adapter.

    Today adapters perform a single model call. This class is the stable place
    for evolving into a full agent loop with model-native tool calls.
    """

    def __init__(self, adapter: AgentAdapter) -> None:
        self.adapter = adapter

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        return self.adapter.run(task, context)

