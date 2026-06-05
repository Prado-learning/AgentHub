class AgentPolicy:
    def __init__(self, allowed_agents: list[str] | None = None) -> None:
        self.allowed_agents = set(allowed_agents or [])

    def allows(self, agent_id: str) -> bool:
        return not self.allowed_agents or agent_id in self.allowed_agents

