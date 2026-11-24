from __future__ import annotations

import os
from typing import Callable

from agenthub.adapters.base import AgentAdapter
from agenthub.adapters.claude_code.adapter import ClaudeCodeAdapter
from agenthub.adapters.codex.adapter import CodexAdapter
from agenthub.adapters.mock.adapter import MockAgentAdapter
from agenthub.adapters.opencode.adapter import OpenCodeAdapter
from agenthub.adapters.openai_chat.adapter import OpenAIChatAdapter
from agenthub.agent.definition_loader import load_agent_configs
from agenthub.infrastructure.config.env import env_flag, load_env_file
from agenthub.infrastructure.config.models import ModelSelection, resolve_model_selection
from agenthub.registry import ADAPTER_BUILDERS
from agenthub.skills.loader import load_skills_for_agent


def _configured_skills(agent_id: str, config: dict) -> list[str]:
    skills = load_skills_for_agent(agent_id, config.get("skills"))
    system_prompt = str(config.get("system_prompt") or "").strip()
    if system_prompt:
        return [f"Custom system prompt:\n{system_prompt}", *skills]
    return skills


# Each builder receives the resolved adapter arguments as keyword
# arguments, so the resolution logic stays in one place and adding an
# adapter is one entry here (or one register_adapter call elsewhere).
def _build_codex(**kw) -> CodexAdapter:
    return CodexAdapter(
        agent_id=kw["agent_id"],
        name=kw["name"],
        model=kw["model"],
        api_key=kw["api_key"],
        base_url=kw["base_url"],
        capabilities=kw["capabilities"],
        skills=kw["skills"],
    )


def _build_claude_code(**kw) -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(
        agent_id=kw["agent_id"],
        name=kw["name"],
        capabilities=kw["capabilities"],
        skills=kw["skills"],
    )


def _build_opencode(**kw) -> OpenCodeAdapter:
    return OpenCodeAdapter(
        agent_id=kw["agent_id"],
        name=kw["name"],
        capabilities=kw["capabilities"],
        skills=kw["skills"],
    )


def _build_openai_chat(**kw) -> OpenAIChatAdapter:
    return OpenAIChatAdapter(
        agent_id=kw["agent_id"],
        name=kw["name"],
        model=kw["model"],
        api_key=kw["api_key"],
        base_url=kw["base_url"],
        capabilities=kw["capabilities"],
        skills=kw["skills"],
    )


def _build_mock(**kw) -> MockAgentAdapter:
    return MockAgentAdapter(
        agent_id=kw["agent_id"],
        name=kw["name"],
        capabilities=kw["capabilities"],
        skills=kw["skills"],
    )


_BUILTIN_ADAPTERS: dict[str, Callable[..., AgentAdapter]] = {
    "codex": _build_codex,
    "claude_code": _build_claude_code,
    "opencode": _build_opencode,
    "openai_chat": _build_openai_chat,
    "mock": _build_mock,
}


def adapter_builders() -> dict[str, Callable[..., AgentAdapter]]:
    """Built-in builders, overridable by name through the registry."""
    return {**_BUILTIN_ADAPTERS, **ADAPTER_BUILDERS}


def build_agent_adapters(
    agent_configs: list[dict] | None = None,
    model: str = "mock",
    api_key: str | None = None,
    base_url: str | None = None,
    model_selection_by_agent: dict[str, ModelSelection] | None = None,
) -> dict[str, AgentAdapter]:
    configs = agent_configs or [
        {"id": "orchestrator", "name": "Orchestrator", "adapter": "mock"},
        {"id": "ui_builder", "name": "UI Builder", "adapter": "mock"},
        {"id": "code_reviewer", "name": "Code Reviewer", "adapter": "mock"},
    ]
    builders = adapter_builders()
    adapters: dict[str, AgentAdapter] = {}
    for config in configs:
        agent_id = config["id"]
        agent_model = model_selection_by_agent.get(agent_id) if model_selection_by_agent else None
        resolved_model = agent_model.model_name if agent_model else config.get("model", model)
        resolved_api_key = agent_model.api_key if agent_model else api_key
        resolved_base_url = agent_model.base_url if agent_model else base_url
        adapter_type = config.get("adapter", "mock")
        builder = builders.get(adapter_type)
        if builder is None:
            # A misspelled adapter must fail loudly rather than silently
            # degrade to a mock that looks like a working agent.
            raise ValueError(
                f"Unknown adapter type {adapter_type!r} for agent {agent_id!r}; "
                f"available: {sorted(builders)}"
            )
        adapters[agent_id] = builder(
            agent_id=agent_id,
            name=config.get("name"),
            model=resolved_model,
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            capabilities=config.get("capabilities"),
            skills=_configured_skills(agent_id, config),
        )
    return adapters


def build_agent_adapters_from_env(
    model_provider: str | None = None,
    model_name: str | None = None,
) -> dict[str, AgentAdapter]:
    load_env_file()
    model_selection = resolve_model_selection(model_provider, model_name)
    model = model_selection.model_name
    use_real_llm = env_flag("ENABLE_REAL_LLM")
    default_adapter = "openai_chat" if use_real_llm else "mock"
    configs = load_agent_configs()

    if not configs:
        configs = [
            {"id": "orchestrator", "name": "Orchestrator", "adapter": default_adapter},
            {"id": "ui_builder", "name": "UI Builder", "adapter": default_adapter},
            {"id": "code_reviewer", "name": "Code Reviewer", "adapter": default_adapter},
        ]

    normalized_configs = [
        {
            **config,
            "adapter": config.get("adapter", default_adapter) if use_real_llm else "mock",
        }
        for config in configs
    ]
    explicit_model_selected = bool(model_provider and model_provider != "auto")
    model_selection_by_agent = {}
    if not explicit_model_selected:
        for config in normalized_configs:
            agent_provider = config.get("model_provider")
            if agent_provider:
                model_selection_by_agent[config["id"]] = resolve_model_selection(
                    agent_provider,
                    config.get("model_name"),
                )

    return build_agent_adapters(
        agent_configs=normalized_configs,
        model=model,
        api_key=model_selection.api_key,
        base_url=model_selection.base_url,
        model_selection_by_agent=model_selection_by_agent,
    )

