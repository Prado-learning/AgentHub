def build_code_artifact(artifact_id: str, title: str, content: str, language: str = "tsx") -> dict:
    return {"id": artifact_id, "type": "code", "title": title, "language": language, "content": content}

