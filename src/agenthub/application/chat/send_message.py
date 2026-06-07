from __future__ import annotations

from datetime import datetime, timezone

from agenthub.domain.run import RunContext
from agenthub.orchestration.coordinator import HarnessRunner
from agenthub.adapters import build_agent_adapters_from_env
from app.api.services.artifact_service import save_artifacts
from app.api.services.attachment_service import get_attachment_records_by_ids
from app.api.services.context_summary_service import get_or_update_summary
from app.api.services.conversation_service import (
    add_message,
    deactivate_generation_group,
    get_conversation,
    list_messages,
    list_pinned_messages,
    next_generation_index,
)


class SendMessageUseCase:
    def execute(self, request: dict) -> dict:
        conversation_id = request["conversation_id"]
        conversation = get_conversation(conversation_id)
        if conversation is None:
            raise ValueError("Conversation not found")

        message = request["message"]
        attachment_ids = message.get("attachment_ids") or []
        saved_user_message = add_message(
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
        history = list_messages(conversation_id)
        attachments = get_attachment_records_by_ids(attachment_ids)
        summary = get_or_update_summary(conversation_id, history)

        context = RunContext(
            conversation_id=conversation_id,
            message=message["content"],
            history=history,
            selected_agents=request.get("selected_agents") or conversation.get("agent_ids", []),
            mode="single" if request.get("agent_mode") == "single" else conversation.get("mode", "group"),
            pinned_context=list_pinned_messages(conversation_id),
            conversation_summary=summary,
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
        generation_group_id = (
            request.get("regenerate_from_message_id")
            or message.get("quoted_message_id")
            or saved_user_message["id"]
        )
        replaced_message_ids = []
        if request.get("regenerate_from_message_id"):
            replaced_message_ids = deactivate_generation_group(conversation_id, generation_group_id)
        generation_index = next_generation_index(conversation_id, generation_group_id)

        saved_agent_messages = [
            add_message(
                conversation_id=conversation_id,
                role=agent_message["role"],
                sender=agent_message.get("sender"),
                content=agent_message["content"],
                format=agent_message.get("format", "markdown"),
                artifact_ids=artifact_ids,
                generation_group_id=generation_group_id,
                generation_index=generation_index,
                replaces_message_ids=replaced_message_ids,
                is_active_generation=True,
            )
            for agent_message in result.messages
        ]

        events = [
            {
                "type": event.type,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
            for event in result.events
        ]
        return {
            "run_id": result.run_id,
            "status": result.status,
            "messages": saved_agent_messages,
            "artifacts": saved_artifacts,
            "events": [*_diagnostic_events(request, attachments), *events],
        }


def build_chat_response(request: dict) -> dict:
    return SendMessageUseCase().execute(request)


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

