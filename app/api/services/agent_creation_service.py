from __future__ import annotations

import re
from pathlib import Path

from app.api.services.agent_service import create_custom_agent
from app.api.services.conversation_store import JsonStore
from app.api.services.llm_service import build_required_llm_provider, complete_json
from agenthub.application.tools.catalog import ToolCatalog
from agenthub.runtime.prompt_builder import format_messages_for_prompt


RUNTIME_DIR = Path("agent-workspace/runtime")
SESSIONS = JsonStore(RUNTIME_DIR / "agent_creation_sessions.json")
CREATE_PATTERN = re.compile(
    r"(创建|新建|新增|配置|create|build|add).{0,20}(agent|智能体)",
    re.IGNORECASE,
)
REQUIRED_FIELDS = ("name", "description", "system_prompt", "tools")


def handle_agent_creation_message(
    conversation_id: str,
    message: str,
    history: list[dict],
    model_provider: str | None = None,
    model_name: str | None = None,
) -> dict | None:
    session = _get_session(conversation_id)
    if session is None and not CREATE_PATTERN.search(message):
        return None

    try:
        provider, provider_id = build_required_llm_provider(model_provider, model_name)
        payload = complete_json(
            provider,
            _creation_prompt(message, history, session),
        )
    except Exception as exc:
        return {
            "status": "failed",
            "content": f"无法继续创建 Agent：{exc}",
            "agent": None,
        }

    draft = _merge_draft((session or {}).get("draft") or {}, payload)
    missing = [field for field in REQUIRED_FIELDS if not draft.get(field)]
    if missing:
        _save_session(conversation_id, draft, missing, provider_id)
        return {
            "status": "collecting",
            "content": _clarification_message(draft, missing),
            "agent": None,
        }

    agent = create_custom_agent(draft)
    _delete_session(conversation_id)
    return {
        "status": "created",
        "content": (
            f"已创建 Agent：{agent['name']}（@{agent['id']}）。\n\n"
            f"- 职责：{agent['description']}\n"
            f"- 能力：{', '.join(agent.get('capabilities') or []) or 'text'}\n"
            f"- 工具：{', '.join(agent.get('tools') or []) or 'none'}\n"
            f"- 模型：{agent.get('model_provider') or 'conversation model'}"
        ),
        "agent": agent,
    }


def _creation_prompt(
    message: str,
    history: list[dict],
    session: dict | None,
) -> str:
    tools = ToolCatalog().list_tools()
    return (
        "You configure a real AgentHub custom Agent from a multi-turn conversation.\n"
        "Extract only information explicitly stated or safely inferred from the requested role.\n"
        "Use only tool IDs from the available tools. Return only JSON.\n\n"
        f"Available tools:\n{tools}\n\n"
        f"Existing draft:\n{(session or {}).get('draft') or {}}\n\n"
        f"Recent conversation:\n{format_messages_for_prompt(history, limit=12, total_limit=5000)}\n\n"
        f"Latest user message:\n{message}\n\n"
        "Schema: "
        '{"name":"","description":"","system_prompt":"","capabilities":[],'
        '"tools":[],"skills":[],"model_provider":null,"model_name":null}'
    )


def _merge_draft(current: dict, payload: dict) -> dict:
    valid_tool_ids = {tool["id"] for tool in ToolCatalog().list_tools()}
    tools = [
        str(tool_id)
        for tool_id in payload.get("tools", current.get("tools", []))
        if str(tool_id) in valid_tool_ids
    ]
    return {
        "name": str(payload.get("name") or current.get("name") or "").strip(),
        "description": str(
            payload.get("description") or current.get("description") or ""
        ).strip(),
        "system_prompt": str(
            payload.get("system_prompt") or current.get("system_prompt") or ""
        ).strip(),
        "capabilities": _string_list(
            payload.get("capabilities") or current.get("capabilities")
        ),
        "tools": tools,
        "skills": _string_list(payload.get("skills") or current.get("skills")),
        "model_provider": payload.get("model_provider") or current.get("model_provider"),
        "model_name": payload.get("model_name") or current.get("model_name"),
    }


def _clarification_message(draft: dict, missing: list[str]) -> str:
    labels = {
        "name": "Agent 名称",
        "description": "职责描述",
        "system_prompt": "System Prompt",
        "tools": "允许使用的工具",
    }
    known = "\n".join(
        f"- {key}: {value}"
        for key, value in draft.items()
        if value and key in REQUIRED_FIELDS
    )
    return (
        "我正在创建这个 Agent，但还需要补充以下信息："
        f"{'、'.join(labels[field] for field in missing)}。\n\n"
        f"当前已确认：\n{known or '- 暂无'}"
    )


def _get_session(conversation_id: str) -> dict | None:
    return next(
        (
            session
            for session in SESSIONS.read()
            if session.get("conversation_id") == conversation_id
        ),
        None,
    )


def _save_session(
    conversation_id: str,
    draft: dict,
    missing: list[str],
    provider_id: str,
) -> None:
    sessions = [
        session
        for session in SESSIONS.read()
        if session.get("conversation_id") != conversation_id
    ]
    sessions.append(
        {
            "conversation_id": conversation_id,
            "status": "collecting",
            "draft": draft,
            "missing_fields": missing,
            "model_provider": provider_id,
        }
    )
    SESSIONS.write(sessions)


def _delete_session(conversation_id: str) -> None:
    SESSIONS.write(
        [
            session
            for session in SESSIONS.read()
            if session.get("conversation_id") != conversation_id
        ]
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
