from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.api.services import artifact_service, conversation_service
from app.api.services.conversation_store import JsonStore


def _patch_conversation_stores(tmp_path: Path, monkeypatch) -> None:
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


def test_update_is_atomic_under_concurrent_append(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "store.json")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda _: store.update(lambda records: [*records, {"n": 1}]),
                range(100),
            )
        )

    assert len(store.read()) == 100


def test_concurrent_add_message_loses_no_messages(tmp_path: Path, monkeypatch) -> None:
    _patch_conversation_stores(tmp_path, monkeypatch)
    conversation = conversation_service.create_conversation(title="Race", mode="group")
    conversation_id = conversation["id"]

    def _send(index: int) -> dict:
        return conversation_service.add_message(
            conversation_id=conversation_id,
            role="user",
            content=f"message {index}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(_send, range(40)))

    messages = conversation_service.list_messages(conversation_id)
    assert len(messages) == 40
    assert {message["content"] for message in messages} == {
        f"message {index}" for index in range(40)
    }


def test_concurrent_create_conversation_loses_none(tmp_path: Path, monkeypatch) -> None:
    _patch_conversation_stores(tmp_path, monkeypatch)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda index: conversation_service.create_conversation(title=f"c{index}"),
                range(20),
            )
        )

    conversations = conversation_service.list_conversations()
    assert len(conversations) == 21  # 20 created + 1 seeded default


def test_concurrent_save_artifacts_loses_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        artifact_service,
        "ARTIFACTS",
        JsonStore(tmp_path / "artifacts.json"),
    )
    monkeypatch.setattr(
        artifact_service,
        "ARTIFACT_VERSIONS",
        JsonStore(tmp_path / "artifact_versions.json"),
    )

    def _save(index: int) -> list[dict]:
        return artifact_service.save_artifacts(
            conversation_id="conv_race",
            run_id=f"run_{index}",
            artifacts=[
                {
                    "id": "art",
                    "type": "review",
                    "title": f"review {index}",
                    "content": f"content {index}",
                }
            ],
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(_save, range(20)))

    assert len(artifact_service.list_artifacts()) == 20
    assert len(artifact_service.ARTIFACT_VERSIONS.read()) == 20
