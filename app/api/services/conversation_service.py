from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.api.services.conversation_store import JsonStore


RUNTIME_DIR = Path("agent-workspace/runtime")
CONVERSATIONS = JsonStore(RUNTIME_DIR / "conversations.json")
MESSAGES = JsonStore(RUNTIME_DIR / "messages.json")


DEFAULT_CONVERSATION_ID = "conv_demo"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_default_conversation() -> None:
    conversations = CONVERSATIONS.read()
    if conversations:
        return

    now = utc_now()
    CONVERSATIONS.write(
        [
            {
                "id": DEFAULT_CONVERSATION_ID,
                "title": "Demo Conversation",
                "mode": "group",
                "agent_ids": ["orchestrator", "ui_builder", "code_reviewer"],
                "is_pinned": False,
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "last_message": "",
            }
        ]
    )
    MESSAGES.write([])


def list_conversations(search: str = "", archived: bool = False) -> list[dict]:
    ensure_default_conversation()
    normalized_search = search.strip().lower()

    conversations = [
        conversation
        for conversation in CONVERSATIONS.read()
        if bool(conversation.get("is_archived")) is archived
    ]

    if normalized_search:
        conversations = [
            conversation
            for conversation in conversations
            if _matches_search(conversation, normalized_search)
        ]

    sorted_conversations = sorted(
        conversations,
        key=lambda conversation: str(conversation.get("updated_at", "")),
        reverse=True,
    )
    return sorted(
        sorted_conversations,
        key=lambda conversation: bool(conversation.get("is_pinned")),
        reverse=True,
    )


def create_conversation(
    title: str | None = None,
    mode: str = "group",
    agent_ids: list[str] | None = None,
) -> dict:
    ensure_default_conversation()
    now = utc_now()
    conversation = {
        "id": f"conv_{uuid4().hex[:12]}",
        "title": title.strip() if title and title.strip() else "New Conversation",
        "mode": mode,
        "agent_ids": agent_ids or ["orchestrator"],
        "is_pinned": False,
        "is_archived": False,
        "created_at": now,
        "updated_at": now,
        "last_message": "",
    }
    conversations = CONVERSATIONS.read()
    conversations.append(conversation)
    CONVERSATIONS.write(conversations)
    return conversation


def get_conversation(conversation_id: str) -> dict | None:
    ensure_default_conversation()
    return next(
        (
            conversation
            for conversation in CONVERSATIONS.read()
            if conversation.get("id") == conversation_id
        ),
        None,
    )


def update_conversation(conversation_id: str, updates: dict) -> dict | None:
    ensure_default_conversation()
    conversations = CONVERSATIONS.read()
    for conversation in conversations:
        if conversation.get("id") != conversation_id:
            continue
        for key in ("title", "mode", "agent_ids"):
            if key in updates and updates[key] is not None:
                conversation[key] = updates[key]
        conversation["updated_at"] = utc_now()
        CONVERSATIONS.write(conversations)
        return conversation
    return None


def set_conversation_pinned(conversation_id: str, is_pinned: bool) -> dict | None:
    return _set_conversation_flag(conversation_id, "is_pinned", is_pinned)


def set_conversation_archived(conversation_id: str, is_archived: bool) -> dict | None:
    return _set_conversation_flag(conversation_id, "is_archived", is_archived)


def list_messages(conversation_id: str) -> list[dict]:
    ensure_default_conversation()
    return [
        message
        for message in MESSAGES.read()
        if message.get("conversation_id") == conversation_id
    ]


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    sender: str | None = None,
    format: str = "markdown",
    artifact_ids: list[str] | None = None,
    quoted_message_id: str | None = None,
    attachment_ids: list[str] | None = None,
) -> dict:
    ensure_default_conversation()
    now = utc_now()
    message = {
        "id": f"msg_{uuid4().hex[:12]}",
        "conversation_id": conversation_id,
        "role": role,
        "sender": sender,
        "content": content,
        "format": format,
        "artifact_ids": artifact_ids or [],
        "quoted_message_id": quoted_message_id,
        "attachment_ids": attachment_ids or [],
        "is_pinned": False,
        "created_at": now,
    }
    messages = MESSAGES.read()
    messages.append(message)
    MESSAGES.write(messages)
    _touch_conversation(conversation_id, content, now)
    return message


def _matches_search(conversation: dict, normalized_search: str) -> bool:
    fields = [
        str(conversation.get("title", "")),
        str(conversation.get("last_message", "")),
        " ".join(conversation.get("agent_ids", [])),
    ]
    return any(normalized_search in field.lower() for field in fields)


def _set_conversation_flag(
    conversation_id: str,
    field: str,
    value: bool,
) -> dict | None:
    ensure_default_conversation()
    conversations = CONVERSATIONS.read()
    for conversation in conversations:
        if conversation.get("id") != conversation_id:
            continue
        conversation[field] = value
        conversation["updated_at"] = utc_now()
        CONVERSATIONS.write(conversations)
        return conversation
    return None


def _touch_conversation(conversation_id: str, last_message: str, updated_at: str) -> None:
    conversations = CONVERSATIONS.read()
    for conversation in conversations:
        if conversation.get("id") == conversation_id:
            conversation["last_message"] = _summarize_message(last_message)
            conversation["updated_at"] = updated_at
            CONVERSATIONS.write(conversations)
            return


def set_message_pinned(
    conversation_id: str,
    message_id: str,
    is_pinned: bool,
) -> dict | None:
    ensure_default_conversation()
    messages = MESSAGES.read()
    for message in messages:
        if (
            message.get("conversation_id") == conversation_id
            and message.get("id") == message_id
        ):
            message["is_pinned"] = is_pinned
            MESSAGES.write(messages)
            return message
    return None


def list_pinned_messages(conversation_id: str) -> list[dict]:
    return [
        message
        for message in list_messages(conversation_id)
        if bool(message.get("is_pinned"))
    ]


def _summarize_message(content: str, limit: int = 96) -> str:
    text = re.sub(r"```[\s\S]*?```", " code block ", content)
    text = re.sub(r"[*_#>`~-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
