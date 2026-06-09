import base64
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.services import (
    agent_service,
    artifact_service,
    attachment_service,
    conversation_service,
    context_summary_service,
    diff_service,
    memory_service,
)
from app.api.services.conversation_store import JsonStore
from agenthub.tools.builtin import deploy as deploy_module


client = TestClient(app)


def test_custom_agent_can_be_created_and_listed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        agent_service,
        "CUSTOM_AGENTS",
        JsonStore(tmp_path / "custom_agents.json"),
    )

    response = client.post(
        "/agents",
        json={
            "name": "Test Writer",
            "description": "Writes focused tests.",
            "system_prompt": "Always write concise pytest cases.",
            "capabilities": ["test"],
            "tools": ["file_reader_tool"],
        },
    )

    assert response.status_code == 200
    agent = response.json()["agent"]
    assert agent["id"] == "test_writer"
    assert agent["system_prompt"] == "Always write concise pytest cases."

    listed = client.get("/agents").json()["agents"]
    assert any(item["id"] == "test_writer" and item["is_custom"] for item in listed)


def test_deploy_intent_creates_deployment_artifact(tmp_path: Path, monkeypatch) -> None:
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
        artifact_service,
        "ARTIFACTS",
        JsonStore(tmp_path / "artifacts.json"),
    )
    monkeypatch.setattr(
        artifact_service,
        "ARTIFACT_VERSIONS",
        JsonStore(tmp_path / "artifact_versions.json"),
    )
    monkeypatch.setattr(artifact_service, "PREVIEW_DIR", tmp_path / "previews")
    monkeypatch.setattr(deploy_module, "DEPLOYMENT_DIR", tmp_path / "deployments")

    response = client.post(
        "/chat",
        json={
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "Build a React landing page and deploy it",
                "format": "markdown",
            },
            "selected_agents": ["orchestrator", "ui_builder", "code_reviewer"],
        },
    )

    assert response.status_code == 200
    deployment = next(
        artifact for artifact in response.json()["artifacts"] if artifact["type"] == "deployment"
    )
    assert deployment["status"] == "success"
    assert deployment["preview_url"].startswith("/deployments/")


def test_structured_diff_and_artifact_versions(tmp_path: Path, monkeypatch) -> None:
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
    artifact_service.ARTIFACTS.write(
        [
            {
                "id": "code_1",
                "type": "code",
                "title": "Demo.tsx",
                "language": "tsx",
                "content": "export const value = 1;",
            },
            {
                "id": "diff_1",
                "type": "diff",
                "title": "Patch",
                "content": (
                    "--- a/src/demo.ts\n"
                    "+++ b/src/demo.ts\n"
                    "@@ -1 +1 @@\n"
                    "-export const value = 1;\n"
                    "+export const value = 2;\n"
                ),
            },
        ]
    )

    updated = client.patch(
        "/artifacts/code_1",
        json={"content": "export const value = 2;"},
    )
    assert updated.status_code == 200
    versions = client.get("/artifacts/code_1/versions").json()["versions"]
    assert versions[0]["reason"] == "edited"

    structured = client.get("/artifacts/diff_1/diff")
    assert structured.status_code == 200
    lines = structured.json()["files"][0]["hunks"][0]["lines"]
    assert [line["type"] for line in lines] == ["remove", "add"]


def test_partial_quote_regenerate_and_document_preview(tmp_path: Path, monkeypatch) -> None:
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
        artifact_service,
        "ARTIFACTS",
        JsonStore(tmp_path / "artifacts.json"),
    )
    monkeypatch.setattr(
        artifact_service,
        "ARTIFACT_VERSIONS",
        JsonStore(tmp_path / "artifact_versions.json"),
    )
    monkeypatch.setattr(
        attachment_service,
        "ATTACHMENTS",
        JsonStore(tmp_path / "attachments.json"),
    )
    monkeypatch.setattr(attachment_service, "UPLOAD_DIR", tmp_path / "uploads")

    upload = client.post(
        "/conversations/conv_demo/attachments",
        json={
            "filename": "deck.pptx",
            "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "content_base64": base64.b64encode(b"pptx").decode("ascii"),
        },
    ).json()["attachment"]

    first = client.post(
        "/chat",
        json={
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "Read this file",
                "format": "markdown",
                "quoted_text": "only this sentence",
                "attachment_ids": [upload["id"]],
            },
            "selected_agents": ["file_analyst"],
        },
    )
    assert first.status_code == 200
    artifacts = first.json()["artifacts"]
    assert any(artifact["type"] == "presentation_preview" for artifact in artifacts)

    user_message = client.get("/conversations/conv_demo/messages").json()["messages"][0]
    assert user_message["quoted_text"] == "only this sentence"

    regenerated = client.post(
        "/chat/regenerate",
        json={
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "Read this file",
                "format": "markdown",
            },
            "selected_agents": ["file_analyst"],
            "regenerate_from_message_id": user_message["id"],
        },
    )
    assert regenerated.status_code == 200
    messages = client.get("/conversations/conv_demo/messages").json()["messages"]
    agent_versions = [
        message
        for message in messages
        if message["role"] == "agent" and message.get("generation_group_id") == user_message["id"]
    ]
    assert any(message.get("is_active_generation") is False for message in agent_versions)
    assert max(message.get("generation_index") or 0 for message in agent_versions) >= 2


def test_workflow_artifact_can_be_created_and_run(tmp_path: Path, monkeypatch) -> None:
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
        artifact_service,
        "ARTIFACTS",
        JsonStore(tmp_path / "artifacts.json"),
    )
    monkeypatch.setattr(
        artifact_service,
        "ARTIFACT_VERSIONS",
        JsonStore(tmp_path / "artifact_versions.json"),
    )
    monkeypatch.setattr(
        attachment_service,
        "ATTACHMENTS",
        JsonStore(tmp_path / "attachments.json"),
    )
    monkeypatch.setattr(
        context_summary_service,
        "SUMMARIES",
        JsonStore(tmp_path / "summaries.json"),
    )
    monkeypatch.setattr(
        memory_service,
        "MEMORIES",
        JsonStore(tmp_path / "memories.json"),
    )
    monkeypatch.setattr(artifact_service, "PREVIEW_DIR", tmp_path / "previews")

    conversation = client.post(
        "/conversations",
        json={
            "title": "Workflow Demo",
            "mode": "single",
            "agent_ids": ["orchestrator"],
        },
    ).json()["conversation"]

    created = client.post(
        "/chat",
        json={
            "conversation_id": conversation["id"],
            "message": {
                "role": "user",
                "content": "帮我创建一个网页生成 workflow",
                "format": "markdown",
            },
            "selected_agents": ["orchestrator"],
            "agent_mode": "single",
        },
    )
    assert created.status_code == 200
    workflow = next(
        artifact
        for artifact in created.json()["artifacts"]
        if artifact["type"] == "workflow"
    )

    run_response = client.post(
        f"/artifacts/{workflow['id']}/run",
        json={"model_provider": "auto"},
    )
    assert run_response.status_code == 200
    data = run_response.json()
    assert data["status"] in {"success", "partial_success"}
    assert any(artifact["type"] == "workflow" for artifact in created.json()["artifacts"])
    assert any(artifact["type"] == "code" for artifact in data["artifacts"])
    assert any(artifact["type"] == "preview" for artifact in data["artifacts"])
    assert any(event["type"] == "run.completed" for event in data["events"])
