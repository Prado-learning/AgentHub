from fastapi.testclient import TestClient

from app.api.main import app


def main() -> None:
    client = TestClient(app)
    response = client.post(
        "/chat",
        json={
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "帮我做一个 Todo List 页面",
                "format": "markdown",
            },
            "selected_agents": ["orchestrator", "ui_builder", "code_reviewer"],
        },
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()

