"""Wire application ports to HTTP persistence/services."""

from uuid import uuid4
from agenthub.application.chat.send_message import ChatServices, SendMessageUseCase
from app.api.services import conversation_service as conversations
from app.api.services import (
    attachment_service,
    artifact_service,
    agent_creation_service,
    context_summary_service,
    memory_service,
)
from app.api.services import execution_service, run_store


def build_chat_response(request: dict) -> dict:
    run_id = request.get("_run_id") or f"run_{uuid4().hex[:12]}"
    services = ChatServices(
        get_conversation=conversations.get_conversation,
        add_message=conversations.add_message,
        list_messages=conversations.list_messages,
        list_pinned_messages=conversations.list_pinned_messages,
        get_attachments=attachment_service.get_attachment_records_by_ids,
        handle_agent_creation=agent_creation_service.handle_agent_creation_message,
        get_summary=context_summary_service.get_or_update_summary,
        list_memories=memory_service.list_memories,
        list_artifacts=artifact_service.list_artifacts,
        execute_context=execution_service.execute_context,
        publish_result=execution_service.publish_result,
        deactivate_generation_group=conversations.deactivate_generation_group,
    )
    with execution_service.lock_for(run_id):
        return SendMessageUseCase(services).execute({**request, "_run_id": run_id})


build_mock_chat_response = build_chat_response
