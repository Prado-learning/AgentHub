from collections.abc import Callable
from typing import Any

from agenthub_harness.registry.tool_registry import ToolRegistry
from agenthub_harness.tools import code_review_tool, preview_tool, ui_builder_tool
from agenthub_harness.tools.schemas import ToolResult


def execute_tool(tool: Callable[..., Any], **kwargs: Any) -> Any:
    return tool(**kwargs)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or build_default_tool_registry()

    def execute(self, tool_id: str, **kwargs: Any) -> ToolResult:
        tool = self.registry.get(tool_id)
        if tool is None:
            raise KeyError(f"Tool not found: {tool_id}")
        return execute_tool(tool, **kwargs)


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("ui_builder_tool", ui_builder_tool)
    registry.register("code_review_tool", code_review_tool)
    registry.register("preview_tool", preview_tool)
    return registry
