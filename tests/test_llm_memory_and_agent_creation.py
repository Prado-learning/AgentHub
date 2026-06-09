from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.services import agent_service, conversation_service
from app.api.services.conversation_store import JsonStore
from app.api.services import agent_creation_service, context_summary_service, memory_service


client = TestClient(app)


class FakeProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete(self, prompt: str) -> str:
        return self.content


def test_llm_summary_persists_real_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        context_summary_service,
        "SUMMARIES",
        JsonStore(tmp_path / "summaries.json"),
    )
    monkeypatch.setattr(
        context_summary_service,
        "build_required_llm_provider",
        lambda *args, **kwargs: (FakeProvider("LLM summary"), "stepfun"),
    )

    history = [
        {"sender": "user", "content": f"message {index}"}
        for index in range(context_summary_service.MAX_HISTORY_MESSAGES_WITHOUT_SUMMARY + 2)
    ]

    summary = context_summary_service.get_or_update_summary("conv_x", history)

    assert summary is not None
    assert summary["content"] == "LLM summary"
    assert summary["source"] == "llm"


def test_llm_memory_extraction_creates_durable_memories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        memory_service,
        "MEMORIES",
        JsonStore(tmp_path / "memories.json"),
    )
    monkeypatch.setattr(
        memory_service,
        "build_required_llm_provider",
        lambda *args, **kwargs: (
            FakeProvider(
                '{"memories":[{"category":"constraint","content":"Do not use mock data","confidence":0.98},'
                '{"category":"goal","content":"Build a Python search algorithm","confidence":0.87}]}'
            ),
            "stepfun",
        ),
    )

    memories = memory_service.extract_memories_with_llm(
        "conv_x",
        {"id": "msg_1", "content": "Please remember this"},
        [{"sender": "user", "content": "We need a real implementation."}],
    )

    assert len(memories) == 2
    assert memories[0]["category"] == "constraint"
    assert memory_service.list_memories("conv_x")


def test_chat_can_create_agent_through_dialog(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_REAL_LLM", "false")
    monkeypatch.setattr(
        conversation_service,
        "CONVERSATIONS",
        JsonStore(tmp_path / "conversations.json"),
    )
    monkeypatch.setattr(
        conversation_service,
        "MESSAGES",
        JsonStore(tmp_path / "messages.json"),
    )
    monkeypatch.setattr(
        agent_service,
        "CUSTOM_AGENTS",
        JsonStore(tmp_path / "custom_agents.json"),
    )
    monkeypatch.setattr(
        agent_creation_service,
        "build_required_llm_provider",
        lambda *args, **kwargs: (
            FakeProvider(
                '{"name":"UI Helper","description":"Builds UI pages","system_prompt":"You are a UI helper.",'
                '"capabilities":["ui","code"],"tools":["preview_tool","file_reader_tool"],"skills":[]}'
            ),
            "stepfun",
        ),
    )

    response = client.post(
        "/chat",
        json={
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "帮我创建一个负责 UI 页面构建的智能体，能预览页面。",
                "format": "markdown",
            },
            "selected_agents": ["orchestrator"],
        },
    )

    assert response.status_code == 200
    assert response.json()["created_agent"]["id"] == "ui_helper"
    agents = client.get("/agents").json()["agents"]
    assert any(agent["id"] == "ui_helper" for agent in agents)
