from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.services.chat_service import build_chat_response


router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "agent", "system"]
    content: str
    format: str = "markdown"
    quoted_message_id: str | None = None
    quoted_text: str | None = None
    quoted_artifact_id: str | None = None
    quoted_range: dict | None = None
    attachment_ids: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    conversation_id: str
    message: ChatMessage
    selected_agents: list[str] = []
    model_provider: str | None = None
    model_name: str | None = None
    agent_mode: Literal["single", "multi"] | None = None
    tool_preferences: dict[str, bool] = Field(default_factory=dict)
    regenerate_from_message_id: str | None = None


@router.post("/chat")
def chat(request: ChatRequest) -> dict:
    try:
        return build_chat_response(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/chat/regenerate")
def regenerate_chat(request: ChatRequest) -> dict:
    try:
        return build_chat_response(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


