import base64
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.services import artifact_service, attachment_service, conversation_service, diff_service
from app.api.services.conversation_store import JsonStore
from agenthub_harness.tools.image_reader_tool import image_reader_tool


client = TestClient(app)


def test_attachment_upload_and_chat_context(tmp_path: Path, monkeypatch) -> None:
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
        attachment_service,
        "ATTACHMENTS",
        JsonStore(tmp_path / "attachments.json"),
    )
    monkeypatch.setattr(attachment_service, "UPLOAD_DIR", tmp_path / "uploads")

    payload = base64.b64encode(b"# Product Brief\nBuild a clean travel page.").decode("ascii")
    response = client.post(
        "/conversations/conv_demo/attachments",
        json={
            "filename": "brief.md",
            "mime_type": "text/markdown",
            "content_base64": payload,
        },
    )

    assert response.status_code == 200
    attachment = response.json()["attachment"]
    assert attachment["type"] == "file"
    assert "Product Brief" in attachment["extracted_text"]

    chat_response = client.post(
        "/chat",
        json={
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "Read this attachment",
                "format": "markdown",
                "attachment_ids": [attachment["id"]],
            },
            "selected_agents": ["orchestrator"],
        },
    )

    assert chat_response.status_code == 200
    assert any(artifact["type"] == "file" for artifact in chat_response.json()["artifacts"])


def test_message_pin_api(tmp_path: Path, monkeypatch) -> None:
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
    message = conversation_service.add_message(
        "conv_demo",
        role="user",
        sender="you",
        content="Remember the brand tone.",
    )

    response = client.patch(f"/conversations/conv_demo/messages/{message['id']}/pin")

    assert response.status_code == 200
    assert response.json()["message"]["is_pinned"] is True
    pinned_response = client.get("/conversations/conv_demo/pinned-messages")
    assert pinned_response.json()["messages"][0]["id"] == message["id"]


def test_apply_diff_artifact(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "app" / "demo.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hello\n", encoding="utf-8")

    monkeypatch.setattr(
        artifact_service,
        "ARTIFACTS",
        JsonStore(tmp_path / "artifacts.json"),
    )
    monkeypatch.setattr(diff_service, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(diff_service, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(
        diff_service,
        "APPLICATIONS",
        JsonStore(tmp_path / "patch_applications.json"),
    )
    artifact_service.ARTIFACTS.write(
        [
            {
                "id": "diff_1",
                "type": "diff",
                "title": "demo patch",
                "content": (
                    "--- a/app/demo.txt\n"
                    "+++ b/app/demo.txt\n"
                    "@@ -1 +1 @@\n"
                    "-hello\n"
                    "+hello agenthub\n"
                ),
            }
        ]
    )

    result = diff_service.apply_diff_artifact("diff_1")

    assert result["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "hello agenthub\n"


def test_image_reader_tool_extracts_png_size(tmp_path: Path) -> None:
    png = tmp_path / "image.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x02\x00\x00\x00\x03"
        b"\x08\x02\x00\x00\x00"
    )

    result = image_reader_tool(
        [
            {
                "id": "att_img",
                "type": "image",
                "filename": "image.png",
                "mime_type": "image/png",
                "size": png.stat().st_size,
                "file_path": str(png),
            }
        ]
    )

    assert result.type == "image"
    assert "2x3" in result.content
