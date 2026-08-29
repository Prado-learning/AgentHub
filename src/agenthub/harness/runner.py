"""Multi-agent run execution.

The HarnessRunner owns execution: scheduling plan steps (parallel where
allowed), invoking agent adapters, enforcing permissions and run limits,
degrading through fallback adapters, and aggregating artifacts. Planning
itself lives in ``agenthub.orchestration``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from uuid import uuid4

from agenthub.adapters import AgentAdapter, AgentTask, build_agent_adapters
from agenthub.adapters.base import AgentResult
from agenthub.application.agents.runtime_profile import (
    AgentRuntimeProfile,
    load_agent_runtime_profiles,
)
from agenthub.artifacts.builders.artifact_builder import (
    stamp_artifact,
    tool_result_to_artifact,
)
from agenthub.artifacts.conflict_resolver import resolve_artifact_conflicts
from agenthub.domain.plan import PlanStep
from agenthub.domain.run import RunContext, RunEvent, RunResult
from agenthub.harness.fallback import FallbackChain
from agenthub.harness.limits import RunLimits
from agenthub.harness.permission import ensure_tool_allowed, tool_policy_for
from agenthub.orchestration.rule_planner import Orchestrator
from agenthub.policies import AgentPolicy
from agenthub.tools.executor import ToolExecutor
from agenthub.tools.input_mapper import tool_kwargs_for


@dataclass(frozen=True)
class StepExecutionResult:
    step_id: str
    agent_id: str
    status: str
    messages: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass
class HarnessRunner:
    """Coordinates a complete multi-agent run for one user message."""

    mode: str = "mock"
    adapters: dict[str, AgentAdapter] = field(default_factory=build_agent_adapters)
    tool_executor: ToolExecutor = field(default_factory=ToolExecutor)
    limits: RunLimits = field(default_factory=RunLimits)
    events: list[RunEvent] = field(default_factory=list)
    agent_profiles: dict[str, AgentRuntimeProfile] = field(
        default_factory=load_agent_runtime_profiles
    )
    agent_policy: AgentPolicy = field(default_factory=AgentPolicy)
    fallback: FallbackChain = field(default_factory=FallbackChain)

    @property
    def max_parallel_steps(self) -> int:
        return self.limits.max_parallel_steps

    def run(self, context: RunContext) -> RunResult:
        self.events = []
        run_events = [self._record_event("run.started", {"conversation_id": context.conversation_id})]
        available_agents = [
            agent_id for agent_id in self.adapters if self.agent_policy.allows(agent_id)
        ]
        orchestrator = Orchestrator(
            available_agent_ids=available_agents,
            available_tool_ids=self.tool_executor.registry.list_ids(),
            agent_profiles=self.agent_profiles,
        )
        plan = orchestrator.plan(context)
        run_events.append(
            self._record_event(
                "run.planned",
                {
                    "reason": plan.reason,
                    "steps": [
                        {
                            "id": step.id,
                            "agent_id": step.agent_id,
                            "task": step.task,
                            "tools": step.tools,
                            "depends_on": step.depends_on,
                            "can_run_parallel": step.can_run_parallel,
                        }
                        for step in plan.steps
                    ],
                },
            )
        )

        step_results: dict[str, StepExecutionResult] = {}
        messages: list[dict] = []
        raw_artifacts: list[dict] = []
        pending = {step.id: step for step in plan.steps}
        steps_executed = 0

        while pending:
            ready = [
                step
                for step in pending.values()
                if all(dep in step_results for dep in step.depends_on)
            ]
            if not ready:
                for step in pending.values():
                    result = self._skipped_result(step, "unresolved dependencies")
                    step_results[step.id] = result
                    messages.extend(result.messages)
                    run_events.append(
                        self._record_event(
                            "agent.skipped",
                            {"step_id": step.id, "agent_id": step.agent_id, "reason": result.error},
                        )
                    )
                break

            if not self.limits.allows_step(steps_executed):
                for step in pending.values():
                    result = self._skipped_result(step, "run step limit exceeded")
                    step_results[step.id] = result
                    messages.extend(result.messages)
                    run_events.append(
                        self._record_event(
                            "agent.skipped",
                            {"step_id": step.id, "agent_id": step.agent_id, "reason": result.error},
                        )
                    )
                break

            for step in ready:
                pending.pop(step.id, None)

            blocked = [
                step
                for step in ready
                if any(step_results[dep].status != "success" for dep in step.depends_on)
            ]
            executable = [step for step in ready if step not in blocked]

            for step in blocked:
                result = self._skipped_result(step, "dependency failed")
                step_results[step.id] = result
                messages.extend(result.messages)
                run_events.append(
                    self._record_event(
                        "agent.skipped",
                        {"step_id": step.id, "agent_id": step.agent_id, "reason": result.error},
                    )
                )

            parallel_steps = [
                step for step in executable if step.can_run_parallel and len(executable) > 1
            ]
            sequential_steps = [step for step in executable if step not in parallel_steps]
            steps_executed += len(executable)

            if parallel_steps:
                run_events.extend(self._start_events(parallel_steps))
                with ThreadPoolExecutor(
                    max_workers=min(self.limits.max_parallel_steps, len(parallel_steps))
                ) as executor:
                    futures = {
                        executor.submit(self._execute_step, step, context, [*raw_artifacts]): step
                        for step in parallel_steps
                    }
                    for future in as_completed(futures):
                        result = future.result()
                        step_results[result.step_id] = result
                        messages.extend(result.messages)
                        raw_artifacts.extend(result.artifacts)
                        run_events.append(self._completion_event(result))

            for step in sequential_steps:
                run_events.extend(self._start_events([step]))
                result = self._execute_step(step, context, raw_artifacts)
                step_results[result.step_id] = result
                messages.extend(result.messages)
                raw_artifacts.extend(result.artifacts)
                run_events.append(self._completion_event(result))

        artifacts, conflicts = resolve_artifact_conflicts(raw_artifacts)
        status = self._run_status(step_results)
        run_events.append(
            self._record_event(
                "run.completed",
                {
                    "conversation_id": context.conversation_id,
                    "agent_count": len(plan.steps),
                    "artifact_count": len(artifacts),
                    "conflict_count": len(conflicts),
                    "status": status,
                },
            )
        )
        messages.append(
            self._summary_message(
                plan_steps=plan.steps,
                step_results=step_results,
                artifacts=artifacts,
                conflicts=conflicts,
                status=status,
            )
        )
        return RunResult(
            run_id=f"run_{uuid4().hex[:12]}",
            status=status,
            conversation_id=context.conversation_id,
            messages=messages,
            artifacts=artifacts,
            events=self.events,
        )

    def _execute_step(
        self,
        step: PlanStep,
        context: RunContext,
        prior_artifacts: list[dict],
    ) -> StepExecutionResult:
        adapter = self.adapters.get(step.agent_id)
        if adapter is None:
            return self._failed_result(step, "adapter not found")

        task = AgentTask(agent_id=step.agent_id, instruction=step.task, tools=step.tools)
        try:
            result = adapter.run(task, context)
        except Exception as exc:
            result = AgentResult(agent_id=step.agent_id, status="error", error=str(exc))

        if result.status != "success":
            fallback_result = self.fallback.run(
                step.agent_id, task, context, result.error or "adapter failed"
            )
            if fallback_result is not None and fallback_result.status == "success":
                result = fallback_result

        step_artifacts = [
            stamp_artifact(artifact, step.agent_id, step.id) for artifact in result.artifacts
        ]
        try:
            tool_artifacts = self._execute_step_tools(
                step.tools,
                [*prior_artifacts, *step_artifacts],
                step,
                context,
            )
        except Exception as exc:
            return StepExecutionResult(
                step_id=step.id,
                agent_id=step.agent_id,
                status="failed",
                messages=[
                    *result.messages,
                    self._error_message(step.agent_id, f"Tool execution failed: {exc}"),
                ],
                artifacts=step_artifacts,
                error=str(exc),
            )

        status = "success" if result.status == "success" else "failed"
        messages = result.messages or [
            self._error_message(step.agent_id, result.error or "Agent execution failed")
        ]
        return StepExecutionResult(
            step_id=step.id,
            agent_id=step.agent_id,
            status=status,
            messages=messages,
            artifacts=[*step_artifacts, *tool_artifacts],
            error=result.error,
        )

    def _execute_step_tools(
        self,
        tool_ids: list[str],
        artifacts: list[dict],
        step: PlanStep,
        context: RunContext,
    ) -> list[dict]:
        tool_artifacts: list[dict] = []
        policy = tool_policy_for(self.agent_profiles.get(step.agent_id))
        for tool_id in tool_ids:
            ensure_tool_allowed(step.agent_id, tool_id, policy)
            kwargs = tool_kwargs_for(tool_id, artifacts, step, context)
            self._record_event(
                "tool.started",
                {
                    "step_id": step.id,
                    "agent_id": step.agent_id,
                    "tool_id": tool_id,
                    "argument_keys": sorted(kwargs),
                },
            )
            try:
                result = self.tool_executor.execute(tool_id, **kwargs)
            except Exception as exc:
                self._record_event(
                    "tool.failed",
                    {
                        "step_id": step.id,
                        "agent_id": step.agent_id,
                        "tool_id": tool_id,
                        "error": str(exc),
                    },
                )
                raise
            self._record_event(
                "tool.completed",
                {
                    "step_id": step.id,
                    "agent_id": step.agent_id,
                    "tool_id": tool_id,
                    "artifact_type": result.type,
                    "artifact_title": result.title,
                },
            )
            tool_artifacts.append(stamp_artifact(tool_result_to_artifact(result), step.agent_id, step.id))
        return tool_artifacts

    def _failed_result(self, step: PlanStep, reason: str) -> StepExecutionResult:
        return StepExecutionResult(
            step_id=step.id,
            agent_id=step.agent_id,
            status="failed",
            messages=[self._error_message(step.agent_id, reason)],
            error=reason,
        )

    def _skipped_result(self, step: PlanStep, reason: str) -> StepExecutionResult:
        return StepExecutionResult(
            step_id=step.id,
            agent_id=step.agent_id,
            status="skipped",
            messages=[self._error_message(step.agent_id, f"Skipped: {reason}")],
            error=reason,
        )

    def _error_message(self, sender: str, content: str) -> dict:
        return {"role": "agent", "sender": sender, "content": content, "format": "markdown"}

    def _start_events(self, steps: list[PlanStep]) -> list[RunEvent]:
        event_type = "agent.parallel_started" if len(steps) > 1 else "agent.started"
        return [
            self._record_event(
                event_type,
                {
                    "step_id": step.id,
                    "agent_id": step.agent_id,
                    "task": step.task,
                    "depends_on": step.depends_on,
                },
            )
            for step in steps
        ]

    def _completion_event(self, result: StepExecutionResult) -> RunEvent:
        return self._record_event(
            "agent.completed",
            {
                "step_id": result.step_id,
                "agent_id": result.agent_id,
                "status": result.status,
                "artifact_count": len(result.artifacts),
                "error": result.error,
            },
        )

    def _record_event(self, event_type: str, payload: dict) -> RunEvent:
        event = RunEvent(type=event_type, payload=payload)
        self.events.append(event)
        return event

    def _run_status(self, results: dict[str, StepExecutionResult]) -> str:
        if not results:
            return "success"
        statuses = {result.status for result in results.values()}
        if statuses == {"success"}:
            return "success"
        if "success" in statuses:
            return "partial_success"
        return "failed"

    def _summary_message(
        self,
        *,
        plan_steps: list[PlanStep],
        step_results: dict[str, StepExecutionResult],
        artifacts: list[dict],
        conflicts: list[object],
        status: str,
    ) -> dict:
        agent_lines: list[str] = []
        for step in plan_steps:
            result = step_results.get(step.id)
            state = result.status if result else "pending"
            detail = f"{step.agent_id}: {state}"
            if result and result.error:
                detail = f"{detail} ({result.error})"
            agent_lines.append(f"- {detail}")

        artifact_lines = [
            f"- {artifact.get('type', 'artifact')}: {artifact.get('title') or artifact.get('id')}"
            for artifact in artifacts[:8]
        ]
        if len(artifacts) > 8:
            artifact_lines.append(f"- ... {len(artifacts) - 8} more artifacts")

        content = [
            "Orchestrator summary",
            "",
            f"- Status: {status}",
            f"- Agents completed: {len(step_results)}",
            f"- Artifacts: {len(artifacts)}",
            f"- Conflicts: {len(conflicts)}",
        ]
        if agent_lines:
            content.extend(["", "Agent results:", *agent_lines])
        if artifact_lines:
            content.extend(["", "Artifacts produced:", *artifact_lines])
        if conflicts:
            content.append("")
            content.append("Conflict artifacts were emitted so you can compare candidates before applying changes.")
        content.append("")
        content.append("Review the inline cards below this message or open the artifact panel for details.")
        return {
            "role": "agent",
            "sender": "orchestrator",
            "content": "\n".join(content),
            "format": "markdown",
        }
