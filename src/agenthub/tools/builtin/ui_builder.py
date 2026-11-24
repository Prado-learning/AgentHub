from html import escape
from agenthub.tools.schemas import ToolResult


def ui_builder_tool(prompt: str, code: str = "") -> ToolResult:
    """Package upstream generated code; without code emit an explicitly labelled brief."""
    if code:
        return ToolResult(
            id="ui_source", type="code", title="Generated UI", content=code
        )
    return ToolResult(
        id="ui_brief",
        type="document",
        title="UI implementation brief",
        content=(
            "Implementation requested:\n"
            + prompt
            + "\nNo source code was produced by the model. Configure a real model to generate the implementation."
        ),
    )
