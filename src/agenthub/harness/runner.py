"""Multi-agent run execution.

The HarnessRunner owns execution: scheduling plan steps (parallel where
allowed), invoking agent adapters, enforcing permissions and run limits,
degrading through fallback adapters, and aggregating artifacts. Planning
itself lives in ``agenthub.orchestration``.

Phase 2 / Phase 3 additions (over the article's ``确定性 Harness``):

- Every step runs inside a :class:`FlowTracer` stage; tool calls run
  inside a nested stage. With ``AGENT_DEBUG=0`` (the default) the
  tracer is a no-op and the overhead is a single boolean check.
- Tool failures no longer abort the whole step. They log a
  ``tool.failed`` event and let the rest of the tools run, matching
  the article's "single-step failure does not block the run" rule.
- A step that runs with ``can_short_circuit=True`` (set by the
  planner for single-chat orchestrator calls) marks its result as
  ``final=True`` on success; the main loop then skips every
  remaining pending step with reason ``earlier step produced final
  answer``.
- Adapter calls flow through an injectable :class:`Gateway`. The
  default is :class:`NoopGateway`, a transparent pass-through.
- Each step carries an :class:`AuthorityTier` (``L1/L2/L3``) chosen
  by the planner. The harness records the tier in the trace and in
  the final summary; L2/L3 steps still execute for now (the gate is
  pluggable, not enforced) but the audit trail is in place.
- L2/L3 completions emit an ``authority.requires_confirmation``
  event and flag their ``agent.completed`` payload with
  ``requires_user_confirmation=True``. The ``run.completed`` payload
  carries a ``pending_confirmation_steps`` array so the front end
  can render the approval queue without re-parsing the trace.
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
from agenthub.domain.authority import AuthorityDecision, AuthorityTier
from agenthub.domain.plan import PlanStep
from agenthub.domain.run import RunContext, RunEvent, RunResult
from agenthub.domain.trace import StageTrace
from agenthub.gateway import Gateway, build_default_gateway
from agenthub.harness.authority_gate import AuthorityGate, GateAction, permissive_gate
from agenthub.harness.fallback import FallbackChain
from agenthub.harness.limits import RunLimits
from agenthub.harness.permission import ensure_tool_allowed, tool_policy_for
from agenthub.orchestration.rule_planner import Orchestrator
from agenthub.policies import AgentPolicy
from agenthub.tools.executor import ToolExecutor
from agenthub.tools.input_mapper import tool_kwargs_for
from agenthub.tracing import FlowTracer


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


@dataclass
class HarnessRunner:
    """Coordinates a complete multi-agent run for one user message."""

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
    fallback: FallbackChain = field(default_factory=FallbackChain)
    tracer: FlowTracer = field(default_factory=FlowTracer)
    gateway: Gateway = field(default_factory=build_default_gateway)
    authority_gate: AuthorityGate = field(default_factory=permissive_gate)
    _current_run_id: str | None = None

    @property
    def max_parallel_steps(self) -> int:
        return self.limits.max_parallel_steps

    def run(self, context: RunContext) -> RunResult:
        self.events = []
        self.debug_trace = []
        run_id = f"run_{uuid4().hex[:12]}"
        self._current_run_id = run_id
        run_events = [self._record_event("run.started", {"run_id": run_id, "conversation_id": context.conversation_id})]
        self.tracer.record_lifecycle(
            "run.started",
            "Run started",
            {"run_id": run_id, "conversation_id": context.conversation_id, "mode": context.mode},
        )
        available_agents = [
            agent_id for agent_id in self.adapters if self.agent_policy.allows(agent_id)
        ]
        orchestrator = Orchestrator(
            available_agent_ids=available_agents,
            available_tool_ids=self.tool_executor.registry.list_ids(),
            agent_profiles=self.agent_profiles,
        )
        plan = orchestrator.plan(context)
        planned_payload = {
            "reason": plan.reason,
            "step_count": len(plan.steps),
            "steps": [
                {
                    "id": step.id,
                    "agent_id": step.agent_id,
                    "task": step.task,
                    "tools": step.tools,
                    "depends_on": step.depends_on,
                    "can_run_parallel": step.can_run_parallel,
                    "authority": step.authority.value,
                    "can_short_circuit": step.can_short_circuit,
                }
                for step in plan.steps
            ],
        }
        run_events.append(self._record_event("run.planned", planned_payload))
        self.tracer.record_lifecycle("run.planned", "Run planned", planned_payload)

        step_results: dict[str, StepExecutionResult] = {}
        messages: list[dict] = []
        raw_artifacts: list[dict] = []
        pending = {step.id: step for step in plan.steps}
        steps_executed = 0
        early_final_step: str | None = None

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

            if early_final_step is not None:
                reason = f"earlier step {early_final_step} produced final answer"
                for step in pending.values():
                    result = self._skipped_result(step, reason)
                    step_results[step.id] = result
                    messages.extend(result.messages)
                    run_events.append(
                        self._record_event(
                            "agent.skipped",
                            {"step_id": step.id, "agent_id": step.agent_id, "reason": result.error},
                        )
                    )
                    self.tracer.record_lifecycle(
                        f"agent.skipped.{step.id}",
                        f"Step {step.id} skipped",
                        {"reason": reason, "agent_id": step.agent_id},
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
                        self._maybe_emit_confirmation(futures[future], result)

            for step in sequential_steps:
                run_events.extend(self._start_events([step]))
                result = self._execute_step(step, context, raw_artifacts)
                step_results[result.step_id] = result
                messages.extend(result.messages)
                raw_artifacts.extend(result.artifacts)
                run_events.append(self._completion_event(result))
                self._maybe_emit_confirmation(step, result)

            # IsFinal detection: a successful step whose planner marked
            # ``can_short_circuit=True`` ends the run.
            for result in step_results.values():
                if result.status == "success" and result.final and early_final_step is None:
                    early_final_step = result.step_id
                    self.tracer.record_lifecycle(
                        "run.short_circuit",
                        "Run short-circuited",
                        {"step_id": result.step_id, "agent_id": result.agent_id},
                    )
                    run_events.append(
                        self._record_event(
                            "run.short_circuit",
                            {"step_id": result.step_id, "agent_id": result.agent_id},
                        )
                    )
                    break

        artifacts, conflicts = resolve_artifact_conflicts(raw_artifacts)
        status = self._run_status(step_results)
        pending_confirmation = [
            {
                "step_id": result.step_id,
                "agent_id": result.agent_id,
                "authority": result.authority.value,
                "artifact_count": len(result.artifacts),
            }
            for result in step_results.values()
            if result.status == "success"
            and result.authority != AuthorityTier.L1_READONLY
        ]
        completed_payload = {
            "conversation_id": context.conversation_id,
            "agent_count": len(plan.steps),
            "artifact_count": len(artifacts),
            "conflict_count": len(conflicts),
            "status": status,
            "short_circuited": early_final_step is not None,
            "short_circuit_step": early_final_step,
            "authority_tiers": sorted({r.authority.value for r in step_results.values()}),
            "pending_confirmation_steps": pending_confirmation,
            "requires_user_confirmation": bool(pending_confirmation),
        }
        run_events.append(self._record_event("run.completed", completed_payload))
        self.tracer.record_lifecycle("run.completed", "Run completed", completed_payload)
        run_events.append(
            self._record_event("run.metrics", self._build_run_metrics(plan, step_results, artifacts))
        )
        self.tracer.record_lifecycle(
            "run.metrics",
            "Run metrics",
            self._build_run_metrics(plan, step_results, artifacts),
        )
        messages.append(
            self._summary_message(
                plan_steps=plan.steps,
                step_results=step_results,
                artifacts=artifacts,
                conflicts=conflicts,
                status=status,
                short_circuited=early_final_step is not None,
            )
        )
        stages = self.tracer.stages
        self.debug_trace = stages
        return RunResult(
            run_id=run_id,
            status=status,
            conversation_id=context.conversation_id,
            messages=messages,
            artifacts=artifacts,
            events=self.events,
            debug_trace=stages,
        )

    def _execute_step(
        self,
        step: PlanStep,
        context: RunContext,
        prior_artifacts: list[dict],
    ) -> StepExecutionResult:
        with self.tracer.begin_stage(
            step.id,
            f"{step.agent_id}:{step.id}",
        ) as stage:
            stage.set_input(
                {
                    "task": step.task,
                    "tools": step.tools,
                    "depends_on": step.depends_on,
                    "authority": step.authority.value,
                    "can_short_circuit": step.can_short_circuit,
                }
            )

            # Authority gate: refuse the step outright when the gate
            # says so (e.g. L3 by default). The refusal still gets a
            # trace stage so the decision is auditable.
            gate_decision = self.authority_gate.before_dispatch(step)
            stage.set_branch(f"authority.{gate_decision.action.value}")
            if gate_decision.action is GateAction.REFUSE:
                self._record_event(
                    "authority.refused",
                    {
                        "step_id": step.id,
                        "agent_id": step.agent_id,
                        "authority": step.authority.value,
                        "reason": gate_decision.reason,
                    },
                )
                stage.set_error(gate_decision.reason)
                return StepExecutionResult(
                    step_id=step.id,
                    agent_id=step.agent_id,
                    status="failed",
                    messages=[
                        self._error_message(
                            step.agent_id,
                            f"Refused by authority gate: {gate_decision.reason}",
                        )
                    ],
                    error=gate_decision.reason,
                    authority=step.authority,
                )

            adapter = self.adapters.get(step.agent_id)
            if adapter is None:
                stage.set_error("adapter not found")
                return self._failed_result(step, "adapter not found")

            task = AgentTask(agent_id=step.agent_id, instruction=step.task, tools=step.tools)
            try:
                result = self._dispatch_adapter(adapter, task, step, context)
                stage.set_raw_api(
                    {"status": result.status, "artifact_count": len(result.artifacts)}
                )
            except Exception as exc:
                stage.set_error(f"adapter raised: {exc}")
                result = AgentResult(agent_id=step.agent_id, status="error", error=str(exc))

            if result.status != "success":
                stage.set_branch("fallback")
                fallback_result = self.fallback.run(
                    step.agent_id, task, context, result.error or "adapter failed"
                )
                if fallback_result is not None and fallback_result.status == "success":
                    result = fallback_result

            step_artifacts = [
                stamp_artifact(artifact, step.agent_id, step.id)
                for artifact in result.artifacts
            ]

            # Tool failures no longer abort the step. We collect what
            # we got and let the rest of the tools run.
            tool_artifacts: list[dict] = []
            tool_errors: list[str] = []
            tool_artifacts, tool_errors = self._execute_step_tools(
                step.tools,
                [*prior_artifacts, *step_artifacts],
                step,
                context,
            )
            if tool_errors:
                stage.set_error("; ".join(tool_errors))

            status = "success" if result.status == "success" else "failed"
            messages = result.messages or [
                self._error_message(step.agent_id, result.error or "Agent execution failed")
            ]

            # IsFinal decision: only L1 auto-executable steps with
            # ``can_short_circuit=True`` may end the run early. L2/L3
            # need human confirmation, so they never short-circuit
            # even if the planner asks for it.
            can_short_circuit = (
                step.can_short_circuit and step.authority.auto_executable and status == "success"
            )

            stage.set_output(
                {
                    "message_count": len(messages),
                    "artifact_count": len(step_artifacts) + len(tool_artifacts),
                    "tool_error_count": len(tool_errors),
                    "final": can_short_circuit,
                }
            )
            if can_short_circuit:
                stage.set_final(True, reason=f"{step.agent_id} produced conclusive answer")

            return StepExecutionResult(
                step_id=step.id,
                agent_id=step.agent_id,
                status=status,
                messages=messages,
                artifacts=[*step_artifacts, *tool_artifacts],
                error=result.error,
                final=can_short_circuit,
                authority=step.authority,
            )

    def _maybe_emit_confirmation(self, step: PlanStep, result: StepExecutionResult) -> None:
        """Consult the authority gate and emit the confirmation event.

        The article frames L2 as "model can suggest, human decides". The
        default gate asks for confirmation on every L2 success; a
        stricter gate (or a future override) can flip that decision
        without touching this method.
        """

        if result.status != "success":
            return
        decision = self.authority_gate.after_dispatch(step, _agent_result_for(result))
        if decision.action is not GateAction.REQUEST_CONFIRMATION:
            return
        self._record_event(
            "authority.requires_confirmation",
            {
                "step_id": step.id,
                "agent_id": step.agent_id,
                "authority": step.authority.value,
                "task": step.task,
                "artifact_count": len(result.artifacts),
                "reason": decision.reason,
            },
        )
        # Persist the pending decision so the API layer can list
        # confirmations without re-parsing the run trace. The call is
        # import-local so the harness stays usable without the FastAPI
        # app (and its service module) being on the path.
        try:
            from app.api.services.decision_service import upsert_pending

            upsert_pending(
                run_id=self._current_run_id,
                step_id=step.id,
                agent_id=step.agent_id,
                authority=step.authority.value,
                task=step.task,
                artifact_count=len(result.artifacts),
            )
        except Exception:  # pragma: no cover - persistence is best-effort
            # Tests / offline use should not break the harness over a
            # missing service. The event stream still carries the full
            # payload so the API can rebuild state if needed.
            pass

    def _dispatch_adapter(
        self,
        adapter: AgentAdapter,
        task: AgentTask,
        step: PlanStep,
        context: RunContext,
    ) -> AgentResult:
        """Route an adapter call through the gateway.

        The default :class:`NoopGateway` is a pass-through, so callers
        that do not opt in pay nothing. When a real cache or signer is
        injected, this is the single place that knows about it.
        """

        from agenthub.gateway.gateway import GatewayDispatch

        return self.gateway.dispatch(
            adapter,
            GatewayDispatch(
                endpoint=f"adapter:{step.agent_id}",
                task=task,
                context=context,
                cache_ttl_seconds=0,
            ),
        )

    def _execute_step_tools(
        self,
        tool_ids: list[str],
        artifacts: list[dict],
        step: PlanStep,
        context: RunContext,
    ) -> tuple[list[dict], list[str]]:
        tool_artifacts: list[dict] = []
        errors: list[str] = []
        policy = tool_policy_for(self.agent_profiles.get(step.agent_id))
        for tool_id in tool_ids:
            with self.tracer.begin_stage(
                f"{step.id}.{tool_id}",
                f"Tool {tool_id}",
            ) as tool_stage:
                tool_stage.set_input({"tool_id": tool_id, "step_id": step.id})
                try:
                    ensure_tool_allowed(step.agent_id, tool_id, policy)
                    kwargs = tool_kwargs_for(tool_id, artifacts, step, context)
                except Exception as exc:
                    msg = f"{tool_id}: {exc}"
                    errors.append(msg)
                    self._record_event(
                        "tool.failed",
                        {
                            "step_id": step.id,
                            "agent_id": step.agent_id,
                            "tool_id": tool_id,
                            "error": str(exc),
                        },
                    )
                    tool_stage.set_error(msg)
                    continue

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
                    msg = f"{tool_id}: {exc}"
                    errors.append(msg)
                    self._record_event(
                        "tool.failed",
                        {
                            "step_id": step.id,
                            "agent_id": step.agent_id,
                            "tool_id": tool_id,
                            "error": str(exc),
                        },
                    )
                    tool_stage.set_error(msg)
                    continue

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
                tool_stage.set_output(
                    {"artifact_type": result.type, "artifact_title": result.title}
                )
                tool_artifacts.append(
                    stamp_artifact(
                        tool_result_to_artifact(result), step.agent_id, step.id
                    )
                )
        return tool_artifacts, errors

    def _failed_result(self, step: PlanStep, reason: str) -> StepExecutionResult:
        return StepExecutionResult(
            step_id=step.id,
            agent_id=step.agent_id,
            status="failed",
            messages=[self._error_message(step.agent_id, reason)],
            error=reason,
            authority=step.authority,
        )

    def _skipped_result(self, step: PlanStep, reason: str) -> StepExecutionResult:
        return StepExecutionResult(
            step_id=step.id,
            agent_id=step.agent_id,
            status="skipped",
            messages=[self._error_message(step.agent_id, f"Skipped: {reason}")],
            error=reason,
            authority=step.authority,
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
                    "authority": step.authority.value,
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
                "final": result.final,
                "authority": result.authority.value,
                "requires_user_confirmation": result.authority != AuthorityTier.L1_READONLY,
            },
        )

    def _record_event(self, event_type: str, payload: dict) -> RunEvent:
        event = RunEvent(type=event_type, payload=payload)
        self.events.append(event)
        return event

    def _build_run_metrics(
        self,
        plan: Plan,
        step_results: dict[str, "StepExecutionResult"],
        artifacts: list[dict],
    ) -> dict[str, Any]:
        """Aggregate monitoring counters for one completed run.

        Emitted alongside ``run.completed`` so dashboards and the trace
        panel can render consistent counters without re-parsing every
        stage. Counters are intentionally cheap — no per-step cost
        detail, just the roll-up needed to spot regressions.
        """

        stages = self.tracer.stages
        stage_costs = [stage.cost_ms for stage in stages if stage.cost_ms]
        statuses = [result.status for result in step_results.values()]
        authority_counts: dict[str, int] = {}
        for result in step_results.values():
            authority_counts[result.authority.value] = (
                authority_counts.get(result.authority.value, 0) + 1
            )
        agent_counts: dict[str, int] = {}
        for step in plan.steps:
            agent_counts[step.agent_id] = agent_counts.get(step.agent_id, 0) + 1
        cache_hits = sum(
            1 for stage in stages if stage.outputs.get("cache_hit") is True
        )
        return {
            "run_id": self._current_run_id or "",
            "steps_planned": len(plan.steps),
            "steps_succeeded": statuses.count("success"),
            "steps_failed": statuses.count("failed"),
            "steps_short_circuited": sum(
                1 for stage in stages if stage.final
            ),
            "llm_calls": sum(
                1 for stage in stages if stage.stage_name.startswith("llm.")
            ),
            "cache_hits": cache_hits,
            "artifact_count": len(artifacts),
            "total_cost_ms": sum(stage_costs),
            "max_stage_cost_ms": max(stage_costs) if stage_costs else 0,
            "authority_tier_counts": authority_counts,
            "agent_call_counts": agent_counts,
        }

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
        short_circuited: bool,
    ) -> dict:
        agent_lines: list[str] = []
        for step in plan_steps:
            result = step_results.get(step.id)
            state = result.status if result else "pending"
            tier = result.authority.value if result else step.authority.value
            final_tag = " (final)" if result and result.final else ""
            detail = f"- {step.agent_id} [{tier}]: {state}{final_tag}"
            if result and result.error:
                detail = f"{detail} ({result.error})"
            agent_lines.append(detail)

        artifact_lines = [
            f"- {artifact.get('type', 'artifact')}: {artifact.get('title') or artifact.get('id')}"
            for artifact in artifacts[:8]
        ]
        if len(artifacts) > 8:
            artifact_lines.append(f"- ... {len(artifacts) - 8} more artifacts")

        authority_tiers = sorted({r.authority.value for r in step_results.values()})
        l2_or_l3 = [t for t in authority_tiers if t in {"L2", "L3"}]
        pending_steps = [
            f"{result.agent_id} ({result.authority.value})"
            for result in step_results.values()
            if result.status == "success"
            and result.authority != AuthorityTier.L1_READONLY
        ]

        content = [
            "Orchestrator summary",
            "",
            f"- Status: {status}",
            f"- Agents completed: {len(step_results)}",
            f"- Artifacts: {len(artifacts)}",
            f"- Conflicts: {len(conflicts)}",
            f"- Short-circuited: {short_circuited}",
            f"- Authority tiers touched: {', '.join(authority_tiers) or 'none'}",
        ]
        if agent_lines:
            content.extend(["", "Agent results:", *agent_lines])
        if artifact_lines:
            content.extend(["", "Artifacts produced:", *artifact_lines])
        if conflicts:
            content.append("")
            content.append("Conflict artifacts were emitted so you can compare candidates before applying changes.")
        if pending_steps:
            content.append("")
            content.append(
                "Awaiting your confirmation for: " + ", ".join(pending_steps)
            )
        elif l2_or_l3:
            content.append("")
            content.append(
                "L2/L3 actions emitted suggestions only — review the affected "
                "cards and confirm before applying."
            )
        content.append("")
        content.append("Review the inline cards below this message or open the artifact panel for details.")
        return {
            "role": "agent",
            "sender": "orchestrator",
            "content": "\n".join(content),
            "format": "markdown",
        }


def _agent_result_for(result: StepExecutionResult) -> AgentResult:
    """Adapt a :class:`StepExecutionResult` into an :class:`AgentResult`
    so the gate's ``after_dispatch`` signature stays stable.

    Only the fields the gate actually inspects (status, agent_id,
    error) are populated. The remaining fields fall back to safe
    defaults so the gate never has to special-case None.
    """

    return AgentResult(
        agent_id=result.agent_id,
        status=result.status,
        error=result.error,
    )
