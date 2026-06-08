"""Prompt assembly helpers for system prompt, skills, context, and task."""

from __future__ import annotations

import re


CODE_FENCE_RE = re.compile(r"```([A-Za-z0-9_-]*)\n?([\s\S]*?)```")
WHITESPACE_RE = re.compile(r"\s+")


def format_messages_for_prompt(
    messages: list[dict] | None,
    *,
    limit: int = 6,
    item_limit: int = 700,
    total_limit: int = 3600,
    empty: str = "No recent history.",
) -> str:
    """Format chat messages without letting generated code dominate the prompt."""
    selected = (messages or [])[-limit:] if limit > 0 else messages or []
    lines: list[str] = []
    for item in selected:
        content = compact_message_content(str(item.get("content") or ""), limit=item_limit)
        if not content:
            continue
        sender = str(item.get("sender") or item.get("role") or "unknown").strip() or "unknown"
        lines.append(f"{sender}: {content}")

    return _clip_text("\n".join(lines), total_limit) or empty


def compact_message_content(content: str, *, limit: int = 700) -> str:
    text = content.strip()
    if not text:
        return ""

    text = CODE_FENCE_RE.sub(_code_fence_summary, text)
    if _looks_like_large_code(text):
        text = f"[large generated code/html omitted, {len(text)} chars]"
    text = WHITESPACE_RE.sub(" ", text).strip()
    return _clip_text(text, limit)


def _code_fence_summary(match: re.Match[str]) -> str:
    language = match.group(1).strip() or "text"
    code = match.group(2) or ""
    line_count = len(code.splitlines())
    return f"[code block omitted: {language}, {len(code)} chars, {line_count} lines]"


def _looks_like_large_code(text: str) -> bool:
    if len(text) < 1200 or text.count("\n") < 18:
        return False
    lowered = text.lower()
    code_markers = (
        "<!doctype",
        "<html",
        "<body",
        "</div>",
        "export default",
        "function ",
        "const ",
        "class=",
        "@keyframes",
    )
    return any(marker in lowered for marker in code_markers)


def _clip_text(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."
