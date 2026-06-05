from agenthub_harness.tools.schemas import ToolResult


def code_review_tool(code: str) -> ToolResult:
    return ToolResult(
        id="art_002",
        type="review",
        title="Code Review",
        content="- 代码结构清晰\n- 建议增加空状态\n- 建议增加输入校验" if code else "- No code provided",
    )

