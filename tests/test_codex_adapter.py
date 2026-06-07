from agenthub.adapters import CodexAdapter, build_agent_adapters
from agenthub.adapters.base import AgentTask
from agenthub.domain.run import RunContext


def test_codex_adapter_returns_markdown_and_code_artifact(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_MODE", "mock")
    adapter = CodexAdapter()

    result = adapter.run(
        AgentTask(agent_id="codex", instruction="Build a button"),
        RunContext(
            conversation_id="conv_demo",
            message="Build a button",
            history=[],
            selected_agents=["codex"],
            mode="single",
        ),
    )

    assert result.status == "success"
    assert result.messages[0]["sender"] == "codex"
    assert "```tsx" in result.messages[0]["content"]
    assert result.artifacts[0]["type"] == "code"


def test_factory_builds_codex_adapter_from_config() -> None:
    adapters = build_agent_adapters(
        agent_configs=[
            {
                "id": "codex",
                "name": "Codex",
                "adapter": "codex",
                "capabilities": ["code"],
            }
        ]
    )

    assert isinstance(adapters["codex"], CodexAdapter)

