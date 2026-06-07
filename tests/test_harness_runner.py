from agenthub import HarnessRunner
from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.domain.run import RunContext
from agenthub.domain.run import RunResult


def test_harness_runner_accepts_context() -> None:
    runner = HarnessRunner()
    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="hello",
            history=[],
            selected_agents=["orchestrator"],
        )
    )

    assert isinstance(result, RunResult)
    assert result.status == "success"
    assert result.conversation_id == "conv_demo"
    assert result.messages[0]["sender"] == "orchestrator"
    assert runner.events[0].type == "run.started"


def test_harness_runner_dispatches_ui_request_through_adapters() -> None:
    runner = HarnessRunner()
    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="Build a React Todo page",
            history=[],
            selected_agents=["orchestrator", "ui_builder", "code_reviewer"],
        )
    )

    assert [message["sender"] for message in result.messages] == [
        "ui_builder",
        "code_reviewer",
    ]
    assert [artifact["type"] for artifact in result.artifacts] == [
        "code",
        "preview",
        "review",
    ]
    assert result.events[1].payload["steps"][0]["tools"] == ["preview_tool"]
    assert "run.planned" in [event.type for event in result.events]


class FailingAdapter:
    id = "orchestrator"
    name = "Failing"
    capabilities = ["text"]

    def run(self, task: AgentTask, context: RunContext) -> AgentResult:
        raise RuntimeError("boom")


def test_harness_runner_uses_fallback_when_adapter_fails() -> None:
    runner = HarnessRunner(adapters={"orchestrator": FailingAdapter()})
    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="hello",
            history=[],
            selected_agents=["orchestrator"],
        )
    )

    assert result.status == "success"
    assert "Primary adapter failed" in result.messages[0]["content"]


def test_harness_runner_marks_parallel_agent_events() -> None:
    runner = HarnessRunner()
    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="@ui_builder @code_reviewer split this task",
            history=[],
            selected_agents=[],
        )
    )

    assert "agent.parallel_started" in [event.type for event in result.events]


def test_harness_runner_maps_prompt_for_ui_builder_tool_mentions() -> None:
    runner = HarnessRunner()
    result = runner.run(
        RunContext(
            conversation_id="conv_demo",
            message="@ui_builder_tool build a profile card",
            history=[],
            selected_agents=[],
        )
    )

    assert result.status == "success"
    assert any(artifact["type"] == "code" for artifact in result.artifacts)
    assert "build a profile card" in result.artifacts[0]["content"]


