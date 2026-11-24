"""Extract fenced artifacts without labeling every model answer as TSX."""

import re


def artifacts_from_text(agent_id: str, content: str) -> list[dict]:
    artifacts = []
    extensions = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "jsx": "jsx",
        "tsx": "tsx",
        "html": "html",
        "css": "css",
        "json": "json",
        "sql": "sql",
        "bash": "sh",
        "py": "py",
        "js": "js",
        "ts": "ts",
    }
    for index, match in enumerate(
        re.finditer(r"```([\w-]*)(?:[ \t]+([^\n]+))?\n([\s\S]*?)```", content), 1
    ):
        language, name, body = match.groups()
        language = language.lower()
        if language in {"diff", "patch"}:
            artifacts.append(
                {
                    "id": f"{agent_id}_diff_{index}",
                    "type": "diff",
                    "title": name or "Proposed patch",
                    "content": body.strip(),
                }
            )
        elif language in extensions:
            filename = (name or f"Generated_{index}.{extensions[language]}").strip()
            artifacts.append(
                {
                    "id": f"{agent_id}_code_{index}",
                    "type": "code",
                    "title": filename,
                    "file_path": filename,
                    "language": language,
                    "content": body.strip(),
                }
            )
    if not artifacts and re.search(r"<!doctype\s+html|<html[ >]", content, re.I):
        artifacts.append(
            {
                "id": f"{agent_id}_html",
                "type": "code",
                "title": "index.html",
                "file_path": "index.html",
                "language": "html",
                "content": content,
            }
        )
    return artifacts


def upstream_context(context) -> str:
    return (
        "\n\n".join(
            f"Artifact {a.get('file_path') or a.get('title') or a.get('id')}:\n{a.get('content', '')}"
            for a in context.upstream_artifacts
        )[:40000]
        or "No upstream artifacts."
    )
