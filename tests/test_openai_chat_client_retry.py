from __future__ import annotations

import io
import json
from urllib.error import HTTPError, URLError

import pytest

from agenthub.adapters.openai_chat import client as client_module
from agenthub.adapters.openai_chat.client import OpenAICompatibleProvider


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _FakeUlopen:
    def __init__(self, failures: list[Exception | None]) -> None:
        self.failures = list(failures)
        self.calls = 0

    def __call__(self, request, timeout=None):  # noqa: ANN001, ANN202
        self.calls += 1
        if self.failures:
            failure = self.failures.pop(0)
            if failure is not None:
                raise failure
        return _FakeResponse(json.dumps({"choices": [{"message": {"content": "ok"}}]}))


def _http_error(code: int) -> HTTPError:
    return HTTPError("http://llm.test/v1", code, "error", {}, io.BytesIO(b"boom"))


def _provider(
    monkeypatch,
    failures: list[Exception | None],
    **kwargs,
) -> tuple[OpenAICompatibleProvider, _FakeUlopen]:
    fake = _FakeUlopen(failures)
    monkeypatch.setattr(client_module.request, "urlopen", fake)
    provider = OpenAICompatibleProvider(
        model="test-model",
        api_key="key",
        base_url="http://llm.test/v1",
        max_retries=kwargs.get("max_retries", 2),
        retry_base_seconds=kwargs.get("retry_base_seconds", 0),
    )
    return provider, fake


def test_retries_rate_limit_then_succeeds(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [_http_error(429), _http_error(429)])

    assert provider.complete("hello") == "ok"
    assert fake.calls == 3


def test_retries_server_error_then_succeeds(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [_http_error(503)])

    assert provider.complete("hello") == "ok"
    assert fake.calls == 2


def test_retries_timeout_then_succeeds(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [TimeoutError("too slow")])

    assert provider.complete("hello") == "ok"
    assert fake.calls == 2


def test_retries_connection_error_then_succeeds(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [URLError("connection refused")])

    assert provider.complete("hello") == "ok"
    assert fake.calls == 2


def test_does_not_retry_auth_error(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [_http_error(401)])

    with pytest.raises(RuntimeError, match="HTTP 401"):
        provider.complete("hello")
    assert fake.calls == 1


def test_does_not_retry_bad_request(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [_http_error(400)])

    with pytest.raises(RuntimeError, match="HTTP 400"):
        provider.complete("hello")
    assert fake.calls == 1


def test_raises_after_retries_exhausted(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [_http_error(429)] * 3, max_retries=2)

    with pytest.raises(RuntimeError, match="after 3 attempt"):
        provider.complete("hello")
    assert fake.calls == 3


def test_zero_retries_fails_fast(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [_http_error(429)], max_retries=0)

    with pytest.raises(RuntimeError, match="after 1 attempt"):
        provider.complete("hello")
    assert fake.calls == 1


def test_mock_mode_never_calls_http(monkeypatch) -> None:
    provider, fake = _provider(monkeypatch, [])

    assert provider.model == "test-model"
    mock_provider = OpenAICompatibleProvider(model="mock")
    assert mock_provider.complete("hello").startswith("[mock] mock completion")
    assert fake.calls == 0
