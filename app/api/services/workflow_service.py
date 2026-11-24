"""Workflow JSON is compiled to a Plan; execution belongs exclusively to Harness."""

from __future__ import annotations
import json
import re
from uuid import uuid4
from agenthub.domain.plan import Plan, PlanStep
from agenthub.domain.run import RunContext
from agenthub.orchestration.rule_planner import infer_authority
from agenthub.infrastructure.config.paths import conversation_workspace
from app.api.services.artifact_service import get_artifact
from app.api.services.attachment_service import list_attachment_records
from app.api.services.conversation_service import (
    get_conversation,
    list_messages,
    list_pinned_messages,
)
from app.api.services.memory_service import list_memories
from app.api.services.context_summary_service import get_or_update_summary
from app.api.services.execution_service import execute_context, publish_result, lock_for


def parse_workflow_definition(content: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", content.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Workflow content is not valid JSON") from exc
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("nodes"), list)
        or not payload["nodes"]
    ):
        raise ValueError("Workflow must contain nodes")
    if len(payload["nodes"]) > 100:
        raise ValueError("Workflow exceeds 100 nodes")
    return payload


def _step_from_node(node: dict) -> PlanStep:
    if not isinstance(node, dict):
        raise ValueError("Workflow node must be an object")
    kind = node.get("type", "agent")
    if kind not in {"agent", "tool", "input"}:
        raise ValueError("Unsupported workflow node type")
    node_id = str(node.get("id") or "").strip()
    if not node_id:
        raise ValueError("Workflow node requires id")
    tools = node.get("tools") or ([node["tool_id"]] if node.get("tool_id") else [])
    if not isinstance(tools, list) or any(not isinstance(t, str) for t in tools):
        raise ValueError("Invalid workflow tools")
    if kind == "tool" and not tools:
        raise ValueError("Tool node requires tool_id")
    agent = node.get("agent_id") or (
        "orchestrator" if kind in {"input", "tool"} else ""
    )
    if not agent:
        raise ValueError("Agent node requires agent_id")
    deps = node.get("depends_on", [])
    if not isinstance(deps, list):
        raise ValueError("Invalid workflow dependencies")
    return PlanStep(
        id=node_id,
        agent_id=agent,
        task=str(node.get("task") or node.get("prompt") or node.get("label") or ""),
        tools=tools,
        depends_on=deps,
        can_run_parallel=bool(node.get("can_run_parallel", True)),
        authority=infer_authority(tools),
        kind=kind,
        arguments=node.get("arguments") or {},
    )


def run_workflow_artifact(
    artifact_id: str, *, model_provider=None, model_name=None, _run_id=None
) -> dict:
    artifact = get_artifact(artifact_id)
    if not artifact or artifact.get("type") != "workflow":
        raise ValueError("Workflow artifact not found")
    conversation_id = artifact.get("conversation_id", "")
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise ValueError("Conversation not found")
    workflow = parse_workflow_definition(artifact.get("content", ""))
    plan = Plan(
        steps=[_step_from_node(node) for node in workflow["nodes"]],
        reason=f"workflow: {workflow.get('title', 'Workflow')}",
    )
    history = list_messages(conversation_id)
    context = RunContext(
        conversation_id=conversation_id,
        message=workflow.get("source_prompt") or artifact.get("title", "Run workflow"),
        history=history,
        selected_agents=conversation.get("agent_ids", []),
        mode=conversation.get("mode", "group"),
        pinned_context=list_pinned_messages(conversation_id),
        conversation_memories=list_memories(conversation_id),
        conversation_summary=get_or_update_summary(
            conversation_id, history, model_provider, model_name
        ),
        attachments=list_attachment_records(conversation_id),
        workspace_dir=str(conversation_workspace(conversation_id)),
    )
    run_id = _run_id or f"workflow_run_{uuid4().hex[:12]}"
    with lock_for(run_id):
        return publish_result(
            execute_context(
                context,
                run_id=run_id,
                plan=plan,
                model_provider=model_provider,
                model_name=model_name,
            )
        )
