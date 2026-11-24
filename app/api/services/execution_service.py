"""Composition root: wires the harness supervisor to the application stores.

Execution lives in :mod:`agenthub.harness.supervisor` — the background
pool, budgets, cancellation, approval resume, recovery and the per-run
sandbox. What stays here is what genuinely belongs to the application:
publishing a finished run into conversations, messages and artifacts, and
turning an HTTP request into a background run. The port adapters below
are the seam between the two.
"""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from agenthub.domain.run import RunResult
from agenthub.harness.control import execution_scope
from agenthub.harness.supervisor import (
    DecisionStorePort,
    ResultPublisher,
    RunStorePort,
    RunSupervisor,
)
from app.api.services import decision_service, run_store


class _RunStoreAdapter(RunStorePort):
    """SQLite-backed run records behind the supervisor's port."""

    def load(self, run_id: str) -> dict | None:
        return run_store.load_run_result(run_id)

    def update(self, run_id: str, patch: dict) -> None:
        return run_store.update_run(run_id, patch)

    def mutate(self, run_id: str, fn) -> None:
        return run_store.mutate_run(run_id, fn)

    def save_result(self, run_id: str, result: RunResult) -> None:
        return run_store.save_run_result(run_id, result)

    def list_run_ids(self) -> list[str]:
        return run_store.list_run_ids()


class _DecisionStoreAdapter(DecisionStorePort):
    """Reviewable exact-action approvals behind the supervisor's port."""

    def list_for_run(self, run_id: str) -> list[dict]:
        return decision_service.list_decisions_for_run(run_id)

    def upsert_pending(
        self, run_id: str, *, conversation_id: str | None = None, **pending
    ) -> None:
        return decision_service.upsert_pending(
            run_id=run_id, conversation_id=conversation_id, **pending
        )

    def mark_execution(self, run_id: str, step_id: str, state: str) -> None:
        return decision_service.mark_execution(run_id, step_id, state)

    def cancel_pending(self, run_id: str) -> None:
        return decision_service.cancel_pending(run_id)

    def requeue_approved(self, run_id: str, note: str) -> None:
        def requeue(records):
            for decision in records:
                if (
                    decision.get("run_id") == run_id
                    and decision.get("status") == "approved"
                ):
                    decision.update(status="pending", note=note)
            return records

        return decision_service.DECISIONS.update(requeue)


class _AppPublisher(ResultPublisher):
    def publish(self, result: RunResult, *, generation_group_id=None) -> dict:
        return publish_result(result, generation_group_id=generation_group_id)


supervisor = RunSupervisor(
    run_store=_RunStoreAdapter(),
    decisions=_DecisionStoreAdapter(),
    publisher=_AppPublisher(),
)

# Compatibility surface. Routers, chat/workflow services and tests import
# these names from this module; they are the supervisor's own bound
# methods, so there is exactly one run lifecycle in the process.
execute_context = supervisor.execute_context
resume_run = supervisor.resume_run
cancel_run = supervisor.cancel_run
recover_interrupted_runs = supervisor.recover_interrupted_runs
control_for = supervisor.control_for
lock_for = supervisor.lock_for
# Aliased (not copied) so a test clearing one sees the supervisor's own
# control table.
_controls = supervisor.controls
_pool = supervisor.pool


