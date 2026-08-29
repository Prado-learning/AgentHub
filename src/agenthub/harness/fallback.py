"""Fallback strategy when a primary agent adapter fails."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agenthub.adapters.base import AgentAdapter, AgentResult, AgentTask
from agenthub.adapters.mock.adapter import MockAgentAdapter
from agenthub.domain.run import RunContext


def _default_fallback_factories() -> list[Callable[[str], AgentAdapter]]:
    return [
        lambda agent_id: MockAgentAdapter(agent_id=agent_id, name=f"{agent_id} fallback")
    ]


@dataclass
class FallbackChain:
    """Tries fallback adapters in order when a primary adapter fails.

    The default chain degrades to a mock agent so a run can still finish
    with a usable response when the configured provider is unavailable.
    Append additional factories to try another real provider first.
    """

    adapter_factories: list[Callable[[str], AgentAdapter]] = field(
        default_factory=_default_fallback_factories
    )

    def run(
        self,
        agent_id: str,
        task: AgentTask,
        context: RunContext,
        reason: str,
    ) -> AgentResult | None:
        """Run the fallback adapters for one failed step.

        Returns the first successful result with a note about the fallback
        prefixed to its messages, or ``None`` when every fallback also fails
        so the caller keeps the original failure.
        """
        note = {
            "role": "agent",
            "sender": agent_id,
            "content": f"Primary adapter failed, used fallback. Reason: {reason}",
            "format": "markdown",
        }
        for factory in self.adapter_factories:
            adapter = factory(agent_id)
            try:
                result = adapter.run(task, context)
            except Exception:
                continue
            if result.status == "success":
                return AgentResult(
                    agent_id=agent_id,
                    status="success",
                    messages=[note, *result.messages],
                    artifacts=result.artifacts,
                )
        return None
