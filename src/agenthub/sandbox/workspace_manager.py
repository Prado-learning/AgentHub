from pathlib import Path


class WorkspaceManager:
    def __init__(self, root: str = "agent-workspace") -> None:
        self.root = Path(root)

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

