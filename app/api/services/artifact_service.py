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
        "content": "- 代码结构清晰\n- 建议增加空状态\n- 建议增加输入校验",
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


def get_artifact(artifact_id: str) -> dict | None:
    return MOCK_ARTIFACTS.get(artifact_id)


def get_preview_html(artifact_id: str) -> str | None:
    if artifact_id != "art_003":
        return None
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Todo List Preview</title>
    <style>
      body { font-family: Inter, system-ui, sans-serif; margin: 0; padding: 24px; background: #f7fafc; color: #172033; }
      .card { max-width: 420px; border: 1px solid #d7e1ee; border-radius: 8px; padding: 20px; background: #fff; box-shadow: 0 10px 30px rgba(20, 34, 60, 0.08); }
      h1 { margin: 0 0 16px; font-size: 22px; }
      ul { padding-left: 20px; line-height: 1.8; }
    </style>
  </head>
  <body>
    <main class="card">
      <h1>Todo List</h1>
      <ul>
        <li>Sketch the page layout</li>
        <li>Add empty state</li>
        <li>Validate todo input</li>
      </ul>
    </main>
  </body>
</html>
"""

