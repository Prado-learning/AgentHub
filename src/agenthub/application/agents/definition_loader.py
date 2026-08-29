from __future__ import annotations

from dataclasses import asdict

from app.api.services.agent_service import list_custom_agents
from agenthub.domain.agent import AgentDefinition
from agenthub.infrastructure.config.loader import load_yaml_config


def load_agent_configs() -> list[dict]:
    """Load builtin (YAML) and custom (runtime store) agent configs.

    Every entry is round-tripped through the ``AgentDefinition`` domain model
    so required fields are validated and defaults normalized; unknown extra
    keys (e.g. ``is_custom``) are preserved on top of the modelled fields.
    """
    return [_normalized_config(item) for item in _raw_agent_configs()]


def load_agent_definitions() -> list[AgentDefinition]:
    """Typed view over the same configs as ``load_agent_configs``."""
    return [
        AgentDefinition(
            id=str(item["id"]),
            name=str(item.get("name") or item["id"]),
            adapter=str(item.get("adapter") or "openai_chat"),
            description=str(item.get("description") or ""),
            kind=str(item.get("kind") or "builtin"),
            capabilities=list(item.get("capabilities") or []),
            tools=list(item.get("tools") or []),
            skills=list(item.get("skills") or []),
            system_prompt=str(item.get("system_prompt") or ""),
            model_provider=item.get("model_provider") or None,
            model_name=item.get("model_name") or None,
            avatar=item.get("avatar") or None,
        )
        for item in load_agent_configs()
    ]


def _raw_agent_configs() -> list[dict]:
    builtin_agents: list[dict] = []
    for path in ("app/configs/agents.yaml", "app/configs/agent.yaml"):
        try:
            builtin_agents = load_yaml_config(path).get("agents", [])
            break
        except FileNotFoundError:
            continue
    return [*builtin_agents, *list_custom_agents()]


def _normalized_config(item: dict) -> dict:
    agent_id = str(item.get("id") or "").strip()
    if not agent_id:
        raise ValueError(f"Agent definition requires a non-empty id: {item!r}")
    definition = AgentDefinition(
        id=agent_id,
        name=str(item.get("name") or agent_id),
        adapter=str(item.get("adapter") or "openai_chat"),
        description=str(item.get("description") or ""),
        kind=str(item.get("type") or "builtin"),
        capabilities=_string_list(item.get("capabilities")),
        tools=_string_list(item.get("tools")),
        skills=_string_list(item.get("skills")),
        system_prompt=str(item.get("system_prompt") or ""),
        model_provider=item.get("model_provider") or None,
        model_name=item.get("model_name") or None,
        avatar=item.get("avatar") or None,
    )
    config = asdict(definition)
    config.update({key: value for key, value in item.items() if key not in config})
    return config


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]
