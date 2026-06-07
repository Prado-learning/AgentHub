from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.services.agent_service import (
    create_custom_agent,
    delete_custom_agent,
    update_custom_agent,
)
from agenthub.application.agents.catalog import AgentCatalog
from agenthub.application.tools.catalog import ToolCatalog
from agenthub.infrastructure.config.models import list_model_options


router = APIRouter(tags=["agents"])


class AgentWriteRequest(BaseModel):
    id: str | None = None
    name: str | None = None
    description: str = ""
    system_prompt: str = ""
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    model_provider: str | None = None
    model_name: str | None = None
    avatar: str | None = None


@router.get("/agents")
def list_agents() -> dict[str, list[dict]]:
    return {"agents": AgentCatalog().list_agents()}


@router.post("/agents")
def create_agent(request: AgentWriteRequest) -> dict:
    return {"agent": create_custom_agent(request.model_dump())}


@router.patch("/agents/{agent_id}")
def update_agent(agent_id: str, request: AgentWriteRequest) -> dict:
    agent = update_custom_agent(agent_id, request.model_dump(exclude_unset=True))
    if agent is None:
        raise HTTPException(status_code=404, detail="Custom agent not found")
    return {"agent": agent}


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str) -> dict[str, bool]:
    if not delete_custom_agent(agent_id):
        raise HTTPException(status_code=404, detail="Custom agent not found")
    return {"deleted": True}


@router.get("/models")
def list_models() -> dict[str, list[dict]]:
    return {"models": list_model_options()}


@router.get("/tools")
def list_tools() -> dict[str, list[dict]]:
    return {"tools": ToolCatalog().list_tools()}
