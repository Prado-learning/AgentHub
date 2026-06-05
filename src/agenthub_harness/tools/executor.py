from collections.abc import Callable
from typing import Any


def execute_tool(tool: Callable[..., Any], **kwargs: Any) -> Any:
    return tool(**kwargs)

