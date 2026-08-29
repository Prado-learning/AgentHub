"""Permission checks gating which tools an agent may execute."""

from __future__ import annotations

from agenthub.application.agents.runtime_profile import AgentRuntimeProfile
from agenthub.policies import ToolPolicy


def tool_policy_for(profile: AgentRuntimeProfile | None) -> ToolPolicy:
    """Build the tool allow-list for one agent.

    Agents without a runtime profile, or with an empty tool list, are denied
    every tool; only explicitly configured tools may run.
    """
    return ToolPolicy(allowed_tools=list(profile.tools) if profile else [])


def ensure_tool_allowed(agent_id: str, tool_id: str, policy: ToolPolicy) -> None:
    if not policy.allows(tool_id):
        raise PermissionError(f"Agent {agent_id} is not allowed to use tool {tool_id}")