def start_chat(request: dict):
    """Accept a chat or workflow request and run it in the background."""
    from app.api.services.chat_service import build_chat_response

    run_id = f"run_{uuid4().hex[:12]}"
    conversation_id = request["conversation_id"]
    supervisor.claim_run(run_id, conversation_id)

    def work():
        try:
            with supervisor.lock_for(run_id), execution_scope(
                supervisor.control_for(run_id)
            ):
                supervisor.control_for(run_id).check()
                if request.get("_workflow_artifact_id"):
                    from app.api.services.workflow_service import (
                        run_workflow_artifact,
                    )

                    response = run_workflow_artifact(
                        request["_workflow_artifact_id"],
                        model_provider=request.get("model_provider"),
                        model_name=request.get("model_name"),
                        _run_id=run_id,
                    )
                else:
                    response = build_chat_response({**request, "_run_id": run_id})
                supervisor.run_store.update(
                    run_id, {"response": response, "status": response["status"]}
                )
        except Exception as exc:
            status = (
                "cancelled"
                if supervisor.control_for(run_id).cancelled.is_set()
                else "failed"
            )
            supervisor.run_store.update(run_id, {"status": status, "error": str(exc)})
        finally:
            supervisor.controls.pop(run_id, None)

    supervisor.submit(work)
    return {"run_id": run_id, "status": "queued", "conversation_id": conversation_id}


def publish_result(result: RunResult, *, generation_group_id=None) -> dict:
    """Publish a run's messages and artifacts in one transaction.

    The result and its publication marker commit together, so a retried
    publish cannot duplicate conversation messages.
    """
    from agenthub.infrastructure.persistence.json_store import transaction
    from app.api.services import artifact_service, conversation_service

    with transaction(
        run_store._store(result.run_id),
        artifact_service.ARTIFACTS,
        artifact_service.ARTIFACT_VERSIONS,
        conversation_service.CONVERSATIONS,
        conversation_service.MESSAGES,
    ):
        return _publish_result(result, generation_group_id=generation_group_id)


def _publish_result(result: RunResult, *, generation_group_id=None) -> dict:
    from app.api.services.artifact_service import save_artifacts
    from app.api.services.conversation_service import add_message, next_generation_index

    snapshot = run_store.load_run_result(result.run_id) or {}
    published = snapshot.get("publication", {"messages": {}, "artifacts": {}})
    published = published or {"messages": {}, "artifacts": {}}

    def key(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()

    group_id = (
        generation_group_id or snapshot.get("generation_group_id") or result.run_id
    )
    generation_index = snapshot.get("generation_index") or next_generation_index(
        result.conversation_id, group_id
    )
    new_artifacts = [
        a for a in result.artifacts if key(a) not in published["artifacts"]
    ]
    if new_artifacts:
        saved = save_artifacts(result.conversation_id, result.run_id, new_artifacts)
        # Match source items in order; derived previews follow their source.
        cursor = 0
        for artifact in new_artifacts:
            group = [saved[cursor]]
            cursor += 1
            while (
                cursor < len(saved)
                and saved[cursor].get("source_artifact_id") == group[0]["id"]
            ):
                group.append(saved[cursor])
                cursor += 1
            published["artifacts"][key(artifact)] = group
    artifacts = [
        item
        for artifact in result.artifacts
        for item in published["artifacts"][key(artifact)]
    ]
    messages = []
    from agenthub.application.chat.send_message import _trace_events

    trace = _trace_events(
        (run_store.load_run_result(result.run_id) or {}).get("events", []),
        run_id=result.run_id,
    )
    for index, message in enumerate(result.messages):
        fingerprint = key([index, message])
        if fingerprint not in published["messages"]:
            published["messages"][fingerprint] = add_message(
                conversation_id=result.conversation_id,
                role=message.get("role", "agent"),
                sender=message.get("sender"),
                content=message.get("content", ""),
                format=message.get("format", "markdown"),
                artifact_ids=[a["id"] for a in artifacts],
                generation_group_id=group_id,
                generation_index=generation_index,
                trace_events=trace,
            )
            messages.append(published["messages"][fingerprint])
    response = {
        "run_id": result.run_id,
        "status": result.status,
        "messages": messages,
        "artifacts": artifacts,
        "events": (run_store.load_run_result(result.run_id) or {}).get("events", []),
    }
    run_store.update_run(
        result.run_id,
        {
            "publication": published,
            "response": response,
            "generation_group_id": group_id,
            "generation_index": generation_index,
        },
    )
    return response
