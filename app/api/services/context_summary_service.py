from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.api.services.conversation_store import JsonStore
from app.api.services.llm_service import build_required_llm_provider
from agenthub.runtime.prompt_builder import format_messages_for_prompt


RUNTIME_DIR = Path("agent-workspace/runtime")
SUMMARIES = JsonStore(RUNTIME_DIR / "conversation_summaries.json")
MAX_HISTORY_MESSAGES_WITHOUT_SUMMARY = 18
MAX_HISTORY_CHARS_WITHOUT_SUMMARY = 10000


def get_or_update_summary(
    conversation_id: str,
    history: list[dict],
    model_provider: str | None = None,
    model_name: str | None = None,
) -> dict | None:
    total_chars = sum(len(str(item.get("content") or "")) for item in history)
    if len(history) < MAX_HISTORY_MESSAGES_WITHOUT_SUMMARY and total_chars < MAX_HISTORY_CHARS_WITHOUT_SUMMARY:
        return _get_summary(conversation_id)

    previous = _get_summary(conversation_id)
    try:
        provider, provider_id = build_required_llm_provider(model_provider, model_name)
        summary_text = provider.complete(_summary_prompt(history, previous))
    except Exception:
        return previous
    records = [item for item in SUMMARIES.read() if item.get("conversation_id") != conversation_id]
    summary = {
        "conversation_id": conversation_id,
        "content": summary_text,
        "source": "llm",
        "model_provider": provider_id,
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


def _summary_prompt(history: list[dict], previous: dict | None) -> str:
    return (
        "Summarize this AgentHub conversation for future agent turns.\n"
        "Preserve durable facts and current work state. Do not invent details.\n"
        "Use these sections: User goals, Confirmed constraints, Decisions, "
        "Artifacts and progress, Open tasks.\n\n"
        f"Previous summary:\n{(previous or {}).get('content', 'None')}\n\n"
        f"Conversation:\n{format_messages_for_prompt(history, limit=30, total_limit=12000)}"
    )
