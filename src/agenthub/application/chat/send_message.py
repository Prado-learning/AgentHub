from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from agenthub.domain.run import RunContext, RunResult
from dataclasses import dataclass
from agenthub.infrastructure.config.paths import conversation_workspace


@dataclass
class ChatServices:
    get_conversation: Callable
    add_message: Callable
    list_messages: Callable
    list_pinned_messages: Callable
    get_attachments: Callable
    handle_agent_creation: Callable
    get_summary: Callable
    list_artifacts: Callable
    list_memories: Callable
    execute_context: Callable
    publish_result: Callable
    deactivate_generation_group: Callable


class SendMessageUseCase:
    def __init__(self, services: ChatServices) -> None:
        self.services = services

    def execute(
        self,
        request: dict,
        *,
        on_run_result: Callable[[RunResult], None] | None = None,
    ) -> dict:
        conversation_id = request["conversation_id"]
        conversation = self.services.get_conversation(conversation_id)
        if conversation is None:
            raise ValueError("Conversation not found")

        message = request["message"]
        attachment_ids = message.get("attachment_ids") or []
        attachments = self.services.get_attachments(attachment_ids)
        if len(attachments) != len(set(attachment_ids)) or any(
            a.get("conversation_id") != conversation_id for a in attachments
        ):
            raise ValueError("Attachment does not belong to this conversation")
        saved_user_message = self.services.add_message(
            conversation_id=conversation_id,
            role=message["role"],
            sender="you" if message["role"] == "user" else message["role"],
            content=message["content"],
            format=message.get("format", "markdown"),
            quoted_message_id=message.get("quoted_message_id"),
            quoted_text=message.get("quoted_text"),
            quoted_artifact_id=message.get("quoted_artifact_id"),
            quoted_range=message.get("quoted_range"),
            attachment_ids=attachment_ids,
        )
        history = [
            m
            for m in self.services.list_messages(conversation_id)
            if m.get("is_active", True)
        ]
        agent_creation = self.services.handle_agent_creation(
            conversation_id,
            message["content"],
            history,
            model_provider=request.get("model_provider"),
            model_name=request.get("model_name"),
        )
        if agent_creation is not None:
            response = self._save_agent_creation_response(
                conversation_id,
                saved_user_message,
                agent_creation,
            )
            response["run_id"] = request.get("_run_id") or response["run_id"]
            return response
        summary = self.services.get_summary(
            conversation_id,
            history,
            model_provider=request.get("model_provider"),
            model_name=request.get("model_name"),
        )
        pinned_context = self.services.list_pinned_messages(conversation_id)
        conversation_memories = self.services.list_memories(conversation_id)

        context = RunContext(
            conversation_id=conversation_id,
            message=message["content"],
            history=history,
            selected_agents=request.get("selected_agents")
            or conversation.get("agent_ids", []),
            mode="single"
            if request.get("agent_mode") == "single"
            else conversation.get("mode", "group"),
            pinned_context=pinned_context,
            conversation_memories=conversation_memories,
            conversation_summary=summary,
            attachments=attachments,
            tool_preferences=request.get("tool_preferences") or {},
            workspace_dir=str(conversation_workspace(conversation_id)),
            upstream_artifacts=[
                a
                for a in self.services.list_artifacts(conversation_id)
                if a.get("type") in {"code", "preview", "diff", "workflow"}
            ][-8:],
        )
        result = self.services.execute_context(
            context,
            run_id=request.get("_run_id"),
            model_provider=request.get("model_provider"),
            model_name=request.get("model_name"),
        )
        if on_run_result is not None:
            on_run_result(result)
        group = request.get("regenerate_from_message_id") or saved_user_message["id"]
        if request.get("regenerate_from_message_id"):
            self.services.deactivate_generation_group(conversation_id, group)
        return self.services.publish_result(result, generation_group_id=group)

    def _save_agent_creation_response(
        self,
        conversation_id: str,
        saved_user_message: dict,
        result: dict,
    ) -> dict:
        event_type = (
            "agent.created"
            if result.get("status") == "created"
            else "agent.creation_collecting"
        )
        trace_events = _trace_events(
            [
                {
                    "type": event_type,
                    "payload": {
                        "status": result.get("status"),
                        "agent_id": (result.get("agent") or {}).get("id"),
                    },
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
            run_id=f"agent_creation_{saved_user_message['id']}",
        )
        saved_message = self.services.add_message(
            conversation_id=conversation_id,
            role="agent",
            sender="orchestrator",
            content=str(result.get("content") or ""),
            format="markdown",
            generation_group_id=saved_user_message["id"],
            generation_index=1,
            trace_events=trace_events,
        )
        return {
            "run_id": f"agent_creation_{saved_user_message['id']}",
            "status": "failed" if result.get("status") == "failed" else "success",
            "messages": [saved_message],
            "artifacts": [],
            "events": trace_events,
            "created_agent": result.get("agent"),
        }


def build_chat_response(request: dict, *, services: ChatServices) -> dict:
    return SendMessageUseCase(services).execute(request)


def _diagnostic_events(
    request: dict,
    attachments: list[dict],
    history: list[dict],
    context: RunContext,
) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    image_count = len(
        [
            attachment
            for attachment in attachments
            if str(attachment.get("mime_type", "")).startswith("image/")
        ]
    )
    return [
        {
            "type": "message.received",
            "payload": {
                "conversation_id": request.get("conversation_id"),
                "message_length": len(
                    str(request.get("message", {}).get("content", ""))
                ),
                "regenerate": bool(request.get("regenerate_from_message_id")),
            },
            "created_at": now,
        },
        {
            "type": "context.loaded",
            "payload": {
                "mode": context.mode,
                "history_count": len(history),
                "pinned_count": len(context.pinned_context or []),
                "selected_agents": context.selected_agents,
            },
            "created_at": now,
        },
        {
            "type": "model.selected",
            "payload": {
                "provider": request.get("model_provider") or "auto",
                "model_name": request.get("model_name") or "",
            },
            "created_at": now,
        },
        {
            "type": "attachments.prepared",
            "payload": {
                "count": len(attachments),
                "image_count": image_count,
                "total_bytes": sum(
                    int(attachment.get("size") or 0) for attachment in attachments
                ),
            },
            "created_at": now,
        },
    ]


def _trace_events(events: list[dict], run_id: str) -> list[dict]:
    if not events:
        return []
    start_time = _parse_iso(events[0].get("created_at"))
    return [
        _trace_event(event, index=index, run_id=run_id, start_time=start_time)
        for index, event in enumerate(events)
    ]


def _trace_event(
    event: dict,
    index: int,
    run_id: str,
    start_time: datetime | None,
) -> dict:
    created_at = str(event.get("created_at") or datetime.now(timezone.utc).isoformat())
    current_time = _parse_iso(created_at)
    title, detail, status = _describe_event(event)
    duration_ms = None
    if start_time and current_time:
        duration_ms = max(0, int((current_time - start_time).total_seconds() * 1000))
    return {
        **event,
        "id": f"{run_id}_trace_{index + 1}",
        "run_id": run_id,
        "title": title,
        "detail": detail,
        "status": status,
        "agent_id": event.get("payload", {}).get("agent_id"),
        "duration_ms": duration_ms,
        "metadata": event.get("payload", {}),
        "created_at": created_at,
    }


def _describe_event(event: dict) -> tuple[str, str, str]:
    event_type = str(event.get("type") or "")
    payload = event.get("payload") or {}
    if event_type == "message.received":
        return (
            "收到用户消息",
            f"消息长度 {payload.get('message_length', 0)} 字符",
            "done",
        )
    if event_type == "context.loaded":
        agents = ", ".join(payload.get("selected_agents") or [])
        return (
            "读取会话上下文",
            (
                f"{payload.get('history_count', 0)} 条历史，"
                f"{payload.get('pinned_count', 0)} 条长期上下文，"
                f"模式 {payload.get('mode', '')}，Agent: {agents or 'auto'}"
            ),
            "done",
        )
    if event_type == "model.selected":
        return (
            "选择模型",
            f"{payload.get('provider') or 'auto'} {payload.get('model_name') or ''}".strip(),
            "done",
        )
    if event_type == "attachments.prepared":
        return (
            "准备附件",
            (
                f"{payload.get('count', 0)} 个附件，"
                f"{payload.get('image_count', 0)} 张图片，"
                f"{payload.get('total_bytes', 0)} bytes"
            ),
            "done",
        )
    if event_type == "run.started":
        return "启动 Orchestrator", f"会话 {payload.get('conversation_id', '')}", "done"
    if event_type == "run.planned":
        steps = payload.get("steps") or []
        return (
            "完成任务拆解",
            f"{len(steps)} 个步骤：{payload.get('reason', '')}",
            "done",
        )
    if event_type in {"agent.started", "agent.parallel_started"}:
        tools = ", ".join(payload.get("tools") or [])
        detail = str(payload.get("task") or "")
        if tools:
            detail = f"{detail}；工具 {tools}"
        return f"调用 Agent {payload.get('agent_id', '')}", detail, "done"
    if event_type == "agent.completed":
        status = "error" if payload.get("status") == "failed" else "done"
        detail = f"状态 {payload.get('status', '')}，产物 {payload.get('artifact_count', 0)} 个"
        if payload.get("error"):
            detail = f"{detail}，错误：{payload.get('error')}"
        return f"Agent {payload.get('agent_id', '')} 完成", detail, status
    if event_type == "agent.skipped":
        return (
            f"跳过 Agent {payload.get('agent_id', '')}",
            str(payload.get("reason") or ""),
            "error",
        )
    if event_type == "tool.started":
        keys = ", ".join(payload.get("argument_keys") or [])
        return (
            f"调用工具 {payload.get('tool_id', '')}",
            f"参数：{keys or 'none'}",
            "done",
        )
    if event_type == "tool.completed":
        return (
            f"工具 {payload.get('tool_id', '')} 完成",
            (
                f"生成 {payload.get('artifact_type', '')}：{payload.get('artifact_title', '')}"
            ),
            "done",
        )
    if event_type == "tool.failed":
        return (
            f"工具 {payload.get('tool_id', '')} 失败",
            str(payload.get("error") or ""),
            "error",
        )
    if event_type == "run.completed":
        status = "error" if payload.get("status") == "failed" else "done"
        return (
            "汇总执行结果",
            (
                f"状态 {payload.get('status', '')}，"
                f"Agent {payload.get('agent_count', 0)} 个，"
                f"产物 {payload.get('artifact_count', 0)} 个，"
                f"冲突 {payload.get('conflict_count', 0)} 个"
            ),
            status,
        )
    return event_type or "执行事件", str(payload), "done"


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None
