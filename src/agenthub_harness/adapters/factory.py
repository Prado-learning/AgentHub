from __future__ import annotations

import os

from agenthub_harness.adapters.base import AgentAdapter
from agenthub_harness.adapters.codex_adapter import CodexAdapter
from agenthub_harness.adapters.mock_adapter import MockAgentAdapter
from agenthub_harness.adapters.openai_chat_adapter import OpenAIChatAdapter
from agenthub_harness.config.loader import load_yaml_config
from agenthub_harness.config.env import env_flag, load_env_file
from agenthub_harness.config.models import ModelSelection, resolve_model_selection
from agenthub_harness.skills.loader import load_skills_for_agent


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
    adapters: dict[str, AgentAdapter] = {}
    for config in configs:
        agent_id = config["id"]
        agent_model = model_selection_by_agent.get(agent_id) if model_selection_by_agent else None
        resolved_model = agent_model.model_name if agent_model else config.get("model", model)
        resolved_api_key = agent_model.api_key if agent_model else api_key
        resolved_base_url = agent_model.base_url if agent_model else base_url
        adapter_type = config.get("adapter", "mock")
        if adapter_type == "codex":
            adapters[agent_id] = CodexAdapter(
                agent_id=agent_id,
                name=config.get("name"),
                model=resolved_model,
                api_key=resolved_api_key,
                base_url=resolved_base_url,
                capabilities=config.get("capabilities"),
                skills=load_skills_for_agent(agent_id, config.get("skills")),
            )
        elif adapter_type == "openai_chat":
            adapters[agent_id] = OpenAIChatAdapter(
                agent_id=agent_id,
                name=config.get("name"),
                model=resolved_model,
                api_key=resolved_api_key,
                base_url=resolved_base_url,
                capabilities=config.get("capabilities"),
                skills=load_skills_for_agent(agent_id, config.get("skills")),
            )
        else:
            adapters[agent_id] = MockAgentAdapter(
                agent_id=agent_id,
                name=config.get("name"),
                capabilities=config.get("capabilities"),
                skills=load_skills_for_agent(agent_id, config.get("skills")),
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
    try:
        configs = load_yaml_config("app/configs/agent.yaml").get("agents", [])
    except FileNotFoundError:
        configs = []

    if not configs:
        configs = [
            {"id": "orchestrator", "name": "Orchestrator", "adapter": default_adapter},
            {"id": "ui_builder", "name": "UI Builder", "adapter": default_adapter},
            {"id": "code_reviewer", "name": "Code Reviewer", "adapter": default_adapter},
        ]

    normalized_configs = [
        {
            **config,
            "adapter": (
                config.get("adapter", default_adapter)
                if config.get("adapter") == "codex"
                else default_adapter
            ),
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
