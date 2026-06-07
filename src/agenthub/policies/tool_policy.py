class ToolPolicy:
    def __init__(self, allowed_tools: list[str] | None = None) -> None:
        self.allowed_tools = set(allowed_tools or [])

    def allows(self, tool_id: str) -> bool:
        return not self.allowed_tools or tool_id in self.allowed_tools


