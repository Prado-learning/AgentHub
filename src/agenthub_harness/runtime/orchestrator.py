class Orchestrator:
    def plan(self, message: str) -> list[str]:
        return ["orchestrator", "ui_builder", "code_reviewer"] if message else []

