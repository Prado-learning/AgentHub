from agenthub.application.chat.send_message import SendMessageUseCase, build_chat_response


def build_mock_chat_response(request: dict) -> dict:
    return build_chat_response(request)


__all__ = ["SendMessageUseCase", "build_chat_response", "build_mock_chat_response"]

