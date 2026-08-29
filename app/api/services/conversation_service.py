from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.api.services.conversation_store import JsonStore, transaction


RUNTIME_DIR = Path("agent-workspace/runtime")
CONVERSATIONS = JsonStore(RUNTIME_DIR / "conversations.json")
MESSAGES = JsonStore(RUNTIME_DIR / "messages.json")


DEFAULT_CONVERSATION_ID = "conv_demo"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_default_conversation() -> None:
    seeded = False

    def _seed(records: list[dict]) -> list[dict] | None:
        nonlocal seeded
        if records:
            return None
        seeded = True
        now = utc_now()
        return [
            {
                "id": DEFAULT_CONVERSATION_ID,
                "title": "Demo Conversation",
                "mode": "group",
                "agent_ids": ["orchestrator", "ui_builder", "code_reviewer"],
                "is_pinned": False,
                "is_archived": False,
                "is_trashed": False,
                "created_at": now,
                "updated_at": now,
                "last_message": "",
            }
        ]

    CONVERSATIONS.update(_seed)
    if seeded:
        MESSAGES.write([])


def list_conversations(
    search: str = "",
    archived: bool = False,
    trashed: bool = False,
) -> list[dict]:
    ensure_default_conversation()
    normalized_search = search.strip().lower()

    if trashed:
        conversations = [
            conversation
            for conversation in CONVERSATIONS.read()
            if bool(conversation.get("is_trashed"))
        ]
    else:
        conversations = [
            conversation
            for conversation in CONVERSATIONS.read()
            if not bool(conversation.get("is_trashed"))
            and bool(conversation.get("is_archived")) is archived
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
        "is_trashed": False,
        "created_at": now,
        "updated_at": now,
        "last_message": "",
    }
    CONVERSATIONS.update(lambda records: [*records, conversation])
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
    updated: dict | None = None

    def _mutate(records: list[dict]) -> list[dict] | None:
        nonlocal updated
        for conversation in records:
            if conversation.get("id") != conversation_id:
                continue
            for key in ("title", "mode", "agent_ids"):
                if key in updates and updates[key] is not None:
                    conversation[key] = updates[key]
            conversation["updated_at"] = utc_now()
            updated = conversation
            return records
        return None

    CONVERSATIONS.update(_mutate)
    return updated


def set_conversation_pinned(conversation_id: str, is_pinned: bool) -> dict | None:
    return _set_conversation_flag(conversation_id, "is_pinned", is_pinned)


def set_conversation_archived(conversation_id: str, is_archived: bool) -> dict | None:
    return _set_conversation_flag(conversation_id, "is_archived", is_archived)


def set_conversation_trashed(conversation_id: str, is_trashed: bool) -> dict | None:
    return _set_conversation_flag(conversation_id, "is_trashed", is_trashed)


def delete_conversation(conversation_id: str) -> dict | None:
    ensure_default_conversation()
    deleted: dict | None = None

    def _remove_conversation(records: list[dict]) -> list[dict] | None:
        nonlocal deleted
        remaining = [
            conversation
            for conversation in records
            if conversation.get("id") != conversation_id
        ]
        if len(remaining) == len(records):
            return None
        deleted = next(
            conversation
            for conversation in records
            if conversation.get("id") == conversation_id
        )
        return remaining

    def _remove_messages(records: list[dict]) -> list[dict] | None:
        remaining = [
            message
            for message in records
            if message.get("conversation_id") != conversation_id
        ]
        return remaining if len(remaining) != len(records) else None

    with transaction(MESSAGES, CONVERSATIONS):
        CONVERSATIONS.update(_remove_conversation)
        if deleted is not None:
            MESSAGES.update(_remove_messages)
    return deleted


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
    quoted_text: str | None = None,
    quoted_artifact_id: str | None = None,
    quoted_range: dict | None = None,
    attachment_ids: list[str] | None = None,
    generation_group_id: str | None = None,
    generation_index: int | None = None,
    replaces_message_ids: list[str] | None = None,
    is_active_generation: bool = True,
    trace_events: list[dict] | None = None,
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
        "quoted_text": quoted_text,
        "quoted_artifact_id": quoted_artifact_id,
        "quoted_range": quoted_range,
        "attachment_ids": attachment_ids or [],
        "generation_group_id": generation_group_id,
        "generation_index": generation_index,
        "replaces_message_ids": replaces_message_ids or [],
        "is_active_generation": is_active_generation,
        "is_pinned": False,
        "trace_events": trace_events or [],
        "created_at": now,
    }
    with transaction(MESSAGES, CONVERSATIONS):
        MESSAGES.update(lambda records: [*records, message])
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
    updated: dict | None = None

    def _mutate(records: list[dict]) -> list[dict] | None:
        nonlocal updated
        for conversation in records:
            if conversation.get("id") != conversation_id:
                continue
            conversation[field] = value
            conversation["updated_at"] = utc_now()
            updated = conversation
            return records
        return None

    CONVERSATIONS.update(_mutate)
    return updated


def _touch_conversation(conversation_id: str, last_message: str, updated_at: str) -> None:
    def _mutate(records: list[dict]) -> list[dict] | None:
        for conversation in records:
            if conversation.get("id") == conversation_id:
                conversation["last_message"] = _summarize_message(last_message)
                conversation["updated_at"] = updated_at
                return records
        return None

    CONVERSATIONS.update(_mutate)


def set_message_pinned(
    conversation_id: str,
    message_id: str,
    is_pinned: bool,
) -> dict | None:
    ensure_default_conversation()
    updated: dict | None = None

    def _mutate(records: list[dict]) -> list[dict] | None:
        nonlocal updated
        for message in records:
            if (
                message.get("conversation_id") == conversation_id
                and message.get("id") == message_id
            ):
                message["is_pinned"] = is_pinned
                updated = message
                return records
        return None

    MESSAGES.update(_mutate)
    return updated


def list_pinned_messages(conversation_id: str) -> list[dict]:
    return [
        message
        for message in list_messages(conversation_id)
        if bool(message.get("is_pinned"))
    ]


def deactivate_generation_group(conversation_id: str, generation_group_id: str) -> list[str]:
    replaced: list[str] = []

    def _mutate(records: list[dict]) -> list[dict] | None:
        changed = False
        for message in records:
            if (
                message.get("conversation_id") == conversation_id
                and message.get("generation_group_id") == generation_group_id
                and message.get("role") == "agent"
                and message.get("is_active_generation", True)
            ):
                message["is_active_generation"] = False
                replaced.append(str(message.get("id")))
                changed = True
        return records if changed else None

    MESSAGES.update(_mutate)
    return replaced


def next_generation_index(conversation_id: str, generation_group_id: str) -> int:
    indexes = [
        int(message.get("generation_index") or 0)
        for message in list_messages(conversation_id)
        if message.get("generation_group_id") == generation_group_id
    ]
    return (max(indexes) if indexes else 0) + 1


def _summarize_message(content: str, limit: int = 96) -> str:
    text = re.sub(r"```[\s\S]*?```", " code block ", content)
    text = re.sub(r"[*_#>`~-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
