from agenthub_harness.tools.schemas import ToolResult


def ui_builder_tool(prompt: str) -> ToolResult:
    return ToolResult(
        id="art_001",
        type="code",
        title="TodoList.tsx",
        content=(
            f"// generated from: {prompt}\n"
            "export default function TodoList() { return <div>Todo List</div>; }"
        ),
    )
