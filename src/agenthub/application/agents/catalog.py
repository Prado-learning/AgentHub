from __future__ import annotations

from agenthub.application.agents.definition_loader import load_agent_configs


class AgentCatalog:
    def list_agents(self) -> list[dict]:
        return [
            {
                "id": config["id"],
                "name": config.get("name", config["id"]),
                "description": config.get("description", "Custom Agent."),
                "capabilities": config.get("capabilities", []),
                "tools": config.get("tools", []),
                "skills": config.get("skills", []),
                "system_prompt": config.get("system_prompt"),
                "model_provider": config.get("model_provider"),
                "model_name": config.get("model_name"),
                "avatar": config.get("avatar"),
                "is_custom": bool(config.get("is_custom")),
            }
            for config in load_agent_configs()
        ]

