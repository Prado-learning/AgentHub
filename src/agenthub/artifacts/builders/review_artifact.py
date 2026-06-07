def build_review_artifact(artifact_id: str, title: str, content: str) -> dict:
    return {"id": artifact_id, "type": "review", "title": title, "content": content}

