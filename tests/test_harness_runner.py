from agenthub_harness import HarnessRunner
from agenthub_harness.core.context import RunContext


def test_harness_runner_accepts_context() -> None:
    runner = HarnessRunner()
    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="hello",
            selected_agents=["orchestrator"],
        )
    )

    assert result["status"] == "queued"
    assert result["conversation_id"] == "conv_demo"
    assert runner.events[0].type == "run.started"

