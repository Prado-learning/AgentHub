from __future__ import annotations

import json
import re

from agenthub.tools.schemas import ToolResult


def workflow_builder_tool(prompt: str = "") -> ToolResult:
    cleaned_prompt = " ".join(str(prompt or "").split()).strip() or "Create a reusable workflow."
    workflow = _build_workflow_definition(cleaned_prompt)
    title = str(workflow.get("title") or "Generated Workflow")
    return ToolResult(
        id="workflow_result",
        type="workflow",
        title=title,
        content=json.dumps(workflow, ensure_ascii=False, indent=2),
        language="json",
        metadata={
            "file_path": "GeneratedWorkflow.json",
            "workflow_title": title,
            "node_count": len(workflow.get("nodes") or []),
        },
    )


def _build_workflow_definition(prompt: str) -> dict:
    title = _infer_title(prompt)
    nodes: list[dict] = [
        {
            "id": "node_input",
            "type": "input",
            "label": "User Request",
            "prompt": prompt,
        }
    ]

    dependencies = ["node_input"]
    if _contains_any(prompt, ["file", "upload", "附件", "文件", "文档", "需求文档"]):
        nodes.append(
            {
                "id": "node_file_context",
                "type": "agent",
                "label": "Read File Context",
                "agent_id": "file_analyst",
                "task": f"Read the uploaded file context and summarize requirements: {prompt}",
                "tools": ["file_reader_tool", "document_preview_tool"],
                "depends_on": ["node_input"],
            }
        )
        dependencies = ["node_file_context"]

    if _contains_any(prompt, ["image", "picture", "screenshot", "photo", "图片", "截图", "视觉"]):
        nodes.append(
            {
                "id": "node_visual_context",
                "type": "agent",
                "label": "Analyze Visual Input",
                "agent_id": "vision_agent",
                "task": f"Analyze the uploaded image or visual reference: {prompt}",
                "tools": ["image_reader_tool"],
                "depends_on": ["node_input"],
            }
        )
        dependencies = list(dict.fromkeys([*dependencies, "node_visual_context"]))

    build_node_id = "node_main_agent"
    build_agent_id = "codex"
    build_label = "Implement Solution"
    build_task = f"Implement the requested solution: {prompt}"
    build_tools: list[str] = []

    if _contains_any(
        prompt,
        [
            "react",
            "frontend",
            "front-end",
            "ui",
            "page",
            "landing page",
            "html",
            "网页",
            "页面",
            "前端",
            "界面",
        ],
    ):
        build_node_id = "node_ui_builder"
        build_agent_id = "ui_builder"
        build_label = "Build UI"
        build_task = f"Build the requested UI/page and keep it ready for preview: {prompt}"
        build_tools = ["preview_tool"]

    nodes.append(
        {
            "id": build_node_id,
            "type": "agent",
            "label": build_label,
            "agent_id": build_agent_id,
            "task": build_task,
            "tools": build_tools,
            "depends_on": dependencies,
        }
    )

    if _contains_any(prompt, ["review", "qa", "check", "审查", "检查", "优化", "测试"]):
        nodes.append(
            {
                "id": "node_review",
                "type": "agent",
                "label": "Review Output",
                "agent_id": "code_reviewer",
                "task": f"Review the generated implementation and highlight risks or missing tests: {prompt}",
                "tools": ["code_review_tool"],
                "depends_on": [build_node_id],
            }
        )

    if _contains_any(prompt, ["deploy", "publish", "发布", "部署", "上线"]):
        nodes.append(
            {
                "id": "node_deploy",
                "type": "tool",
                "label": "Deploy Preview",
                "tool_id": "deploy_tool",
                "task": "Deploy the latest generated code or preview as a local static page.",
                "depends_on": [build_node_id],
            }
        )

    return {
        "version": 1,
        "kind": "agenthub.workflow",
        "title": title,
        "description": f"Workflow generated from the request: {prompt}",
        "source_prompt": prompt,
        "nodes": nodes,
    }


def _infer_title(prompt: str) -> str:
    stripped = re.sub(r"^[#>*\s]+", "", prompt).strip()
    if not stripped:
        return "Generated Workflow"
    title = re.split(r"[。！？!?\n]", stripped, maxsplit=1)[0].strip()
    title = re.sub(r"\s+", " ", title)
    if len(title) > 48:
        title = f"{title[:45].rstrip()}..."
    return title or "Generated Workflow"


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)
