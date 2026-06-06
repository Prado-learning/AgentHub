from fastapi import APIRouter

from agenthub_harness.config.loader import load_yaml_config


router = APIRouter(tags=["agents"])


AGENT_DESCRIPTIONS = {
    "orchestrator": "Coordinates the multi-agent workflow.",
    "codex": "Handles coding tasks through the Codex adapter.",
    "ui_builder": "Drafts React UI artifacts.",
    "code_reviewer": "Reviews generated code and suggests improvements.",
}


@router.get("/agents")
def list_agents() -> dict[str, list[dict]]:
    try:
        configs = load_yaml_config("app/configs/agent.yaml").get("agents", [])
    except FileNotFoundError:
        configs = []

    return {
        "agents": [
            {
                "id": config["id"],
                "name": config.get("name", config["id"]),
                "description": AGENT_DESCRIPTIONS.get(config["id"], "Custom Agent."),
                "capabilities": config.get("capabilities", []),
            }
            for config in configs
        ]
    }

