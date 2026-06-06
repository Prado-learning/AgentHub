from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from agenthub_harness.config.env import env_flag, load_env_file
from agenthub_harness.core.context import RunContext
from agenthub_harness.llm.openai_compatible_provider import OpenAICompatibleProvider
from agenthub_harness.tools.executor import build_default_tool_registry


@dataclass(frozen=True)
class PlanStep:
    id: str
    agent_id: str
    task: str
    tools: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    can_run_parallel: bool = True


@dataclass(frozen=True)
class Plan:
    steps: list[PlanStep]
    reason: str


class Orchestrator:
    def __init__(
        self,
        available_agent_ids: list[str] | None = None,
        available_tool_ids: list[str] | None = None,
        planner_provider: Any | None = None,
    ) -> None:
        self.available_agent_ids = available_agent_ids or [
            "orchestrator",
            "codex",
            "ui_builder",
            "code_reviewer",
        ]
        self.available_tool_ids = available_tool_ids or build_default_tool_registry().list_ids()
        self.planner_provider = planner_provider

    def plan(self, context: RunContext) -> Plan:
        message = context.message.strip()
        if not message:
            return Plan(steps=[], reason="empty message")

        mentions = self._extract_mentions(message)
        if mentions["agents"] or mentions["tools"]:
            return self._plan_explicit_mentions(message, mentions)

        if context.mode == "single" and context.selected_agents:
            agent_id = context.selected_agents[0]
            return Plan(
                steps=[self._build_step("step_1", agent_id, message, explicit_tools=[])],
                reason="single chat selected agent",
            )

        llm_plan = self._plan_with_llm(context)
        if llm_plan is not None:
            return llm_plan

        return Plan(
            steps=self._build_auto_steps(message),
            reason="rule based auto dispatch",
        )

    def _plan_explicit_mentions(self, message: str, mentions: dict[str, list[str]]) -> Plan:
        agents = mentions["agents"] or ["orchestrator"]
        steps: list[PlanStep] = []
        for index, agent_id in enumerate(agents, start=1):
            tools = mentions["tools"] if index == 1 else []
            steps.append(
                self._build_step(
                    f"step_{index}",
                    agent_id,
                    message,
                    explicit_tools=tools,
                )
            )
        return Plan(steps=steps, reason="explicit @mention")

    def _build_auto_steps(self, message: str) -> list[PlanStep]:
        intents = self._classify_intents(message)
        steps: list[PlanStep] = []

        if "ui_generation" in intents:
            steps.append(
                self._build_step(
                    "step_ui_builder",
                    "ui_builder",
                    message,
                    explicit_tools=["preview_tool"],
                )
            )

        if "code_review" in intents:
            depends_on = ["step_ui_builder"] if steps else []
            steps.append(
                self._build_step(
                    "step_code_reviewer",
                    "code_reviewer",
                    message,
                    explicit_tools=["code_review_tool"],
                    depends_on=depends_on,
                    can_run_parallel=not depends_on,
                )
            )

        if "preview" in intents and "ui_generation" not in intents:
            steps.append(
                self._build_step(
                    "step_preview",
                    "orchestrator",
                    message,
                    explicit_tools=["preview_tool"],
                )
            )

        if not steps:
            steps.append(self._build_step("step_orchestrator", "orchestrator", message))

        return [
            step
            for step in steps
            if step.agent_id in self.available_agent_ids
        ]

    def _plan_with_llm(self, context: RunContext) -> Plan | None:
        load_env_file()
        if self.planner_provider is None and not env_flag("ENABLE_LLM_PLANNER"):
            return None

        provider = self.planner_provider or OpenAICompatibleProvider(
            model="mock" if env_flag("ENABLE_LLM_PLANNER_MOCK") else "gpt-4.1-mini"
        )
        prompt = self._planner_prompt(context)
        try:
            raw_content = provider.complete(prompt)
            payload = self._extract_json_object(raw_content)
            return self._plan_from_payload(payload)
        except Exception:
            return None

    def _planner_prompt(self, context: RunContext) -> str:
        history = "\n".join(
            f"{item.get('sender') or item.get('role')}: {item.get('content')}"
            for item in context.history[-8:]
        )
        return (
            "You are AgentHub Orchestrator. Return only JSON, no markdown.\n"
            "Plan how to answer the current user message with available agents and tools.\n"
            f"Available agents: {', '.join(self.available_agent_ids)}\n"
            f"Available tools: {', '.join(self.available_tool_ids)}\n"
            f"Selected agents: {', '.join(context.selected_agents) or 'none'}\n"
            f"Conversation mode: {context.mode}\n"
            f"Recent history:\n{history}\n\n"
            f"User message:\n{context.message}\n\n"
            "JSON schema:\n"
            '{"reason":"...","steps":[{"id":"step_1","agent_id":"codex",'
            '"task":"...","tools":["preview_tool"],"depends_on":[],'
            '"can_run_parallel":false}]}'
        )

    def _extract_json_object(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Planner response did not contain a JSON object")
        payload = json.loads(stripped[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Planner response must be a JSON object")
        return payload

    def _plan_from_payload(self, payload: dict[str, Any]) -> Plan:
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("Planner steps must be a list")

        steps: list[PlanStep] = []
        seen_step_ids: set[str] = set()
        for index, item in enumerate(raw_steps, start=1):
            if not isinstance(item, dict):
                continue

            agent_id = str(item.get("agent_id", "")).strip()
            if agent_id not in self.available_agent_ids:
                continue

            step_id = str(item.get("id") or f"step_{index}").strip()
            if not step_id or step_id in seen_step_ids:
                step_id = f"step_{index}"

            tools = [
                str(tool_id)
                for tool_id in item.get("tools", [])
                if str(tool_id) in self.available_tool_ids
            ]
            depends_on = [
                str(dep)
                for dep in item.get("depends_on", [])
                if str(dep) in seen_step_ids
            ]
            steps.append(
                PlanStep(
                    id=step_id,
                    agent_id=agent_id,
                    task=str(item.get("task") or ""),
                    tools=tools,
                    depends_on=depends_on,
                    can_run_parallel=bool(item.get("can_run_parallel", True)),
                )
            )
            seen_step_ids.add(step_id)

        if not steps:
            raise ValueError("Planner returned no usable steps")

        return Plan(
            steps=steps,
            reason=str(payload.get("reason") or "llm planner"),
        )

    def _build_step(
        self,
        step_id: str,
        agent_id: str,
        message: str,
        explicit_tools: list[str] | None = None,
        depends_on: list[str] | None = None,
        can_run_parallel: bool = True,
    ) -> PlanStep:
        tools = explicit_tools if explicit_tools is not None else self._tools_for(agent_id)
        return PlanStep(
            id=step_id,
            agent_id=agent_id,
            task=self._task_for(agent_id, message),
            tools=[tool_id for tool_id in tools if tool_id in self.available_tool_ids],
            depends_on=depends_on or [],
            can_run_parallel=can_run_parallel,
        )

    def _extract_mentions(self, message: str) -> dict[str, list[str]]:
        mentioned = re.findall(r"@([A-Za-z0-9_]+)", message)
        agents = [
            agent_id
            for agent_id in self.available_agent_ids
            if agent_id in mentioned and agent_id != "orchestrator"
        ] or [
            agent_id for agent_id in self.available_agent_ids if agent_id in mentioned
        ]
        tools = [tool_id for tool_id in self.available_tool_ids if tool_id in mentioned]
        return {"agents": agents, "tools": tools}

    def _classify_intents(self, message: str) -> set[str]:
        lowered = message.lower()
        intents: set[str] = set()
        if self._contains_any(
            lowered,
            [
                "react",
                "component",
                "frontend",
                "page",
                "ui",
                "todo",
                "dashboard",
                "form",
                "页面",
                "组件",
                "前端",
                "界面",
                "表单",
            ],
        ):
            intents.add("ui_generation")
        if self._contains_any(lowered, ["review", "check", "审查", "检查", "优化"]):
            intents.add("code_review")
        if self._contains_any(lowered, ["preview", "预览", "展示"]):
            intents.add("preview")
        if self._contains_any(lowered, ["file", "upload", "读取", "文件"]):
            intents.add("file_task")
        if self._contains_any(lowered, ["deploy", "部署", "发布"]):
            intents.add("deploy")
        if "ui_generation" in intents and "code_review" not in intents:
            intents.add("code_review")
        return intents or {"text_answer"}

    def _task_for(self, agent_id: str, message: str) -> str:
        if agent_id == "ui_builder":
            return f"Build the requested UI/code artifact: {message}"
        if agent_id == "code_reviewer":
            return f"Review the generated or described code: {message}"
        if agent_id == "orchestrator":
            return f"Respond to the user and coordinate next steps: {message}"
        return message

    def _tools_for(self, agent_id: str) -> list[str]:
        if agent_id == "ui_builder":
            return ["preview_tool"]
        if agent_id == "code_reviewer":
            return ["code_review_tool"]
        return []

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)
