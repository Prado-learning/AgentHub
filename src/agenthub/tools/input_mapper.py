from __future__ import annotations

from agenthub.domain.plan import PlanStep
from agenthub.domain.run import RunContext


def tool_kwargs_for(
    tool_id: str,
    artifacts: list[dict],
    step: PlanStep,
    context: RunContext,
) -> dict:
    latest_code = latest_code_content(artifacts)
    if tool_id == "ui_builder_tool":
        return {"prompt": step.task or context.message}
    if tool_id == "preview_tool":
        return {
            "title": "Generated Preview",
            "code": latest_code or step.task or context.message,
        }
    if tool_id == "deploy_tool":
        preview_html = latest_preview_html(artifacts)
        return {
            "title": "AgentHub Deployment",
            "code": latest_code or step.task or context.message,
            "preview_html": preview_html,
        }
    if tool_id == "code_review_tool":
        return {"code": latest_code or step.task or context.message}
    if tool_id == "file_reader_tool":
        return {"attachments": context.attachments or []}
    if tool_id == "image_reader_tool":
        return {"attachments": context.attachments or []}
    if tool_id == "document_preview_tool":
        return {"attachments": context.attachments or []}
    return {"prompt": step.task or context.message}


def latest_code_content(artifacts: list[dict]) -> str:
    for artifact in reversed(artifacts):
        if artifact.get("type") == "code":
            return str(artifact.get("content", ""))
    return ""


def latest_preview_html(artifacts: list[dict]) -> str:
    for artifact in reversed(artifacts):
        if artifact.get("type") == "preview":
            return str(artifact.get("preview_html", ""))
    return ""

