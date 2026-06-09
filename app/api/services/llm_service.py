from __future__ import annotations

import json
import re
from typing import Any

from agenthub.adapters.openai_chat.client import OpenAICompatibleProvider
from agenthub.infrastructure.config.models import resolve_model_selection


def build_required_llm_provider(
    model_provider: str | None = None,
    model_name: str | None = None,
) -> tuple[OpenAICompatibleProvider, str]:
    selection = resolve_model_selection(model_provider, model_name)
    if (
        not selection.api_key
        or not selection.base_url
        or not selection.model_name
        or selection.model_name == "mock"
    ):
        raise RuntimeError(
            "A real LLM provider is required. Configure API key, base URL, and model name."
        )
    return (
        OpenAICompatibleProvider(
            model=selection.model_name,
            api_key=selection.api_key,
            base_url=selection.base_url,
        ),
        selection.provider_id,
    )


def complete_json(provider: OpenAICompatibleProvider, prompt: str) -> dict[str, Any]:
    content = provider.complete(prompt).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    payload = json.loads(content[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    return payload
