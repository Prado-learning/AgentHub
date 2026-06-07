from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from app.api.services.conversation_store import JsonStore


RUNTIME_DIR = Path("agent-workspace/runtime")
SUMMARIES = JsonStore(RUNTIME_DIR / "conversation_summaries.json")
MAX_HISTORY_MESSAGES_WITHOUT_SUMMARY = 18
MAX_HISTORY_CHARS_WITHOUT_SUMMARY = 10000


def get_or_update_summary(conversation_id: str, history: list[dict]) -> dict | None:
    total_chars = sum(len(str(item.get("content") or "")) for item in history)
    if len(history) < MAX_HISTORY_MESSAGES_WITHOUT_SUMMARY and total_chars < MAX_HISTORY_CHARS_WITHOUT_SUMMARY:
        return _get_summary(conversation_id)

    summary_text = _build_rule_summary(history)
    records = [item for item in SUMMARIES.read() if item.get("conversation_id") != conversation_id]
    summary = {
        "conversation_id": conversation_id,
        "content": summary_text,
        "message_count": len(history),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    records.append(summary)
    SUMMARIES.write(records)
    return summary


def _get_summary(conversation_id: str) -> dict | None:
    return next(
        (item for item in SUMMARIES.read() if item.get("conversation_id") == conversation_id),
        None,
    )


def _build_rule_summary(history: list[dict], limit: int = 1800) -> str:
    important = []
    for item in history[-24:]:
        sender = item.get("sender") or item.get("role") or "unknown"
        content = _clean(str(item.get("content") or ""))
        if not content:
            continue
        important.append(f"- {sender}: {content[:240]}")
    summary = "Conversation summary for long-context continuity:\n" + "\n".join(important)
    return summary[:limit]


def _clean(content: str) -> str:
    content = re.sub(r"```[\s\S]*?```", " code block ", content)
    return re.sub(r"\s+", " ", content).strip()
