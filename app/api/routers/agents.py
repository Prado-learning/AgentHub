from fastapi import APIRouter

from agenthub_harness.config.loader import load_yaml_config
from agenthub_harness.config.models import list_model_options


router = APIRouter(tags=["agents"])


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
                "description": config.get("description", "Custom Agent."),
                "capabilities": config.get("capabilities", []),
                "tools": config.get("tools", []),
                "skills": config.get("skills", []),
                "model_provider": config.get("model_provider"),
                "model_name": config.get("model_name"),
            }
            for config in configs
        ]
    }


@router.get("/models")
def list_models() -> dict[str, list[dict]]:
    return {"models": list_model_options()}


@router.get("/tools")
def list_tools() -> dict[str, list[dict]]:
    try:
        tools = load_yaml_config("app/configs/tools.yaml").get("tools", [])
    except FileNotFoundError:
        tools = []
    return {"tools": tools}

