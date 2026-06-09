from collections.abc import Callable
from typing import Any

from agenthub.tools.builtin.code_review import code_review_tool
from agenthub.tools.builtin.deploy import deploy_tool
from agenthub.tools.builtin.document_preview import document_preview_tool
from agenthub.tools.builtin.file_reader import file_reader_tool
from agenthub.tools.builtin.image_reader import image_reader_tool
from agenthub.tools.builtin.preview import preview_tool
from agenthub.tools.builtin.ui_builder import ui_builder_tool
from agenthub.tools.builtin.workflow_builder import workflow_builder_tool
from agenthub.tools.registry import ToolRegistry
from agenthub.tools.schemas import ToolResult


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
    registry.register("deploy_tool", deploy_tool)
    registry.register("document_preview_tool", document_preview_tool)
    registry.register("file_reader_tool", file_reader_tool)
    registry.register("image_reader_tool", image_reader_tool)
    registry.register("workflow_builder_tool", workflow_builder_tool)
    return registry
