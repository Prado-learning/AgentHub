from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.api.services.conversation_store import JsonStore


RUNTIME_DIR = Path("agent-workspace/runtime")
PREVIEW_DIR = Path("agent-workspace/previews")
ARTIFACTS = JsonStore(RUNTIME_DIR / "artifacts.json")


MOCK_ARTIFACTS: dict[str, dict] = {
    "art_001": {
        "id": "art_001",
        "type": "code",
        "title": "TodoList.tsx",
        "language": "tsx",
        "content": "export default function TodoList() { return <div>Todo List</div>; }",
    },
    "art_002": {
        "id": "art_002",
        "type": "review",
        "title": "Code Review",
        "content": "- Code structure is clear\n- Add an empty state\n- Add input validation",
    },
    "art_003": {
        "id": "art_003",
        "type": "preview",
        "title": "Todo List Preview",
        "preview_url": "/artifacts/art_003/preview",
    },
}


def list_mock_artifacts() -> list[dict]:
    return list(MOCK_ARTIFACTS.values())


def save_artifacts(conversation_id: str, run_id: str, artifacts: list[dict]) -> list[dict]:
    if not artifacts:
        return []

    records = ARTIFACTS.read()
    saved: list[dict] = []
    for artifact in artifacts:
        artifact_id = f"{artifact.get('id', 'art')}_{uuid4().hex[:8]}"
        saved_artifact = {
            **artifact,
            "id": artifact_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
        }
        if saved_artifact.get("type") == "preview":
            saved_artifact["preview_url"] = f"/artifacts/{artifact_id}/preview"
            if saved_artifact.get("preview_html"):
                PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
                preview_path = PREVIEW_DIR / f"{artifact_id}.html"
                preview_path.write_text(saved_artifact["preview_html"], encoding="utf-8")
                saved_artifact["preview_file"] = str(preview_path)
        records.append(saved_artifact)
        saved.append(_public_artifact(saved_artifact))
    ARTIFACTS.write(records)
    return saved


def list_artifacts(conversation_id: str | None = None) -> list[dict]:
    records = ARTIFACTS.read()
    if conversation_id:
        records = [
            artifact
            for artifact in records
            if artifact.get("conversation_id") == conversation_id
        ]
    return [_public_artifact(artifact) for artifact in records]


def get_artifact(artifact_id: str) -> dict | None:
    for artifact in ARTIFACTS.read():
        if artifact.get("id") == artifact_id:
            return _public_artifact(artifact)
    return MOCK_ARTIFACTS.get(artifact_id)


def update_artifact(artifact_id: str, updates: dict) -> dict | None:
    records = ARTIFACTS.read()
    for artifact in records:
        if artifact.get("id") != artifact_id:
            continue
        artifact.update(updates)
        ARTIFACTS.write(records)
        return _public_artifact(artifact)
    if artifact_id in MOCK_ARTIFACTS:
        MOCK_ARTIFACTS[artifact_id].update(updates)
        return MOCK_ARTIFACTS[artifact_id]
    return None


def get_preview_html(artifact_id: str) -> str | None:
    for artifact in ARTIFACTS.read():
        if artifact.get("id") == artifact_id and artifact.get("type") == "preview":
            preview_file = artifact.get("preview_file")
            if preview_file and Path(preview_file).exists():
                return Path(preview_file).read_text(encoding="utf-8")
            return artifact.get("preview_html") or _default_preview_html(artifact.get("title", "Preview"))
    if artifact_id != "art_003":
        return None
    return _default_preview_html("Todo List Preview")


def _public_artifact(artifact: dict) -> dict:
    return {
        key: value
        for key, value in artifact.items()
        if key not in {"preview_html", "preview_file"}
    }


def _default_preview_html(title: str) -> str:
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      body {{ font-family: Inter, system-ui, sans-serif; margin: 0; padding: 24px; background: #f7fafc; color: #172033; }}
      .card {{ max-width: 420px; border: 1px solid #d7e1ee; border-radius: 8px; padding: 20px; background: #fff; box-shadow: 0 10px 30px rgba(20, 34, 60, 0.08); }}
      h1 {{ margin: 0 0 16px; font-size: 22px; }}
      ul {{ padding-left: 20px; line-height: 1.8; }}
    </style>
  </head>
  <body>
    <main class="card">
      <h1>{title}</h1>
      <ul>
        <li>Sketch the page layout</li>
        <li>Add empty state</li>
        <li>Validate todo input</li>
      </ul>
    </main>
  </body>
</html>
"""
