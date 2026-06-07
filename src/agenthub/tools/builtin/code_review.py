from agenthub.tools.schemas import ToolResult


def code_review_tool(code: str) -> ToolResult:
    return ToolResult(
        id="art_002",
        type="review",
        title="Code Review",
        content=(
            "- Code structure is clear\n"
            "- Add an empty state\n"
            "- Add input validation"
            if code
            else "- No code provided"
        ),
    )

