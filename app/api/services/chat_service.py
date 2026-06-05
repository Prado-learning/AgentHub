from app.api.services.artifact_service import list_mock_artifacts


def build_mock_chat_response(_request: dict) -> dict:
    # TODO Day 2: replace mock response with HarnessRunner
    return {
        "run_id": "run_demo_001",
        "status": "success",
        "messages": [
            {
                "id": "msg_001",
                "role": "agent",
                "sender": "orchestrator",
                "content": "我会先让 UI Builder 生成页面，再让 Code Reviewer 检查。",
                "format": "markdown",
            },
            {
                "id": "msg_002",
                "role": "agent",
                "sender": "ui_builder",
                "content": "已生成 TodoList React 组件。",
                "format": "markdown",
            },
            {
                "id": "msg_003",
                "role": "agent",
                "sender": "code_reviewer",
                "content": "代码结构清晰，建议后续补充空状态和输入校验。",
                "format": "markdown",
            },
        ],
        "artifacts": list_mock_artifacts(),
    }

