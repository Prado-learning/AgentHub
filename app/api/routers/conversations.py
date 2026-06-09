from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.services.conversation_service import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    list_messages,
    list_pinned_messages,
    set_conversation_archived,
    set_conversation_pinned,
    set_conversation_trashed,
    set_message_pinned,
    update_conversation,
)
from app.api.services.memory_service import (
    delete_memory,
    extract_memories_with_llm,
    list_memories,
)


router = APIRouter(tags=["conversations"])


class ConversationCreateRequest(BaseModel):
    title: str | None = None
    mode: Literal["single", "group"] = "group"
    agent_ids: list[str] = Field(default_factory=lambda: ["orchestrator"])


class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    mode: Literal["single", "group"] | None = None
    agent_ids: list[str] | None = None


class MemoryExtractRequest(BaseModel):
    model_provider: str | None = None
    model_name: str | None = None


@router.get("/conversations")
def read_conversations(
    search: str = "",
    archived: bool = Query(False),
    trashed: bool = Query(False),
) -> dict[str, list[dict]]:
    return {
        "conversations": list_conversations(
            search=search,
            archived=archived,
            trashed=trashed,
        )
    }


@router.post("/conversations")
def create_new_conversation(request: ConversationCreateRequest) -> dict:
    return {
        "conversation": create_conversation(
            title=request.title,
            mode=request.mode,
            agent_ids=request.agent_ids,
        )
    }


@router.patch("/conversations/{conversation_id}")
def patch_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
) -> dict:
    conversation = update_conversation(
        conversation_id,
        request.model_dump(exclude_unset=True),
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.patch("/conversations/{conversation_id}/pin")
def pin_conversation(conversation_id: str) -> dict:
    conversation = set_conversation_pinned(conversation_id, True)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.patch("/conversations/{conversation_id}/unpin")
def unpin_conversation(conversation_id: str) -> dict:
    conversation = set_conversation_pinned(conversation_id, False)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.patch("/conversations/{conversation_id}/archive")
def archive_conversation(conversation_id: str) -> dict:
    conversation = set_conversation_archived(conversation_id, True)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.patch("/conversations/{conversation_id}/unarchive")
def unarchive_conversation(conversation_id: str) -> dict:
    conversation = set_conversation_archived(conversation_id, False)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.patch("/conversations/{conversation_id}/trash")
def trash_conversation(conversation_id: str) -> dict:
    conversation = set_conversation_trashed(conversation_id, True)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.patch("/conversations/{conversation_id}/restore")
def restore_conversation(conversation_id: str) -> dict:
    conversation = set_conversation_trashed(conversation_id, False)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.delete("/conversations/{conversation_id}")
def remove_conversation(conversation_id: str) -> dict:
    conversation = delete_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@router.get("/conversations/{conversation_id}/messages")
def read_conversation_messages(conversation_id: str) -> dict[str, list[dict]]:
    if get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"messages": list_messages(conversation_id)}


@router.get("/conversations/{conversation_id}/pinned-messages")
def read_pinned_messages(conversation_id: str) -> dict[str, list[dict]]:
    if get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"messages": list_pinned_messages(conversation_id)}


@router.patch("/conversations/{conversation_id}/messages/{message_id}/pin")
def pin_message(conversation_id: str, message_id: str) -> dict:
    message = set_message_pinned(conversation_id, message_id, True)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message": message}


@router.patch("/conversations/{conversation_id}/messages/{message_id}/unpin")
def unpin_message(conversation_id: str, message_id: str) -> dict:
    message = set_message_pinned(conversation_id, message_id, False)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message": message}


@router.get("/conversations/{conversation_id}/memories")
def read_memories(conversation_id: str) -> dict[str, list[dict]]:
    if get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"memories": list_memories(conversation_id)}


@router.post("/conversations/{conversation_id}/messages/{message_id}/extract-memory")
def extract_message_memory(
    conversation_id: str,
    message_id: str,
    request: MemoryExtractRequest,
) -> dict[str, list[dict]]:
    messages = list_messages(conversation_id)
    message = next((item for item in messages if item.get("id") == message_id), None)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    try:
        memories = extract_memories_with_llm(
            conversation_id,
            message,
            messages,
            model_provider=request.model_provider,
            model_name=request.model_name,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"memories": memories}


@router.delete("/conversations/{conversation_id}/memories/{memory_id}")
def remove_memory(conversation_id: str, memory_id: str) -> dict:
    memory = delete_memory(conversation_id, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"memory": memory}
