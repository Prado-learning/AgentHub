from __future__ import annotations

from app.api.services.agent_service import list_custom_agents
from agenthub.infrastructure.config.loader import load_yaml_config


def load_agent_configs() -> list[dict]:
    builtin_agents: list[dict] = []
    for path in ("app/configs/agents.yaml", "app/configs/agent.yaml"):
        try:
            builtin_agents = load_yaml_config(path).get("agents", [])
            break
        except FileNotFoundError:
            continue
    return [*builtin_agents, *list_custom_agents()]

