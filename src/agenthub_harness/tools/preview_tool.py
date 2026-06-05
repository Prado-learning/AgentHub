from agenthub_harness.tools.schemas import ToolResult


def preview_tool() -> ToolResult:
    return ToolResult(
        id="art_003",
        type="preview",
        title="Todo List Preview",
        content="/artifacts/art_003/preview",
    )

