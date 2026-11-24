"""Run lifecycle supervision: durable execution, approval resume, recovery.

The supervisor owns everything about a run that is not the plan itself:
the background pool it executes on, the ``RunControl`` carrying its
budget and cancellation flag, the sandbox its side effects are confined
to, and the transition between ``queued`` → ``running`` →
``waiting_approval`` → terminal state. It depends on three ports —
:class:`RunStorePort`, :class:`DecisionStorePort` and
:class:`ResultPublisher` — so the harness runs identically against the
SQLite-backed application store, an in-memory store in tests, or a
different backend entirely. Nothing here imports the HTTP application.

Cancellation is cooperative: the supervisor sets the flag and lets the
runner observe it between steps and tools. Processes started through the
run's sandbox are terminated by the sandbox, so a cancelled run does not
leave a CLI tree behind.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import RLock
from typing import Any, Callable, Protocol
from uuid import uuid4

from agenthub.adapters import build_agent_adapters_from_env
from agenthub.domain.run import RunContext, RunResult
from agenthub.harness.control import RunControl, execution_scope
from agenthub.harness.runner import HarnessRunner
from agenthub.infrastructure.config.env import env_flag
from agenthub.sandbox.manager import SandboxManager

_ACTIVE_STATUSES = {"queued", "running", "cancelling", "waiting_approval"}
_TERMINAL_STATUSES = {
    "success",
    "failed",
    "partial_success",
    "cancelled",
    "interrupted",
}


class RunStorePort(Protocol):
    """Durable run records: status, events, checkpoint, result."""

    def load(self, run_id: str) -> dict | None: ...

    def update(self, run_id: str, patch: dict) -> None: ...

    def mutate(self, run_id: str, fn: Callable[[dict], dict]) -> None: ...

    def save_result(self, run_id: str, result: RunResult) -> None: ...

    def list_run_ids(self) -> list[str]: ...


class DecisionStorePort(Protocol):
    """Per-step approval decisions for one run."""

    def list_for_run(self, run_id: str) -> list[dict]: ...

    def upsert_pending(
        self, run_id: str, *, conversation_id: str | None = None, **pending: Any
    ) -> None: ...

    def mark_execution(self, run_id: str, step_id: str, state: str) -> None: ...

    def cancel_pending(self, run_id: str) -> None: ...

    def requeue_approved(self, run_id: str, note: str) -> None: ...


class ResultPublisher(Protocol):
    """Turns a finished run into conversation messages and artifacts."""

    def publish(self, result: RunResult, *, generation_group_id=None) -> dict: ...


class RunSupervisor:
    """Creates, resumes, cancels and recovers runs."""

    def __init__(
        self,
        *,
        run_store: RunStorePort,
        decisions: DecisionStorePort,
        publisher: ResultPublisher,
        adapter_factory: Callable[..., dict] | None = None,
        sandbox_manager: SandboxManager | None = None,
        max_workers: int = 4,
    ) -> None:
        self.run_store = run_store
        self.decisions = decisions
        self.publisher = publisher
        self.adapter_factory = adapter_factory or build_agent_adapters_from_env
        self.sandbox_manager = sandbox_manager or SandboxManager()
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="agenthub-run"
        )
        self._controls: dict[str, RunControl] = {}
        self._locks: dict[str, RLock] = {}
        self._guard = RLock()

    # -- ambient state -----------------------------------------------------

    @property
    def controls(self) -> dict[str, RunControl]:
        """Live controls, shared so a test can clear them between runs."""
        return self._controls

    @property
    def pool(self) -> ThreadPoolExecutor:
        return self._pool

    def control_for(self, run_id: str) -> RunControl:
        with self._guard:
            return self._controls.setdefault(
                run_id,
                RunControl(
                    timeout_seconds=float(os.environ.get("RUN_TIMEOUT_SECONDS", "300")),
                    max_llm_calls=int(os.environ.get("RUN_MAX_LLM_CALLS", "24")),
                ),
            )

    def lock_for(self, run_id: str) -> RLock:
        with self._guard:
            return self._locks.setdefault(run_id, RLock())

    def active_run_for(self, conversation_id: str) -> str | None:
        """The run already occupying this conversation, if any."""
        for run_id in self.run_store.list_run_ids():
            record = self.run_store.load(run_id) or {}
            if record.get("conversation_id") == conversation_id and record.get(
                "status"
            ) in _ACTIVE_STATUSES:
                return run_id
        return None

    def submit(self, work: Callable[[], Any]) -> None:
        self._pool.submit(work)

    def claim_run(self, run_id: str, conversation_id: str) -> None:
        """Reserve the single active run slot a conversation is allowed.

        The check and the queued write happen under one lock so two
        concurrent submissions for the same conversation cannot both win.
        """
        with self._guard:
            if self.active_run_for(conversation_id) is not None:
                raise ValueError(
                    "This conversation already has an active run; "
                    "finish or cancel it first"
                )
            self.run_store.update(
                run_id,
                {
                    "status": "queued",
                    "conversation_id": conversation_id,
                    "events": [],
                },
            )
            self.control_for(run_id)

    # -- execution ---------------------------------------------------------

    def execute_context(
        self,
        context: RunContext,
        *,
        run_id: str | None = None,
        plan=None,
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> RunResult:
        run_id = run_id or f"run_{uuid4().hex[:12]}"
        previous = self.run_store.load(run_id) or {}
        decisions = self.decisions.list_for_run(run_id)
        approvals = {
            d["step_id"]: d["fingerprint"] for d in decisions if d["status"] == "approved"
        }
        rejected = {d["step_id"] for d in decisions if d["status"] == "rejected"}
        self.run_store.update(
            run_id,
            {
                "status": "running",
                "response": None,
                "conversation_id": context.conversation_id,
                "context": asdict(context),
                "model_provider": model_provider,
                "model_name": model_name,
            },
        )

        def emit(event):
            value = {
                "type": event.type,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
            self.run_store.mutate(
                run_id,
                lambda record: {**record, "events": [*(record.get("events") or []), value]},
            )

        adapters = self.adapter_factory(model_provider, model_name)
        planner_provider = (
            getattr(adapters.get("orchestrator"), "provider", None)
            if env_flag("ENABLE_LLM_PLANNER", env_flag("ENABLE_REAL_LLM"))
            else None
        )
        try:
            runner = HarnessRunner(
                mode="configured",
                adapters=adapters,
                planner_provider=planner_provider,
                control=self.control_for(run_id),
                sandbox_manager=self.sandbox_manager,
                on_event=emit,
                on_checkpoint=lambda checkpoint: self.run_store.update(
                    run_id, {"checkpoint": checkpoint}
                ),
            )
            result = runner.run(
                context,
                run_id=run_id,
                plan=plan,
                checkpoint=previous.get("checkpoint"),
                approvals=approvals,
                rejected=rejected,
            )
        finally:
            # The runner builds the sandbox, because it is the only
            # component that knows the plan's authority tiers and therefore
            # the boundary the policy demands. The supervisor owns the
            # lifetime: it releases whatever the run registered, so the
            # sandbox spans a resume and never outlives the run.
            self.sandbox_manager.release(run_id)

        prior_events = previous.get("events", [])
        self.run_store.save_result(run_id, result)
        self.run_store.update(
            run_id,
            {
                "events": [
                    *prior_events,
                    *[
                        {
                            "type": e.type,
                            "payload": e.payload,
                            "created_at": e.created_at.isoformat(),
                        }
                        for e in result.events
                    ],
                ]
            },
        )
        for pending in result.checkpoint.get("pending_confirmations", []):
            self.decisions.upsert_pending(
                run_id=run_id,
                conversation_id=context.conversation_id,
                **pending,
            )
        for step_id, step in result.checkpoint.get("step_results", {}).items():
            self.decisions.mark_execution(
                run_id, step_id, "applied" if step["status"] == "success" else "failed"
            )
        if result.status == "cancelled":
            self.decisions.cancel_pending(run_id)
        return result

    def resume_run(self, run_id: str) -> dict:
        with self.lock_for(run_id):
            snapshot = self.run_store.load(run_id)
            if not snapshot or snapshot.get("status") != "waiting_approval":
                raise ValueError("Run is not waiting for approval")
            # A fresh control discards the paused run's remaining budget,
            # but the checkpoint's elapsed time is restored inside run().
            self._controls.pop(run_id, None)
            context = RunContext(**snapshot["context"])
            result = self.execute_context(
                context,
                run_id=run_id,
                model_provider=snapshot.get("model_provider"),
                model_name=snapshot.get("model_name"),
            )
            return self.publisher.publish(
                result, generation_group_id=snapshot.get("generation_group_id")
            )

    def cancel_run(self, run_id: str) -> dict:
        snapshot = self.run_store.load(run_id)
        if snapshot is None:
            raise KeyError("Run not found")
        if snapshot.get("status") in _TERMINAL_STATUSES:
            return snapshot
        self.control_for(run_id).cancelled.set()
        if snapshot.get("status") in {"waiting_approval", "queued"}:
            self.decisions.cancel_pending(run_id)
            return self.run_store.update(run_id, {"status": "cancelled"})
        return self.run_store.update(
            run_id, {"cancel_requested": True, "status": "cancelling"}
        )

    # -- recovery ----------------------------------------------------------

    def recover_interrupted_runs(self) -> None:
        """Reconcile runs after a restart.

        Runs that were mid-flight are marked ``interrupted`` and never
        replayed: their steps may already have had effects, and the
        checkpoint's ``inflight_steps`` records which ones. Runs that were
        waiting for approval keep their pending decisions, but any
        approval granted before the restart is returned to ``pending`` —
        a restart must not dispatch an action nobody re-confirmed.
        """
        for run_id in self.run_store.list_run_ids():
            snapshot = self.run_store.load(run_id) or {}
            status = snapshot.get("status")
            if status in {"running", "queued", "cancelling"}:
                self.run_store.update(
                    run_id,
                    {
                        "status": "interrupted",
                        "error": (
                            "Server restarted during execution; effects may have "
                            "occurred. Inspect the workspace before starting a new run."
                        ),
                    },
                )
            elif status in {
                "waiting_approval",
                "success",
                "partial_success",
                "failed",
            }:
                checkpoint = snapshot.get("checkpoint", {})
                if status == "waiting_approval":
                    for pending in checkpoint.get("pending_confirmations", []):
                        self.decisions.upsert_pending(
                            run_id=run_id,
                            conversation_id=snapshot.get("conversation_id"),
                            **pending,
                        )
                    self.decisions.requeue_approved(
                        run_id, "Server restarted before dispatch; please review again."
                    )
                self._republish_if_needed(snapshot, checkpoint)

    def _republish_if_needed(self, snapshot: dict, checkpoint: dict) -> None:
        if (
            snapshot.get("response")
            or not snapshot.get("raw_messages")
            or not snapshot.get("conversation_id")
        ):
            return
        result = RunResult(
            run_id=snapshot["run_id"],
            status=snapshot["status"],
            conversation_id=snapshot["conversation_id"],
            messages=snapshot.get("raw_messages", []),
            artifacts=snapshot.get("raw_artifacts", []),
            checkpoint=checkpoint,
        )
        self.publisher.publish(
            result, generation_group_id=snapshot.get("generation_group_id")
        )
