class RunPolicy:
    def __init__(self, max_steps: int = 3) -> None:
        self.max_steps = max_steps

    def allows_step(self, step_index: int) -> bool:
        return 0 <= step_index < self.max_steps


