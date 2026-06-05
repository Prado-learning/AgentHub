class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, object] = {}

    def register(self, agent_id: str, agent: object) -> None:
        self._agents[agent_id] = agent

    def get(self, agent_id: str) -> object | None:
        return self._agents.get(agent_id)

    def list_ids(self) -> list[str]:
        return list(self._agents)

