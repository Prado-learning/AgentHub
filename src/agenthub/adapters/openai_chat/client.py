from __future__ import annotations

import base64
import json
import os
import socket
from pathlib import Path
from urllib.error import HTTPError
from urllib import request


class OpenAICompatibleProvider:
    def __init__(
        self,
        model: str = "mock",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "")).rstrip("/")
        self.timeout = timeout or self._env_timeout()

    def complete(self, prompt: str) -> str:
        if not self.api_key or not self.base_url or self.model == "mock":
            return f"[{self.model}] mock completion for: {prompt}"

        return self._post_chat_completion(
            [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        )

    def complete_with_attachments(self, prompt: str, attachments: list[dict]) -> str:
        image_parts = self._image_parts(attachments)
        if not image_parts:
            return self.complete(prompt)
        if not self.api_key or not self.base_url or self.model == "mock":
            return f"[{self.model}] mock vision completion for: {prompt}"

        return self._post_chat_completion(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *image_parts,
                    ],
                }
            ]
        )

    def _post_chat_completion(self, messages: list[dict]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
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
        except (TimeoutError, socket.timeout) as exc:
            image_count = self._count_image_parts(messages)
            raise RuntimeError(
                "LLM API timed out "
                f"(model={self.model}, timeout={self.timeout}s, "
                f"payload_bytes={len(body)}, image_count={image_count})"
            ) from exc
        data = json.loads(response_body)
        return data["choices"][0]["message"]["content"]

    def _image_parts(self, attachments: list[dict]) -> list[dict]:
        parts: list[dict] = []
        for attachment in attachments:
            mime_type = str(attachment.get("mime_type") or "")
            file_path = Path(str(attachment.get("file_path") or ""))
            if not mime_type.startswith("image/") or not file_path.exists():
                continue
            data_url = (
                f"data:{mime_type};base64,"
                f"{base64.b64encode(file_path.read_bytes()).decode('ascii')}"
            )
            parts.append({"type": "image_url", "image_url": {"url": data_url}})
        return parts

    def _env_timeout(self) -> int:
        try:
            return int(os.environ.get("LLM_TIMEOUT_SECONDS", "120"))
        except ValueError:
            return 120

    def _count_image_parts(self, messages: list[dict]) -> int:
        count = 0
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                count += len([part for part in content if part.get("type") == "image_url"])
        return count


