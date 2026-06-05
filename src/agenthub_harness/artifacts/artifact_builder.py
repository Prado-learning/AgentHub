def build_artifact(artifact_id: str, artifact_type: str, title: str, content: str) -> dict[str, str]:
    return {
        "id": artifact_id,
        "type": artifact_type,
        "title": title,
        "content": content,
    }

