from __future__ import annotations

import os

from agenthub_harness.adapters.base import AgentAdapter
from agenthub_harness.adapters.codex_adapter import CodexAdapter
from agenthub_harness.adapters.mock_adapter import MockAgentAdapter
from agenthub_harness.adapters.openai_chat_adapter import OpenAIChatAdapter
from agenthub_harness.config.loader import load_yaml_config
from agenthub_harness.config.env import env_flag, load_env_file
from agenthub_harness.skills.loader import load_skills_for_agent


def build_agent_adapters(
    agent_configs: list[dict] | None = None,
    model: str = "mock",
) -> dict[str, AgentAdapter]:
    configs = agent_configs or [
        {"id": "orchestrator", "name": "Orchestrator", "adapter": "mock"},
        {"id": "ui_builder", "name": "UI Builder", "adapter": "mock"},
        {"id": "code_reviewer", "name": "Code Reviewer", "adapter": "mock"},
    ]
    adapters: dict[str, AgentAdapter] = {}
    for config in configs:
        agent_id = config["id"]
        adapter_type = config.get("adapter", "mock")
        if adapter_type == "codex":
            adapters[agent_id] = CodexAdapter(
                agent_id=agent_id,
                name=config.get("name"),
                model=config.get("model", model),
                capabilities=config.get("capabilities"),
                skills=load_skills_for_agent(agent_id, config.get("skills")),
            )
        elif adapter_type == "openai_chat":
            adapters[agent_id] = OpenAIChatAdapter(
                agent_id=agent_id,
                name=config.get("name"),
                model=config.get("model", model),
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


def build_agent_adapters_from_env() -> dict[str, AgentAdapter]:
    load_env_file()
    model = os.environ.get("MODEL_NAME", "mock")
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
    return build_agent_adapters(agent_configs=normalized_configs, model=model)
