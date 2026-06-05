from agenthub_harness import HarnessRunner
from agenthub_harness.core.context import RunContext


def main() -> None:
    runner = HarnessRunner()
    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="Build a Todo List page",
            selected_agents=["orchestrator", "ui_builder", "code_reviewer"],
        )
    )
    print(result)


if __name__ == "__main__":
    main()

