from collections.abc import Callable
from typing import Any

from agenthub.registry import TOOL_FACTORIES
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

# Built-ins first so a registered extension can override one by name
# without editing this module.
_BUILTIN_TOOLS: dict[str, Callable[..., Any]] = {
    "ui_builder_tool": ui_builder_tool,
    "code_review_tool": code_review_tool,
    "preview_tool": preview_tool,
    "deploy_tool": deploy_tool,
    "document_preview_tool": document_preview_tool,
    "file_reader_tool": file_reader_tool,
    "image_reader_tool": image_reader_tool,
    "workflow_builder_tool": workflow_builder_tool,
}


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
    for tool_id, factory in {**_BUILTIN_TOOLS, **TOOL_FACTORIES}.items():
        registry.register(tool_id, factory)
    return registry
