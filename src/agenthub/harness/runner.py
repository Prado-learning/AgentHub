"""One checkpointable execution engine for chat and workflow plans.

The engine has no dependency on the HTTP application or its persistence services.
Callbacks persist events/checkpoints; callers supply exact-action approvals.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field, replace
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from agenthub.adapters import AgentAdapter, AgentTask, build_agent_adapters
from agenthub.adapters.base import AgentResult
from agenthub.agent.runtime_profile import (
    AgentRuntimeProfile,
    load_agent_runtime_profiles,
)
from agenthub.artifacts.builders.artifact_builder import (
    stamp_artifact,
    tool_result_to_artifact,
)
from agenthub.artifacts.conflict_resolver import resolve_artifact_conflicts
from agenthub.domain.authority import AuthorityTier
from agenthub.domain.plan import Plan, PlanStep
from agenthub.domain.run import RunContext, RunEvent, RunResult
from agenthub.domain.trace import StageTrace
from agenthub.gateway import Gateway, build_default_gateway
from agenthub.gateway.gateway import GatewayDispatch
from agenthub.harness.authority_gate import AuthorityGate, GateAction
from agenthub.harness.control import (
    RunControl,
    RunCancelled,
    BudgetExceeded,
    execution_scope,
)
from agenthub.harness.fallback import FallbackChain
from agenthub.harness.fingerprint import action_fingerprint
from agenthub.harness.limits import RunLimits
from agenthub.harness.permission import ensure_tool_allowed, tool_policy_for
from agenthub.orchestration.rule_planner import Orchestrator, infer_authority
from agenthub.policies import AgentPolicy, SandboxPolicy
from agenthub.sandbox import Sandbox, sandbox_scope
from agenthub.sandbox.manager import SandboxManager
from agenthub.sandbox.profiles import run_spec
from agenthub.tools.executor import ToolExecutor
from agenthub.tools.input_mapper import tool_kwargs_for
from agenthub.harness.tracing import FlowTracer


@dataclass(frozen=True)
class StepExecutionResult:
    step_id: str
    agent_id: str
    status: str
    messages: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    error: str | None = None
    final: bool = False
    authority: AuthorityTier = AuthorityTier.L1_READONLY


def plan_from_dict(value: dict) -> Plan:
    return Plan(
        steps=[
            PlanStep(**{**s, "authority": AuthorityTier(s.get("authority", "L1"))})
            for s in value["steps"]
        ],
        reason=value.get("reason", "saved plan"),
    )


@dataclass
class HarnessRunner:
    planner_provider: Any = None
    mode: str = "mock"
    adapters: dict[str, AgentAdapter] = field(default_factory=build_agent_adapters)
    tool_executor: ToolExecutor = field(default_factory=ToolExecutor)
    limits: RunLimits = field(default_factory=RunLimits)
    events: list[RunEvent] = field(default_factory=list)
    debug_trace: list[StageTrace] = field(default_factory=list)
    agent_profiles: dict[str, AgentRuntimeProfile] = field(
        default_factory=load_agent_runtime_profiles
    )
    agent_policy: AgentPolicy = field(default_factory=AgentPolicy)
    sandbox_policy: SandboxPolicy = field(default_factory=SandboxPolicy)
    fallback: FallbackChain = field(default_factory=FallbackChain)
    tracer: FlowTracer = field(default_factory=FlowTracer)
    gateway: Gateway = field(default_factory=build_default_gateway)
    authority_gate: AuthorityGate = field(default_factory=AuthorityGate)
    control: RunControl = field(default_factory=RunControl)
    sandbox: Sandbox | None = None
    sandbox_manager: SandboxManager | None = None
    on_event: Callable[[RunEvent], None] | None = None
    on_checkpoint: Callable[[dict], None] | None = None
    _current_run_id: str | None = None
    _active_sandbox: Sandbox | None = None
    _event_lock: RLock = field(default_factory=RLock)

    @property
    def max_parallel_steps(self) -> int:
        return self.limits.max_parallel_steps

    def _normalize_step(self, step: PlanStep) -> PlanStep:
        tier = max(
            step.authority, infer_authority(step.tools), key=lambda value: value.value
        )
        if getattr(self.adapters.get(step.agent_id), "side_effecting", False):
            tier = max(tier, AuthorityTier.L2_REVERSIBLE, key=lambda value: value.value)
        return replace(step, authority=tier)

    def run(
        self,
        context: RunContext,
        *,
        plan: Plan | None = None,
        checkpoint: dict | None = None,
        approvals: dict[str, str] | None = None,
        rejected: set[str] | None = None,
        run_id: str | None = None,
    ) -> RunResult:
        checkpoint = checkpoint or {}
        self.control.llm_calls = max(
            self.control.llm_calls, int(checkpoint.get("llm_calls", 0))
        )
        self.control.started = min(
            self.control.started,
            time.monotonic() - float(checkpoint.get("active_elapsed", 0)),
        )
        approvals = approvals or {}
        rejected = rejected or set()
        self._current_run_id = run_id or f"run_{uuid4().hex[:12]}"
        self.events = []
        self.tracer = FlowTracer(enabled=self.tracer.enabled)
        started = time.monotonic()
        self._record_event(
            "run.started",
            {
                "run_id": self._current_run_id,
                "conversation_id": context.conversation_id,
                "resumed": bool(checkpoint),
            },
        )
        self._record_event(
            "context.loaded",
            {
                "history_count": len(context.history),
                "attachment_count": len(context.attachments or []),
                "workspace_dir": context.workspace_dir,
            },
        )
        if plan is None:
            if checkpoint.get("plan"):
                plan = plan_from_dict(checkpoint["plan"])
            else:
                with execution_scope(self.control, self._record_event):
                    plan = Orchestrator(
                        available_agent_ids=[
                            a for a in self.adapters if self.agent_policy.allows(a)
                        ],
                        available_tool_ids=self.tool_executor.registry.list_ids(),
                        agent_profiles=self.agent_profiles,
                        planner_provider=self.planner_provider,
                    ).plan(context)
        expanded = []
        for step in plan.steps:
            effects = [
                t
                for t in step.tools
                if infer_authority([t]) != AuthorityTier.L1_READONLY
            ]
            if step.kind == "agent" and effects:
                prepare_id = step.id + "__prepare"
                expanded.append(
                    replace(
                        step,
                        id=prepare_id,
                        tools=[t for t in step.tools if t not in effects],
                        authority=AuthorityTier.L1_READONLY,
                        can_short_circuit=False,
                    )
                )
                expanded.append(
                    replace(
                        step,
                        kind="tool",
                        tools=effects,
                        depends_on=[prepare_id],
                        can_short_circuit=False,
                    )
                )
            else:
                expanded.append(step)
        plan = Plan(
            steps=[self._normalize_step(s) for s in expanded], reason=plan.reason
        )
        self._validate_plan(plan)
        self._dependency_map = {s.id: s.depends_on for s in plan.steps}
        # Resolved after planning so the sandbox policy can see which
        # authority tiers the plan actually contains.
        self._active_sandbox, owned_sandbox = self._resolve_sandbox(context, plan)
        self._record_event(
            "run.planned",
            {
                "reason": plan.reason,
                "step_count": len(plan.steps),
                "steps": [asdict(s) for s in plan.steps],
            },
        )
        results = {
            key: StepExecutionResult(
                **{**value, "authority": AuthorityTier(value.get("authority", "L1"))}
            )
            for key, value in checkpoint.get("step_results", {}).items()
        }
        pending = {s.id: s for s in plan.steps if s.id not in results}
        confirmations: dict[str, dict] = {}
        inflight: list[str] = []
        final_step = checkpoint.get("final_step")
        forced_status: str | None = None
        executed = int(checkpoint.get("executed_steps", 0))

        def snapshot() -> dict:
            return {
                "plan": asdict(plan),
                "step_results": {key: asdict(value) for key, value in results.items()},
                "pending_confirmations": list(confirmations.values()),
                "inflight_steps": list(inflight),
                "executed_steps": executed,
                "llm_calls": self.control.llm_calls,
                "active_elapsed": time.monotonic() - self.control.started,
                "final_step": final_step,
            }

        def save() -> None:
            if self.on_checkpoint:
                self.on_checkpoint(snapshot())

        try:
            while pending:
                self.control.check()
                ready = [
                    s
                    for s in pending.values()
                    if all(dep in results for dep in s.depends_on)
                ]
                if not ready:
                    raise ValueError("Plan dependencies cannot be resolved")
                executable: list[tuple[PlanStep, RunContext, list[dict]]] = []
                for step in ready:
                    if final_step:
                        result = self._skipped_result(
                            step, "earlier step produced final answer"
                        )
                    elif step.id in rejected:
                        result = self._skipped_result(step, "user rejected action")
                    elif any(results[d].status != "success" for d in step.depends_on):
                        result = self._skipped_result(step, "dependency failed")
                    elif not self.limits.allows_step(executed + len(executable)):
                        result = self._skipped_result(step, "run step limit exceeded")
                    else:
                        result = None
                    if result:
                        results[step.id] = result
                        pending.pop(step.id)
                        self._record_event(
                            "agent.skipped",
                            {
                                "step_id": step.id,
                                "agent_id": step.agent_id,
                                "reason": result.error,
                            },
                        )
                        continue
                    step_context, artifacts = self._dependency_context(
                        step, context, results
                    )
                    verdict = self.authority_gate.before_dispatch(step)
                    if verdict.action == GateAction.REFUSE:
                        results[step.id] = self._failed_result(step, verdict.reason)
                        pending.pop(step.id)
                        self._record_event(
                            "authority.refused",
                            {
                                "step_id": step.id,
                                "agent_id": step.agent_id,
                                "reason": verdict.reason,
                            },
                        )
                        self._completion_event(results[step.id])
                        continue
                    fingerprint = action_fingerprint(
                        step=step,
                        context=step_context,
                        adapter=self.adapters.get(step.agent_id),
                        profile=self.agent_profiles.get(step.agent_id),
                    )
                    if (
                        verdict.action == GateAction.REQUEST_CONFIRMATION
                        and approvals.get(step.id) != fingerprint
                    ):
                        confirmations[step.id] = {
                            "step_id": step.id,
                            "agent_id": step.agent_id,
                            "authority": step.authority.value,
                            "task": step.task,
                            "tools": step.tools,
                            "arguments": {
                                t: tool_kwargs_for(t, artifacts, step, step_context)
                                for t in step.tools
                            },
                            "artifact_count": len(artifacts),
                            "fingerprint": fingerprint,
                            "workspace_dir": context.workspace_dir,
                            "reason": verdict.reason,
                            # What the environment will permit, so an
                            # approval covers the boundary as well as the
                            # intent.
                            "sandbox": self.sandbox_policy.describe(step.authority),
                        }
                        self._record_event(
                            "authority.requires_confirmation", confirmations[step.id]
                        )
                        continue
                    confirmations.pop(step.id, None)
                    executable.append((step, step_context, artifacts))
                if not executable:
                    save()
                    if confirmations:
                        break
                    continue
                # Persist BEFORE dispatch. A crash with in-flight effects is never
                # automatically replayed by the application after restart.
                inflight[:] = [s.id for s, _, _ in executable]
                save()
                parallel = [
                    item
                    for item in executable
                    if item[0].can_run_parallel
                    and item[0].authority == AuthorityTier.L1_READONLY
                ]
                sequential = [item for item in executable if item not in parallel]
                if parallel:
                    self._start_events([s for s, _, _ in parallel])
                    with ThreadPoolExecutor(
                        max_workers=max(1, min(self.max_parallel_steps, len(parallel)))
                    ) as pool:
                        futures = {
                            pool.submit(self._execute_step, s, c, a): s
                            for s, c, a in parallel
                        }
                        completed = {
                            futures[f].id: f.result() for f in as_completed(futures)
                        }
                    for step, _, _ in parallel:
                        results[step.id] = completed[step.id]
                        pending.pop(step.id)
                        inflight.remove(step.id)
                        executed += 1
                        self._completion_event(results[step.id])
                        save()
                for step, step_context, artifacts in sequential:
                    self.control.check()
                    self._start_events([step])
                    results[step.id] = self._execute_step(step, step_context, artifacts)
                    pending.pop(step.id)
                    inflight.remove(step.id)
                    executed += 1
                    self._completion_event(results[step.id])
                    save()
                for result in results.values():
                    if result.final and result.status == "success":
                        if final_step != result.step_id:
                            self._record_event(
                                "run.short_circuit",
                                {
                                    "step_id": result.step_id,
                                    "agent_id": result.agent_id,
                                },
                            )
                        final_step = result.step_id
                self.control.check()
        except RunCancelled:
            forced_status = "cancelled"
            self._record_event("run.cancelled", {"reason": "user cancelled"})
        except BudgetExceeded as exc:
            forced_status = "failed"
            self._record_event("run.failed", {"reason": str(exc)})
        self._release_sandbox(owned_sandbox)
        ordered = [results[s.id] for s in plan.steps if s.id in results]
        raw_artifacts = [a for result in ordered for a in result.artifacts]
        artifacts, conflicts = resolve_artifact_conflicts(raw_artifacts)
        messages = [m for result in ordered for m in result.messages]
        if forced_status:
            confirmations.clear()
        status = forced_status or (
            "waiting_approval" if confirmations else self._run_status(results)
        )
        if final_step and not forced_status and not confirmations:
            status = "success"
        metrics = self._build_run_metrics(plan, results, artifacts)
        metrics["total_cost_ms"] = int((time.monotonic() - started) * 1000)
        self._record_event("run.metrics", metrics)
        self._record_event(
            "run.completed",
            {
                "status": status,
                "conversation_id": context.conversation_id,
                "agent_count": len(ordered),
                "authority_tiers": {s.id: s.authority.value for s in plan.steps},
                "artifact_count": len(artifacts),
                "conflict_count": len(conflicts),
                "pending_confirmation_steps": list(confirmations.values()),
                "requires_user_confirmation": bool(confirmations),
                "short_circuit_step": final_step,
                "short_circuited": bool(final_step),
            },
        )
        messages.append(
            self._summary_message(
                plan_steps=plan.steps,
                step_results=results,
                artifacts=artifacts,
                conflicts=conflicts,
                status=status,
                short_circuited=bool(final_step),
            )
        )
        save()
        self.debug_trace = self.tracer.stages
        return RunResult(
            run_id=self._current_run_id,
            status=status,
            conversation_id=context.conversation_id,
            messages=messages,
            artifacts=artifacts,
            events=list(self.events),
            debug_trace=self.debug_trace,
            checkpoint=snapshot(),
        )

    def _validate_plan(self, plan: Plan) -> None:
        ids = [s.id for s in plan.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate step ids")
        for step in plan.steps:
            if any(dep not in ids or dep == step.id for dep in step.depends_on):
                raise ValueError("Unknown or self-referential dependency")
            if step.kind not in {"input", "agent", "tool"}:
                raise ValueError("Unsupported step kind")
        remaining = {s.id: set(s.depends_on) for s in plan.steps}
        done: set[str] = set()
        while remaining:
            ready = {key for key, deps in remaining.items() if deps <= done}
            if not ready:
                raise ValueError("Cyclic plan dependencies")
            done.update(ready)
            remaining = {
                key: deps for key, deps in remaining.items() if key not in done
            }

    def _dependency_context(
        self, step: PlanStep, context: RunContext, results: dict
    ) -> tuple[RunContext, list[dict]]:
        # Walk all ancestors so a review-only middle step does not erase source artifacts.
        dependency_map = getattr(self, "_dependency_map", {})
        ancestors = set()

        def visit(dep):
            if dep in ancestors:
                return
            for parent in dependency_map.get(dep, []):
                visit(parent)
            ancestors.add(dep)

        for dep in step.depends_on:
            visit(dep)
        messages = [
            m for dep in results if dep in ancestors for m in results[dep].messages
        ]
        artifacts = [
            *context.upstream_artifacts,
            *[a for dep in results if dep in ancestors for a in results[dep].artifacts],
        ]
        # Dependencies transfer exact artifact content; prompt compaction of chat
        # history must not erase the code under review.
        return replace(
            context, history=[*context.history, *messages], upstream_artifacts=artifacts
        ), artifacts

    def _resolve_sandbox(
        self, context: RunContext, plan: Plan
    ) -> tuple[Sandbox | None, bool]:
        """Bind the execution boundary this run's side effects must cross.

        An injected sandbox is used as given — its creator owns the
        lifetime. Otherwise the runner builds one from the run profile,
        tightened to the strictest boundary the sandbox policy demands for
        the plan's tiers, and owns it, which keeps a bare
        ``HarnessRunner`` self-sufficient rather than silently
        unsandboxed.
        """
        if self.sandbox is not None:
            return self.sandbox, False
        manager = self.sandbox_manager or SandboxManager()
        boundary = self.sandbox_policy.strictest(s.authority for s in plan.steps)
        spec = run_spec(
            self._current_run_id,
            conversation_id=context.conversation_id,
            network=boundary.network,
        )
        return manager.create(spec), True

    def _release_sandbox(self, owned: bool) -> None:
        sandbox = self._active_sandbox
        self._active_sandbox = None
        if sandbox is None or not owned:
            return
        try:
            report = sandbox.stop()
        except Exception as exc:  # audit must never break a finished run
            self._record_event("sandbox.report_failed", {"error": str(exc)})
            return
        self._record_event("sandbox.report", report.to_dict())

    def _execute_step(
        self, step: PlanStep, context: RunContext, prior_artifacts: list[dict]
    ) -> StepExecutionResult:
        with (
            execution_scope(self.control, self._record_event),
            sandbox_scope(self._active_sandbox),
            self.tracer.begin_stage(step.id, f"{step.agent_id}:{step.id}") as stage,
        ):
            stage.set_input(
                {
                    "task": step.task,
                    "tools": step.tools,
                    "authority": step.authority.value,
                }
            )
            if not self.agent_policy.allows(step.agent_id):
                return self._failed_result(step, "agent is not allowed")
            try:
                dynamic_artifacts, dynamic_errors, called_tools = [], [], set()
                if step.kind == "input":
                    return StepExecutionResult(step.id, step.agent_id, "success")
                if step.kind == "tool":
                    result = AgentResult(agent_id=step.agent_id)
                else:
                    adapter = self.adapters.get(step.agent_id)
                    if adapter is None:
                        return self._failed_result(step, "adapter not found")
                    task = AgentTask(
                        agent_id=step.agent_id, instruction=step.task, tools=step.tools
                    )
                    from agenthub.runtime.agent_runtime import tool_session

                    safe_tools = [
                        t
                        for t in step.tools
                        if infer_authority([t]) == AuthorityTier.L1_READONLY
                        and tool_policy_for(
                            self.agent_profiles.get(step.agent_id)
                        ).allows(t)
                    ]
                    fields = {
                        "ui_builder_tool": {"prompt": "string"},
                        "workflow_builder_tool": {"prompt": "string"},
                        "code_review_tool": {"code": "string"},
                        "preview_tool": {"code": "string", "title": "string"},
                    }
                    schemas = [
                        {
                            "type": "function",
                            "function": {
                                "name": name,
                                "description": f"Run {name} for this task",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        k: {"type": v}
                                        for k, v in fields.get(name, {}).items()
                                    },
                                    "additionalProperties": False,
                                },
                            },
                        }
                        for name in safe_tools
                    ]

                    def invoke(name, arguments):
                        if name not in safe_tools:
                            raise PermissionError(
                                "Tool was not authorized in this plan"
                            )
                        if set(arguments) - set(fields.get(name, {})):
                            raise ValueError("Unknown tool arguments")
                        if any(
                            not isinstance(v, str) or len(v) > 100000
                            for v in arguments.values()
                        ):
                            raise ValueError("Invalid tool argument")
                        proposed = replace(step, arguments={name: arguments})
                        output, errors = self._execute_step_tools(
                            [name],
                            [*prior_artifacts, *dynamic_artifacts],
                            proposed,
                            context,
                        )
                        dynamic_artifacts.extend(output)
                        dynamic_errors.extend(errors)
                        called_tools.add(name)
                        return {"artifacts": output, "errors": errors}

                    with tool_session(schemas, invoke):
                        result = self._dispatch_adapter(adapter, task, step, context)
                    if result.status != "success":
                        fallback = self.fallback.run(
                            step.agent_id,
                            task,
                            context,
                            result.error or "adapter failed",
                        )
                        if fallback:
                            result = fallback
                self.control.check()
                artifacts = [
                    *dynamic_artifacts,
                    *[
                        stamp_artifact(a, step.agent_id, step.id)
                        for a in result.artifacts
                    ],
                ]
                if result.status != "success":
                    stage.set_error(result.error or "Agent failed")
                    return StepExecutionResult(
                        step.id,
                        step.agent_id,
                        "failed",
                        result.messages,
                        artifacts,
                        result.error,
                        authority=step.authority,
                    )
                tool_artifacts, errors = self._execute_step_tools(
                    [t for t in step.tools if t not in called_tools],
                    [*prior_artifacts, *artifacts],
                    step,
                    context,
                )
                errors = [*dynamic_errors, *errors]
                artifacts.extend(tool_artifacts)
                status = "failed" if errors else "success"
                error = "; ".join(errors) if errors else None
                messages = list(result.messages)
                if error:
                    stage.set_error(error)
                    messages.append(self._error_message(step.agent_id, error))
                final = (
                    step.can_short_circuit
                    and step.authority.auto_executable
                    and status == "success"
                )
                stage.set_final(final)
                stage.set_output({"artifact_count": len(artifacts), "status": status})
                return StepExecutionResult(
                    step.id,
                    step.agent_id,
                    status,
                    messages,
                    artifacts,
                    error,
                    final,
                    step.authority,
                )
            except (RunCancelled, BudgetExceeded):
                raise
            except Exception as exc:
                stage.set_error(str(exc))
                return self._failed_result(step, str(exc))

    def _dispatch_adapter(self, adapter, task, step, context) -> AgentResult:
        result = self.gateway.dispatch(
            adapter,
            GatewayDispatch(
                endpoint=f"adapter:{step.agent_id}",
                task=task,
                context=context,
                cache_ttl_seconds=300
                if getattr(adapter, "cacheable", False)
                and not step.tools
                and step.authority.auto_executable
                else 0,
            ),
        )
        if result.metrics.get("cache_hit"):
            self._record_event(
                "cache.hit", {"step_id": step.id, "agent_id": step.agent_id}
            )
        return result

    def _execute_step_tools(
        self, tool_ids, artifacts, step, context
    ) -> tuple[list[dict], list[str]]:
        produced: list[dict] = []
        errors: list[str] = []
        policy = tool_policy_for(self.agent_profiles.get(step.agent_id))
        for tool_id in tool_ids:
            self.control.check()
            with self.tracer.begin_stage(
                f"{step.id}.{tool_id}", f"tool:{tool_id}"
            ) as stage:
                try:
                    ensure_tool_allowed(step.agent_id, tool_id, policy)
                    kwargs = tool_kwargs_for(
                        tool_id, [*artifacts, *produced], step, context
                    )
                    self._record_event(
                        "tool.started",
                        {
                            "step_id": step.id,
                            "agent_id": step.agent_id,
                            "tool_id": tool_id,
                            "argument_keys": sorted(kwargs),
                        },
                    )
                    result = self.tool_executor.execute(tool_id, **kwargs)
                    self.control.check()
                    produced.append(
                        stamp_artifact(
                            tool_result_to_artifact(result), step.agent_id, step.id
                        )
                    )
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
                    stage.set_output({"artifact_type": result.type})
                except (RunCancelled, BudgetExceeded):
                    raise
                except Exception as exc:
                    errors.append(f"{tool_id}: {exc}")
                    stage.set_error(str(exc))
                    self._record_event(
                        "tool.failed",
                        {
                            "step_id": step.id,
                            "agent_id": step.agent_id,
                            "tool_id": tool_id,
                            "error": str(exc),
                        },
                    )
        return produced, errors

    def _failed_result(self, step, reason):
        return StepExecutionResult(
            step.id,
            step.agent_id,
            "failed",
            [self._error_message(step.agent_id, reason)],
            error=reason,
            authority=step.authority,
        )

    def _skipped_result(self, step, reason):
        return StepExecutionResult(
            step.id, step.agent_id, "skipped", error=reason, authority=step.authority
        )

    def _error_message(self, sender, content):
        return {
            "role": "agent",
            "sender": sender,
            "content": content,
            "format": "markdown",
        }

    def _start_events(self, steps):
        return [
            self._record_event(
                "agent.parallel_started" if len(steps) > 1 else "agent.started",
                {
                    "step_id": s.id,
                    "agent_id": s.agent_id,
                    "task": s.task,
                    "tools": s.tools,
                    "authority": s.authority.value,
                },
            )
            for s in steps
        ]

    def _completion_event(self, result):
        return self._record_event(
            "agent.completed",
            {
                "step_id": result.step_id,
                "agent_id": result.agent_id,
                "status": result.status,
                "error": result.error,
                "requires_user_confirmation": False,
                "artifact_count": len(result.artifacts),
                "authority": result.authority.value,
                "final": result.final,
            },
        )

    def _record_event(self, event_type, payload) -> RunEvent:
        with self._event_lock:
            event = RunEvent(event_type, payload)
            self.events.append(event)
            self.tracer.record_lifecycle(event_type, event_type, payload)
            if self.on_event:
                self.on_event(event)
            return event

    def _build_run_metrics(self, plan, step_results, artifacts):
        statuses = [r.status for r in step_results.values()]
        tiers: dict[str, int] = {}
        agents: dict[str, int] = {}
        for r in step_results.values():
            tiers[r.authority.value] = tiers.get(r.authority.value, 0) + 1
            if r.status != "skipped":
                agents[r.agent_id] = agents.get(r.agent_id, 0) + 1
        usage = [
            e.payload.get("usage", {}) for e in self.events if e.type == "llm.completed"
        ]
        return {
            "run_id": self._current_run_id,
            "steps_planned": len(plan.steps),
            "steps_succeeded": statuses.count("success"),
            "steps_failed": statuses.count("failed"),
            "steps_skipped": statuses.count("skipped"),
            "steps_short_circuited": sum(r.final for r in step_results.values()),
            "llm_calls": sum(e.type == "llm.started" for e in self.events),
            "cache_hits": sum(e.type == "cache.hit" for e in self.events),
            "prompt_tokens": sum(int(u.get("prompt_tokens", 0)) for u in usage),
            "completion_tokens": sum(int(u.get("completion_tokens", 0)) for u in usage),
            "artifact_count": len(artifacts),
            "total_cost_ms": 0,
            "max_stage_cost_ms": max(
                (s.cost_ms for s in self.tracer.stages), default=0
            ),
            "authority_tier_counts": tiers,
            "agent_call_counts": agents,
        }

    def _run_status(self, results):
        statuses = {r.status for r in results.values()}
        if not statuses or statuses == {"success"}:
            return "success"
        return "partial_success" if "success" in statuses else "failed"

    def _summary_message(
        self,
        *,
        plan_steps,
        step_results,
        artifacts,
        conflicts,
        status,
        short_circuited=False,
    ):
        lines = [
            "Orchestrator summary",
            f"Status: {status}",
            f"Artifacts: {len(artifacts)}; conflicts: {len(conflicts)}",
        ]
        for step in plan_steps:
            result = step_results.get(step.id)
            lines.append(
                f"- {step.agent_id}: {result.status if result else 'awaiting approval/dependency'}"
            )
        if status == "waiting_approval":
            lines.append(
                "Review the pending action and confirm to continue. It has not executed."
            )
        return self._error_message("orchestrator", chr(10).join(lines))
