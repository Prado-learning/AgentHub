from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.services.chat_service import build_chat_response


router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "agent", "system"]
    content: str
    format: str = "markdown"
    quoted_message_id: str | None = None


class ChatRequest(BaseModel):
    conversation_id: str
    message: ChatMessage
    selected_agents: list[str] = []


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

