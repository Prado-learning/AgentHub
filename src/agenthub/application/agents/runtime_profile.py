from __future__ import annotations

from dataclasses import dataclass, field

from agenthub.application.agents.definition_loader import load_agent_configs


@dataclass(frozen=True)
class AgentRuntimeProfile:
    id: str
    name: str
    adapter: str
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    system_prompt: str = ""
    model_provider: str | None = None
    model_name: str | None = None


def load_agent_runtime_profiles() -> dict[str, AgentRuntimeProfile]:
    profiles: dict[str, AgentRuntimeProfile] = {}
    for config in load_agent_configs():
        agent_id = str(config.get("id") or "").strip()
        if not agent_id:
            continue
        profiles[agent_id] = AgentRuntimeProfile(
            id=agent_id,
            name=str(config.get("name") or agent_id),
            adapter=str(config.get("adapter") or "openai_chat"),
            capabilities=_string_list(config.get("capabilities")),
            tools=_string_list(config.get("tools")),
            skills=_string_list(config.get("skills")),
            system_prompt=str(config.get("system_prompt") or ""),
            model_provider=config.get("model_provider") or None,
            model_name=config.get("model_name") or None,
        )
    return profiles


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
