from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_mock_agents_and_artifacts() -> None:
    response = client.post(
        "/chat",
        json={
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "帮我做一个 Todo List 页面",
                "format": "markdown",
            },
            "selected_agents": ["orchestrator", "ui_builder", "code_reviewer"],
        },
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "success"
    assert len(data["messages"]) == 3
    assert len(data["artifacts"]) == 3


def test_agents_endpoint() -> None:
    response = client.get("/agents")

    assert response.status_code == 200
    assert [agent["id"] for agent in response.json()["agents"]] == [
        "orchestrator",
        "ui_builder",
        "code_reviewer",
    ]


def test_preview_endpoint_returns_html() -> None:
    response = client.get("/artifacts/art_003/preview")

    assert response.status_code == 200
    assert "Todo List" in response.text

