class ToolPolicy:
    """Tool allow-list.

    ``allowed_tools=None`` means no restriction (everything allowed), while an
    explicit empty list denies every tool. Agents whose profile lists no tools
    therefore cannot execute tools at all.
    """

    def __init__(self, allowed_tools: list[str] | None = None) -> None:
        self.allowed_tools = None if allowed_tools is None else set(allowed_tools)

    def allows(self, tool_id: str) -> bool:
        if self.allowed_tools is None:
            return True
        return tool_id in self.allowed_tools
