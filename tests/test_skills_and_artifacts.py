from pathlib import Path

from app.api.services import artifact_service
from app.api.services.conversation_store import JsonStore
from agenthub.skills.loader import load_skills_for_agent


def test_loads_agent_skill_markdown() -> None:
    skills = load_skills_for_agent("ui_builder")

    assert skills
    assert "UI Builder Skill" in skills[0]


def test_artifacts_are_persisted_with_preview_html(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        artifact_service,
        "ARTIFACTS",
        JsonStore(tmp_path / "artifacts.json"),
    )
    monkeypatch.setattr(artifact_service, "PREVIEW_DIR", tmp_path / "previews")

    saved = artifact_service.save_artifacts(
        conversation_id="conv_demo",
        run_id="run_demo",
        artifacts=[
            {
                "id": "art_003",
                "type": "preview",
                "title": "Preview",
                "content": "/artifacts/art_003/preview",
                "preview_html": "<html><body>hello</body></html>",
            }
        ],
    )

    assert saved[0]["preview_url"].startswith("/artifacts/")
    assert "preview_html" not in saved[0]
    assert artifact_service.get_preview_html(saved[0]["id"]) == "<html><body>hello</body></html>"

