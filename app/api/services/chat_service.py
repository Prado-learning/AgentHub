"""Thin wrapper around the chat use case.

Adds a single cross-cutting concern that doesn't belong in the
application layer: persist the run snapshot so the front end can fetch
``/runs/{run_id}/debug-trace`` after the chat response is gone.
"""

from __future__ import annotations

import logging

from agenthub.application.chat.send_message import (
    SendMessageUseCase,
    build_chat_response as _build_chat_response,
)
from agenthub.domain.run import RunResult

from app.api.services import run_store


_log = logging.getLogger(__name__)


def _persist_run_result(result: RunResult) -> None:
    try:
        run_store.save_run_result(result.run_id, result)
    except Exception:  # pragma: no cover - defensive, never break chat
        _log.exception("failed to persist run snapshot for %s", result.run_id)


def build_chat_response(request: dict) -> dict:
    """Run the chat use case and persist its ``RunResult`` for later replay.

    Persistence is best-effort: a failing save never bubbles up and
    breaks the chat response.
    """

    return SendMessageUseCase().execute(request, on_run_result=_persist_run_result)


def build_mock_chat_response(request: dict) -> dict:
    return _build_chat_response(request)


__all__ = ["SendMessageUseCase", "build_chat_response", "build_mock_chat_response"]
