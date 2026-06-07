from __future__ import annotations

import os
from dataclasses import dataclass

from agenthub.infrastructure.config.env import load_env_file
from agenthub.infrastructure.config.loader import load_yaml_config


@dataclass(frozen=True)
class ModelSelection:
    provider_id: str
    model_name: str
    api_key: str
    base_url: str


def list_model_options() -> list[dict]:
    try:
        return load_yaml_config("app/configs/models.yaml").get("models", [])
    except FileNotFoundError:
        return [
            {"id": "auto", "name": "Auto", "provider": "auto"},
            {"id": "stepfun", "name": "StepFun", "provider": "openai_compatible"},
            {"id": "deepseek", "name": "DeepSeek", "provider": "openai_compatible"},
            {"id": "doubao", "name": "Doubao", "provider": "openai_compatible"},
        ]


def resolve_model_selection(
    provider_id: str | None = None,
    model_name: str | None = None,
) -> ModelSelection:
    load_env_file()
    selected_provider = (provider_id or os.environ.get("DEFAULT_MODEL_PROVIDER") or "auto").strip()
    if selected_provider == "auto":
        selected_provider = os.environ.get("DEFAULT_MODEL_PROVIDER") or "stepfun"

    config = _model_config(selected_provider)
    prefixes = [
        prefix
        for prefix in [
            config.get("env_prefix"),
            config.get("fallback_env_prefix"),
            "OPENAI",
        ]
        if prefix
    ]

    resolved_model = (
        model_name
        or _first_env(prefixes, "MODEL_NAME")
        or os.environ.get("MODEL_NAME")
        or "mock"
    )
    return ModelSelection(
        provider_id=selected_provider,
        model_name=resolved_model,
        api_key=_first_env(prefixes, "API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
        base_url=(
            _first_env(prefixes, "BASE_URL")
            or os.environ.get("OPENAI_BASE_URL", "")
        ),
    )


def _model_config(provider_id: str) -> dict:
    for config in list_model_options():
        if config.get("id") == provider_id:
            return config
    return {"id": provider_id, "env_prefix": provider_id.upper()}


def _first_env(prefixes: list[str], suffix: str) -> str:
    for prefix in prefixes:
        value = os.environ.get(f"{prefix}_{suffix}")
        if value:
            return value
    return ""

