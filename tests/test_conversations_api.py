from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.services import conversation_service
from app.api.services.conversation_store import JsonStore


client = TestClient(app)


def test_conversations_can_be_created_searched_pinned_and_archived(
    tmp_path: Path,
    monkeypatch,
) -> None:
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

    create_response = client.post(
        "/conversations",
        json={
            "title": "Build dashboard",
            "mode": "single",
            "agent_ids": ["ui_builder"],
        },
    )
    assert create_response.status_code == 200
    conversation = create_response.json()["conversation"]
    assert conversation["title"] == "Build dashboard"

    search_response = client.get("/conversations", params={"search": "dashboard"})
    assert search_response.status_code == 200
    assert [item["id"] for item in search_response.json()["conversations"]] == [
        conversation["id"]
    ]

    pin_response = client.patch(f"/conversations/{conversation['id']}/pin")
    assert pin_response.status_code == 200
    assert pin_response.json()["conversation"]["is_pinned"] is True

    archive_response = client.patch(f"/conversations/{conversation['id']}/archive")
    assert archive_response.status_code == 200
    assert archive_response.json()["conversation"]["is_archived"] is True

    active_response = client.get("/conversations")
    assert conversation["id"] not in [
        item["id"] for item in active_response.json()["conversations"]
    ]

    archived_response = client.get("/conversations", params={"archived": True})
    assert conversation["id"] in [
        item["id"] for item in archived_response.json()["conversations"]
    ]


def test_conversation_messages_return_empty_list_for_new_conversation(
    tmp_path: Path,
    monkeypatch,
) -> None:
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

    conversation = client.post("/conversations", json={}).json()["conversation"]
    response = client.get(f"/conversations/{conversation['id']}/messages")

    assert response.status_code == 200
    assert response.json() == {"messages": []}

