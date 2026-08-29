from __future__ import annotations

import re
from pathlib import Path

from app.api.services.conversation_store import JsonStore


RUNTIME_DIR = Path("agent-workspace/runtime")
CUSTOM_AGENTS = JsonStore(RUNTIME_DIR / "custom_agents.json")


def list_custom_agents() -> list[dict]:
    return CUSTOM_AGENTS.read()


def get_custom_agent(agent_id: str) -> dict | None:
    return next(
        (agent for agent in CUSTOM_AGENTS.read() if agent.get("id") == agent_id),
        None,
    )


def create_custom_agent(payload: dict) -> dict:
    base_id = _normalize_agent_id(payload.get("id") or payload.get("name") or "custom_agent")
    created: dict | None = None

    def _mutate(records: list[dict]) -> list[dict]:
        nonlocal created
        existing_ids = {str(agent.get("id")) for agent in records}
        agent_id = base_id
        suffix = 2
        while agent_id in existing_ids:
            agent_id = f"{base_id}_{suffix}"
            suffix += 1
        created = _normalize_agent_payload({**payload, "id": agent_id})
        return [*records, created]

    CUSTOM_AGENTS.update(_mutate)
    assert created is not None
    return created


def update_custom_agent(agent_id: str, payload: dict) -> dict | None:
    updated: dict | None = None

    def _mutate(records: list[dict]) -> list[dict] | None:
        nonlocal updated
        for agent in records:
            if agent.get("id") != agent_id:
                continue
            updates = {key: value for key, value in payload.items() if value is not None}
            agent.update(_normalize_agent_payload({**agent, **updates}, keep_id=True))
            updated = agent
            return records
        return None

    CUSTOM_AGENTS.update(_mutate)
    return updated


def delete_custom_agent(agent_id: str) -> bool:
    deleted = False

    def _mutate(records: list[dict]) -> list[dict] | None:
        nonlocal deleted
        remaining = [agent for agent in records if agent.get("id") != agent_id]
        if len(remaining) == len(records):
            return None
        deleted = True
        return remaining

    CUSTOM_AGENTS.update(_mutate)
    return deleted


def _normalize_agent_payload(payload: dict, keep_id: bool = False) -> dict:
    agent_id = str(payload.get("id") or "custom_agent")
    if not keep_id:
        agent_id = _normalize_agent_id(agent_id)
    return {
        "id": agent_id,
        "name": str(payload.get("name") or agent_id.replace("_", " ").title()),
        "description": str(payload.get("description") or "User-created custom Agent."),
        "type": "custom",
        "adapter": str(payload.get("adapter") or "openai_chat"),
        "system_prompt": str(payload.get("system_prompt") or ""),
        "capabilities": _string_list(payload.get("capabilities")) or ["text"],
        "tools": _string_list(payload.get("tools")),
        "skills": _string_list(payload.get("skills")),
        "model_provider": payload.get("model_provider") or None,
        "model_name": payload.get("model_name") or None,
        "avatar": str(payload.get("avatar") or agent_id[:2].upper()),
        "is_custom": True,
    }


def _normalize_agent_id(value: object) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value).strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "custom_agent"


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
