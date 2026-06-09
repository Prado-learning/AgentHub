from agenthub.tools import (
    code_review_tool,
    preview_tool,
    ui_builder_tool,
    workflow_builder_tool,
)


def test_mock_tools_return_artifacts() -> None:
    code = ui_builder_tool("todo")
    review = code_review_tool(code.content)
    preview = preview_tool()

    assert code.type == "code"
    assert review.type == "review"
    assert preview.type == "preview"


def test_workflow_builder_tool_returns_editable_workflow_artifact() -> None:
    workflow = workflow_builder_tool("Build a React landing page workflow and deploy it")

    assert workflow.type == "workflow"
    assert workflow.language == "json"
    assert '"type": "agent"' in workflow.content
    assert '"tool_id": "deploy_tool"' in workflow.content

