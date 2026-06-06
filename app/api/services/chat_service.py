from agenthub_harness import HarnessRunner
from agenthub_harness.adapters import build_agent_adapters_from_env
from agenthub_harness.core.context import RunContext

from app.api.services.conversation_service import (
    add_message,
    get_conversation,
    list_messages,
)
from app.api.services.artifact_service import save_artifacts


def build_chat_response(request: dict) -> dict:
    conversation_id = request["conversation_id"]
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found")

    message = request["message"]
    add_message(
        conversation_id=conversation_id,
        role=message["role"],
        sender="you" if message["role"] == "user" else message["role"],
        content=message["content"],
        format=message.get("format", "markdown"),
        quoted_message_id=message.get("quoted_message_id"),
    )
    history = list_messages(conversation_id)

    context = RunContext(
        conversation_id=conversation_id,
        message=message["content"],
        history=history,
        selected_agents=request.get("selected_agents") or conversation.get("agent_ids", []),
        mode=conversation.get("mode", "group"),
    )
    adapters = build_agent_adapters_from_env()
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

    return {
        "run_id": result.run_id,
        "status": result.status,
        "messages": saved_agent_messages,
        "artifacts": saved_artifacts,
        "events": [
            {
                "type": event.type,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
            for event in result.events
        ],
    }


def build_mock_chat_response(request: dict) -> dict:
    return build_chat_response(request)
