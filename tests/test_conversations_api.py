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


def test_conversations_can_be_moved_to_and_restored_from_trash(
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

    conversation = client.post(
        "/conversations",
        json={"title": "Temporary idea"},
    ).json()["conversation"]

    trash_response = client.patch(f"/conversations/{conversation['id']}/trash")
    assert trash_response.status_code == 200
    assert trash_response.json()["conversation"]["is_trashed"] is True

    active_response = client.get("/conversations")
    assert conversation["id"] not in [
        item["id"] for item in active_response.json()["conversations"]
    ]

    trashed_response = client.get("/conversations", params={"trashed": True})
    assert conversation["id"] in [
        item["id"] for item in trashed_response.json()["conversations"]
    ]

    restore_response = client.patch(f"/conversations/{conversation['id']}/restore")
    assert restore_response.status_code == 200
    assert restore_response.json()["conversation"]["is_trashed"] is False

    restored_active_response = client.get("/conversations")
    assert conversation["id"] in [
        item["id"] for item in restored_active_response.json()["conversations"]
    ]


def test_trashed_conversation_can_be_permanently_deleted(
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

    conversation = client.post(
        "/conversations",
        json={"title": "Remove forever"},
    ).json()["conversation"]
    conversation_service.add_message(
        conversation_id=conversation["id"],
        role="user",
        content="temporary message",
    )

    trash_response = client.patch(f"/conversations/{conversation['id']}/trash")
    assert trash_response.status_code == 200

    delete_response = client.delete(f"/conversations/{conversation['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["conversation"]["id"] == conversation["id"]

    trashed_response = client.get("/conversations", params={"trashed": True})
    assert conversation["id"] not in [
        item["id"] for item in trashed_response.json()["conversations"]
    ]
    assert [
        message
        for message in conversation_service.MESSAGES.read()
        if message.get("conversation_id") == conversation["id"]
    ] == []

    messages_response = client.get(f"/conversations/{conversation['id']}/messages")
    assert messages_response.status_code == 404


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
