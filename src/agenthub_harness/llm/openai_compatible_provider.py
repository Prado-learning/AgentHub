from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib import request


class OpenAICompatibleProvider:
    def __init__(
        self,
        model: str = "mock",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "")).rstrip("/")
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        if not self.api_key or not self.base_url or self.model == "mock":
            return f"[{self.model}] mock completion for: {prompt}"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0.2,
        }
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM API returned HTTP {exc.code}: {error_body}") from exc
        data = json.loads(response_body)
        return data["choices"][0]["message"]["content"]

