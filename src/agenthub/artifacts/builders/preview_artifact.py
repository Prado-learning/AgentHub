def build_preview_artifact(artifact_id: str, title: str, preview_url: str) -> dict:
    return {"id": artifact_id, "type": "preview", "title": title, "preview_url": preview_url}

