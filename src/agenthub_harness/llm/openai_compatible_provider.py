class OpenAICompatibleProvider:
    def __init__(self, model: str = "mock") -> None:
        self.model = model

    def complete(self, prompt: str) -> str:
        return f"[{self.model}] mock completion for: {prompt}"

