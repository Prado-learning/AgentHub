from __future__ import annotations

import json
import re
from uuid import uuid4

from agenthub.adapters import build_agent_adapters_from_env
from agenthub.artifacts.conflict_resolver import resolve_artifact_conflicts
from agenthub.domain.plan import PlanStep
from agenthub.domain.run import RunContext
from agenthub.orchestration.coordinator import HarnessRunner, StepExecutionResult
from app.api.services.artifact_service import get_artifact, save_artifacts
from app.api.services.attachment_service import list_attachment_records
from app.api.services.context_summary_service import get_or_update_summary
from app.api.services.conversation_service import (
    add_message,
    get_conversation,
    list_messages,
    list_pinned_messages,
)
from app.api.services.memory_service import list_memories
from agenthub.application.chat.send_message import _trace_events


def run_workflow_artifact(
    artifact_id: str,
    *,
    model_provider: str | None = None,
    model_name: str | None = None,
) -> dict:
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise ValueError("Workflow artifact not found")
    if artifact.get("type") != "workflow":
        raise ValueError("Artifact is not a workflow")

    conversation_id = str(artifact.get("conversation_id") or "").strip()
    if not conversation_id:
        raise ValueError("Workflow artifact is missing conversation context")

    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found")

    workflow = parse_workflow_definition(str(artifact.get("content") or ""))
    history = list_messages(conversation_id)
    attachments = list_attachment_records(conversation_id)
    summary = get_or_update_summary(
        conversation_id,
        history,
        model_provider=model_provider,
        model_name=model_name,
    )
    context = RunContext(
        conversation_id=conversation_id,
        message=str(workflow.get("source_prompt") or artifact.get("title") or "Run workflow"),
        history=history,
        selected_agents=conversation.get("agent_ids", []),
        mode=conversation.get("mode", "group"),
        pinned_context=list_pinned_messages(conversation_id),
        conversation_memories=list_memories(conversation_id),
        conversation_summary=summary,
        attachments=attachments,
    )

    runner = HarnessRunner(
        mode="configured",
        adapters=build_agent_adapters_from_env(
            model_provider=model_provider,
            model_name=model_name,
        ),
    )
    runner.events = []
    _record_base_events(
        runner,
        workflow_id=artifact_id,
        workflow=workflow,
        context=context,
        model_provider=model_provider,
        model_name=model_name,
    )

    results: dict[str, StepExecutionResult] = {}
    dynamic_history = [*history]
    raw_messages: list[dict] = []
    raw_artifacts: list[dict] = []
    pending = {
        str(node.get("id")): node
        for node in workflow.get("nodes", [])
        if isinstance(node, dict) and str(node.get("id", "")).strip()
    }

    while pending:
        ready = [
            node
            for node in pending.values()
            if all(dep in results for dep in _depends_on(node))
        ]
        if not ready:
            unresolved = ", ".join(sorted(pending))
            raise ValueError(f"Workflow has unresolved dependencies: {unresolved}")

        for node in ready:
            pending.pop(str(node.get("id")), None)
            node_id = str(node.get("id"))
            dependencies = _depends_on(node)
            if any(results[dependency].status != "success" for dependency in dependencies):
                skipped = StepExecutionResult(
                    step_id=node_id,
                    agent_id=_node_owner(node),
                    status="skipped",
                    messages=[],
                    artifacts=[],
                    error="dependency failed",
                )
                results[node_id] = skipped
                runner._record_event(
                    "agent.skipped",
                    {
                        "step_id": node_id,
                        "agent_id": skipped.agent_id,
                        "reason": skipped.error,
                    },
                )
                continue

            node_type = str(node.get("type") or "agent").strip().lower()
            if node_type == "input":
                results[node_id] = StepExecutionResult(
                    step_id=node_id,
                    agent_id="orchestrator",
                    status="success",
                )
                continue

            step = _step_from_node(node)
            node_context = _context_for_node(context, dynamic_history, _node_task(node, context.message))
            runner._record_event(
                "agent.started",
                {
                    "step_id": step.id,
                    "agent_id": step.agent_id,
                    "task": step.task,
                    "tools": step.tools,
                    "depends_on": step.depends_on,
                },
            )
            if node_type == "tool":
                result = _execute_tool_node(runner, step, node_context, raw_artifacts)
            else:
                result = runner._execute_step(step, node_context, raw_artifacts)
            results[node_id] = result
            raw_messages.extend(result.messages)
            dynamic_history.extend(result.messages)
            raw_artifacts.extend(result.artifacts)
            runner._completion_event(result)

    artifacts, conflicts = resolve_artifact_conflicts(raw_artifacts)
    status = runner._run_status(results)
    runner._record_event(
        "run.completed",
        {
            "conversation_id": conversation_id,
            "agent_count": len(results),
            "artifact_count": len(artifacts),
            "conflict_count": len(conflicts),
            "status": status,
        },
    )

    if not raw_messages:
        raw_messages = [
            {
                "role": "agent",
                "sender": "orchestrator",
                "content": _workflow_completion_message(workflow, status, len(artifacts)),
                "format": "markdown",
            }
        ]

    run_id = f"workflow_run_{uuid4().hex[:12]}"
    event_payloads = [
        {
            "type": event.type,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }
        for event in runner.events
    ]
    trace_events = _trace_events(event_payloads, run_id=run_id)
    saved_artifacts = save_artifacts(
        conversation_id=conversation_id,
        run_id=run_id,
        artifacts=artifacts,
    )
    artifact_ids = [item["id"] for item in saved_artifacts]
    saved_messages = [
        add_message(
            conversation_id=conversation_id,
            role=str(message.get("role") or "agent"),
            sender=str(message.get("sender") or "orchestrator"),
            content=str(message.get("content") or ""),
            format=str(message.get("format") or "markdown"),
            artifact_ids=artifact_ids,
            generation_group_id=run_id,
            generation_index=1,
            trace_events=trace_events,
        )
        for message in raw_messages
    ]
    return {
        "run_id": run_id,
        "status": status,
        "messages": saved_messages,
        "artifacts": saved_artifacts,
        "events": trace_events,
    }


