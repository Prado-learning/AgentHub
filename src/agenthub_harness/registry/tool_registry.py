class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, object] = {}

    def register(self, tool_id: str, tool: object) -> None:
        self._tools[tool_id] = tool

    def get(self, tool_id: str) -> object | None:
        return self._tools.get(tool_id)

    def list_ids(self) -> list[str]:
        return list(self._tools)

