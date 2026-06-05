from agenthub_harness.tools import code_review_tool, preview_tool, ui_builder_tool


def test_mock_tools_return_artifacts() -> None:
    code = ui_builder_tool("todo")
    review = code_review_tool(code.content)
    preview = preview_tool()

    assert code.type == "code"
    assert review.type == "review"
    assert preview.type == "preview"

