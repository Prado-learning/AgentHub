from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.services import conversation_service
from app.api.services.conversation_store import JsonStore


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_runner_agents_artifacts_and_persists_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
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

    response = client.post(
        "/chat",
        json={
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "甯垜鍋氫竴涓?Todo List 椤甸潰",
                "format": "markdown",
            },
            "selected_agents": ["orchestrator", "ui_builder", "code_reviewer"],
        },
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "success"
    assert len(data["messages"]) == 2
    assert len(data["artifacts"]) == 3
    assert any(event["type"] == "context.loaded" for event in data["events"])
    assert any(event["type"] == "run.planned" for event in data["events"])
    assert any(event["type"] == "agent.completed" for event in data["events"])
    assert data["messages"][0]["trace_events"]
    assert data["messages"][0]["trace_events"][0]["title"]

    history_response = client.get("/conversations/conv_demo/messages")
    history = history_response.json()["messages"]
    assert history_response.status_code == 200
    assert len(history) == 3
    assert history[0]["role"] == "user"
    assert history[-1]["sender"] == "code_reviewer"
    assert history[-1]["trace_events"]


def test_agents_endpoint() -> None:
    response = client.get("/agents")

    assert response.status_code == 200
    agent_ids = [agent["id"] for agent in response.json()["agents"]]
    assert agent_ids[:6] == [
        "orchestrator",
        "codex",
        "ui_builder",
        "code_reviewer",
        "vision_agent",
        "file_analyst",
    ]


def test_models_endpoint() -> None:
    response = client.get("/models")

    assert response.status_code == 200
    assert [model["id"] for model in response.json()["models"]] == [
        "auto",
        "stepfun",
        "deepseek",
        "doubao",
    ]


def test_preview_endpoint_returns_html() -> None:
    response = client.get("/artifacts/art_003/preview")

    assert response.status_code == 200
    assert "Todo List" in response.text

