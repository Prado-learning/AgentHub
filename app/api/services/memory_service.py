from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.api.services.conversation_store import JsonStore
from app.api.services.llm_service import build_required_llm_provider, complete_json
from agenthub.runtime.prompt_builder import format_messages_for_prompt


RUNTIME_DIR = Path("agent-workspace/runtime")
MEMORIES = JsonStore(RUNTIME_DIR / "conversation_memories.json")
ALLOWED_CATEGORIES = {"preference", "constraint", "decision", "goal", "open_task"}
SECRET_PATTERN = re.compile(
    r"(api[_ -]?key|secret|password|token|sk-[a-zA-Z0-9_-]{8,})",
    re.IGNORECASE,
)


def list_memories(conversation_id: str) -> list[dict]:
    return [
        memory
        for memory in MEMORIES.read()
        if memory.get("conversation_id") == conversation_id
    ]


def delete_memory(conversation_id: str, memory_id: str) -> dict | None:
    deleted: dict | None = None

    def _mutate(records: list[dict]) -> list[dict] | None:
        nonlocal deleted
        for memory in records:
            if (
                memory.get("conversation_id") == conversation_id
                and memory.get("id") == memory_id
            ):
                deleted = memory
                return [item for item in records if item is not memory]
        return None

    MEMORIES.update(_mutate)
    return deleted


def extract_memories_with_llm(
    conversation_id: str,
    source_message: dict,
    history: list[dict],
    model_provider: str | None = None,
    model_name: str | None = None,
) -> list[dict]:
    provider, provider_id = build_required_llm_provider(model_provider, model_name)
    existing = list_memories(conversation_id)
    payload = complete_json(
        provider,
        _memory_prompt(source_message, history, existing),
    )
    candidates = payload.get("memories")
    if not isinstance(candidates, list):
        raise ValueError("LLM memory response must contain a memories list")

    created: list[dict] = []

    def _mutate(records: list[dict]) -> list[dict] | None:
        existing_keys = {
            _memory_key(str(memory.get("category") or ""), str(memory.get("content") or ""))
            for memory in records
        }
        new_memories: list[dict] = []
        for candidate in candidates[:8]:
            if not isinstance(candidate, dict):
                continue
            content = str(candidate.get("content") or "").strip()
            category = str(candidate.get("category") or "").strip().lower()
            if (
                not content
                or category not in ALLOWED_CATEGORIES
                or SECRET_PATTERN.search(content)
            ):
                continue
            key = _memory_key(category, content)
            if key in existing_keys:
                continue
            memory = {
                "id": f"mem_{uuid4().hex[:12]}",
                "conversation_id": conversation_id,
                "source_message_id": source_message.get("id"),
                "content": content[:600],
                "category": category,
                "confidence": _confidence(candidate.get("confidence")),
                "created_by": "llm",
                "model_provider": provider_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            new_memories.append(memory)
            created.append(memory)
            existing_keys.add(key)
        if not new_memories:
            return None
        return [*records, *new_memories]

    MEMORIES.update(_mutate)
    return created


def _memory_prompt(source_message: dict, history: list[dict], existing: list[dict]) -> str:
    return (
        "Extract only durable, useful memories for future turns in this conversation.\n"
        "The user deliberately requested smart memory extraction from the source message, "
        "so prefer extracting durable goals, preferences, constraints, decisions, or open tasks "
        "when they are present.\n"
        "Never extract API keys, secrets, passwords, tokens, or transient small talk.\n"
        "Allowed categories: preference, constraint, decision, goal, open_task.\n"
        "Do not repeat existing memories. Return only JSON.\n\n"
        f"Existing memories:\n{existing}\n\n"
        f"Recent conversation:\n{format_messages_for_prompt(history, limit=12, total_limit=5000)}\n\n"
        f"Source message:\n{source_message.get('content', '')}\n\n"
        'Schema: {"memories":[{"category":"constraint","content":"...",'
        '"confidence":0.9}]}'
    )


def _memory_key(category: str, content: str) -> str:
    normalized = re.sub(r"\s+", " ", content).strip().lower()
    return f"{category}:{normalized}"


def _confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5