def parse_workflow_definition(content: str) -> dict:
    stripped = str(content or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError("Workflow content is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Workflow content must be a JSON object")
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Workflow must contain at least one node")
    return payload


def _record_base_events(
    runner: HarnessRunner,
    *,
    workflow_id: str,
    workflow: dict,
    context: RunContext,
    model_provider: str | None,
    model_name: str | None,
) -> None:
    runner._record_event(
        "message.received",
        {
            "conversation_id": context.conversation_id,
            "message_length": len(context.message),
            "regenerate": False,
        },
    )
    runner._record_event(
        "context.loaded",
        {
            "mode": context.mode,
            "history_count": len(context.history),
            "pinned_count": len(context.pinned_context or []),
            "selected_agents": context.selected_agents,
        },
    )
    runner._record_event(
        "model.selected",
        {
            "provider": model_provider or "auto",
            "model_name": model_name or "",
        },
    )
    runner._record_event(
        "attachments.prepared",
        {
            "count": len(context.attachments or []),
            "image_count": len(
                [
                    attachment
                    for attachment in context.attachments or []
                    if str(attachment.get("mime_type", "")).startswith("image/")
                ]
            ),
            "total_bytes": sum(
                int(attachment.get("size") or 0)
                for attachment in context.attachments or []
            ),
        },
    )
    runner._record_event(
        "run.started",
        {
            "conversation_id": context.conversation_id,
            "workflow_id": workflow_id,
        },
    )
    runner._record_event(
        "run.planned",
        {
            "reason": f"workflow execution · {workflow.get('title') or 'Workflow'}",
            "steps": [
                {
                    "id": str(node.get("id") or ""),
                    "agent_id": _node_owner(node),
                    "task": _node_task(node, context.message),
                    "tools": _node_tools(node),
                    "depends_on": _depends_on(node),
                    "can_run_parallel": False,
                }
                for node in workflow.get("nodes", [])
                if isinstance(node, dict)
            ],
        },
    )


def _step_from_node(node: dict) -> PlanStep:
    node_id = str(node.get("id") or "workflow_step")
    node_type = str(node.get("type") or "agent").strip().lower()
    if node_type == "tool":
        tool_ids = _node_tools(node)
        if not tool_ids:
            raise ValueError(f"Workflow tool node {node_id} is missing tool_id")
        agent_id = str(node.get("agent_id") or "orchestrator")
        return PlanStep(
            id=node_id,
            agent_id=agent_id,
            task=_node_task(node, ""),
            tools=tool_ids[:1],
            depends_on=_depends_on(node),
            can_run_parallel=False,
        )

    agent_id = str(node.get("agent_id") or "").strip()
    if not agent_id:
        raise ValueError(f"Workflow agent node {node_id} is missing agent_id")
    return PlanStep(
        id=node_id,
        agent_id=agent_id,
        task=_node_task(node, ""),
        tools=_node_tools(node),
        depends_on=_depends_on(node),
        can_run_parallel=False,
    )


def _execute_tool_node(
    runner: HarnessRunner,
    step: PlanStep,
    context: RunContext,
    prior_artifacts: list[dict],
) -> StepExecutionResult:
    try:
        artifacts = runner._execute_step_tools(step.tools, prior_artifacts, step, context)
    except Exception as exc:
        return StepExecutionResult(
            step_id=step.id,
            agent_id=step.agent_id,
            status="failed",
            messages=[
                {
                    "role": "agent",
                    "sender": step.agent_id,
                    "content": f"Workflow tool node failed: {exc}",
                    "format": "markdown",
                }
            ],
            artifacts=[],
            error=str(exc),
        )
    return StepExecutionResult(
        step_id=step.id,
        agent_id=step.agent_id,
        status="success",
        artifacts=artifacts,
    )


def _context_for_node(base: RunContext, history: list[dict], message: str) -> RunContext:
    return RunContext(
        conversation_id=base.conversation_id,
        message=message,
        history=history,
        selected_agents=base.selected_agents,
        mode=base.mode,
        pinned_context=base.pinned_context,
        conversation_memories=base.conversation_memories,
        conversation_summary=base.conversation_summary,
        attachments=base.attachments,
        tool_preferences=base.tool_preferences,
        workspace_dir=base.workspace_dir,
    )


def _depends_on(node: dict) -> list[str]:
    depends_on = node.get("depends_on")
    if not isinstance(depends_on, list):
        return []
    return [str(item).strip() for item in depends_on if str(item).strip()]


def _node_owner(node: dict) -> str:
    node_type = str(node.get("type") or "agent").strip().lower()
    if node_type == "tool":
        return str(node.get("agent_id") or "orchestrator")
    return str(node.get("agent_id") or "orchestrator")


def _node_task(node: dict, fallback: str) -> str:
    return str(node.get("task") or node.get("prompt") or node.get("label") or fallback or "Run workflow step")


def _node_tools(node: dict) -> list[str]:
    tools = node.get("tools")
    if isinstance(tools, list):
        values = [str(tool_id).strip() for tool_id in tools if str(tool_id).strip()]
        if values:
            return values
    tool_id = str(node.get("tool_id") or "").strip()
    return [tool_id] if tool_id else []


def _workflow_completion_message(workflow: dict, status: str, artifact_count: int) -> str:
    title = str(workflow.get("title") or "Workflow")
    return (
        f"Workflow `{title}` finished with status `{status}`.\n\n"
        f"- Nodes: {len(workflow.get('nodes') or [])}\n"
        f"- Artifacts: {artifact_count}"
    )
