from agenthub_harness.core.context import RunContext
from agenthub_harness.runtime.orchestrator import Orchestrator


class FakePlannerProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete(self, prompt: str) -> str:
        return self.content


def test_orchestrator_dispatches_explicit_mentions() -> None:
    plan = Orchestrator().plan(
        RunContext(
            conversation_id="conv_demo",
            message="@ui_builder build a settings page",
            history=[],
            selected_agents=[],
        )
    )

    assert plan.reason == "explicit @mention"
    assert [step.agent_id for step in plan.steps] == ["ui_builder"]
    assert plan.steps[0].tools == []


def test_orchestrator_dispatches_explicit_tool_mentions() -> None:
    plan = Orchestrator().plan(
        RunContext(
            conversation_id="conv_demo",
            message="@preview_tool preview the latest artifact",
            history=[],
            selected_agents=[],
        )
    )

    assert plan.reason == "explicit @mention"
    assert [step.agent_id for step in plan.steps] == ["orchestrator"]
    assert plan.steps[0].tools == ["preview_tool"]


def test_orchestrator_auto_dispatches_ui_work_to_builder_and_reviewer() -> None:
    plan = Orchestrator().plan(
        RunContext(
            conversation_id="conv_demo",
            message="Build a React Todo page",
            history=[],
            selected_agents=["orchestrator", "ui_builder", "code_reviewer"],
        )
    )

    assert plan.reason == "rule based auto dispatch"
    assert [step.agent_id for step in plan.steps] == ["ui_builder", "code_reviewer"]
    assert plan.steps[0].tools == ["preview_tool"]
    assert plan.steps[1].depends_on == ["step_ui_builder"]


def test_orchestrator_uses_single_selected_agent_in_single_mode() -> None:
    plan = Orchestrator().plan(
        RunContext(
            conversation_id="conv_demo",
            message="Please help",
            history=[],
            selected_agents=["code_reviewer"],
            mode="single",
        )
    )

    assert plan.reason == "single chat selected agent"
    assert [step.agent_id for step in plan.steps] == ["code_reviewer"]


def test_single_vision_agent_keeps_default_image_tool() -> None:
    plan = Orchestrator().plan(
        RunContext(
            conversation_id="conv_demo",
            message="Analyze this image",
            history=[],
            selected_agents=["vision_agent"],
            mode="single",
            attachments=[
                {
                    "id": "att_img",
                    "type": "image",
                    "mime_type": "image/png",
                }
            ],
        )
    )

    assert [step.agent_id for step in plan.steps] == ["vision_agent"]
    assert plan.steps[0].tools == ["image_reader_tool"]


def test_orchestrator_explicit_multiple_agents_can_run_in_parallel() -> None:
    plan = Orchestrator().plan(
        RunContext(
            conversation_id="conv_demo",
            message="@ui_builder @code_reviewer split this task",
            history=[],
            selected_agents=[],
        )
    )

    assert [step.agent_id for step in plan.steps] == ["ui_builder", "code_reviewer"]
    assert all(step.can_run_parallel for step in plan.steps)
    assert all(not step.depends_on for step in plan.steps)


def test_orchestrator_uses_llm_planner_when_available() -> None:
    plan = Orchestrator(
        planner_provider=FakePlannerProvider(
            """
            {
              "reason": "llm selected codex",
              "steps": [
                {
                  "id": "step_codex",
                  "agent_id": "codex",
                  "task": "Build the React component",
                  "tools": ["ui_builder_tool", "preview_tool"],
                  "depends_on": [],
                  "can_run_parallel": false
                }
              ]
            }
            """
        )
    ).plan(
        RunContext(
            conversation_id="conv_demo",
            message="Build a React settings page",
            history=[],
            selected_agents=["codex"],
        )
    )

    assert plan.reason == "llm selected codex"
    assert [step.agent_id for step in plan.steps] == ["codex"]
    assert plan.steps[0].tools == ["ui_builder_tool", "preview_tool"]


def test_orchestrator_falls_back_when_llm_planner_returns_invalid_json() -> None:
    plan = Orchestrator(planner_provider=FakePlannerProvider("not json")).plan(
        RunContext(
            conversation_id="conv_demo",
            message="Build a React Todo page",
            history=[],
            selected_agents=["orchestrator", "ui_builder", "code_reviewer"],
        )
    )

    assert plan.reason == "rule based auto dispatch"
    assert [step.agent_id for step in plan.steps] == ["ui_builder", "code_reviewer"]
