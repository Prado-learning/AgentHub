from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.services.chat_service import build_mock_chat_response


router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "agent", "system"]
    content: str
    format: str = "markdown"


class ChatRequest(BaseModel):
    conversation_id: str
    message: ChatMessage
    selected_agents: list[str] = []


@router.post("/chat")
def chat(request: ChatRequest) -> dict:
    return build_mock_chat_response(request.model_dump())

