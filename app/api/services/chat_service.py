from datetime import datetime, timezone

from agenthub_harness import HarnessRunner
from agenthub_harness.adapters import build_agent_adapters_from_env
from agenthub_harness.core.context import RunContext

from app.api.services.conversation_service import (
    add_message,
    get_conversation,
    list_pinned_messages,
    list_messages,
)
from app.api.services.artifact_service import save_artifacts
from app.api.services.attachment_service import get_attachment_records_by_ids


def build_chat_response(request: dict) -> dict:
    conversation_id = request["conversation_id"]
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found")

    message = request["message"]
    attachment_ids = message.get("attachment_ids") or []
    add_message(
        conversation_id=conversation_id,
        role=message["role"],
        sender="you" if message["role"] == "user" else message["role"],
        content=message["content"],
        format=message.get("format", "markdown"),
        quoted_message_id=message.get("quoted_message_id"),
        attachment_ids=attachment_ids,
    )
    history = list_messages(conversation_id)
    attachments = get_attachment_records_by_ids(attachment_ids)

    context = RunContext(
        conversation_id=conversation_id,
        message=message["content"],
        history=history,
        selected_agents=request.get("selected_agents") or conversation.get("agent_ids", []),
        mode="single" if request.get("agent_mode") == "single" else conversation.get("mode", "group"),
        pinned_context=list_pinned_messages(conversation_id),
        attachments=attachments,
        tool_preferences=request.get("tool_preferences") or {},
    )
    adapters = build_agent_adapters_from_env(
        model_provider=request.get("model_provider"),
        model_name=request.get("model_name"),
    )
    result = HarnessRunner(mode="configured", adapters=adapters).run(context)
    saved_artifacts = save_artifacts(
        conversation_id=conversation_id,
        run_id=result.run_id,
        artifacts=result.artifacts,
    )
    artifact_ids = [artifact["id"] for artifact in saved_artifacts]

    saved_agent_messages = [
        add_message(
            conversation_id=conversation_id,
            role=agent_message["role"],
            sender=agent_message.get("sender"),
            content=agent_message["content"],
            format=agent_message.get("format", "markdown"),
            artifact_ids=artifact_ids,
        )
        for agent_message in result.messages
    ]

    events = [
        *[
            {
                "type": event.type,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
            for event in result.events
        ],
    ]
    return {
        "run_id": result.run_id,
        "status": result.status,
        "messages": saved_agent_messages,
        "artifacts": saved_artifacts,
        "events": [*_diagnostic_events(request, attachments), *events],
    }


def build_mock_chat_response(request: dict) -> dict:
    return build_chat_response(request)


def _diagnostic_events(request: dict, attachments: list[dict]) -> list[dict]:
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
                "total_bytes": sum(int(attachment.get("size") or 0) for attachment in attachments),
            },
            "created_at": now,
        },
    ]
