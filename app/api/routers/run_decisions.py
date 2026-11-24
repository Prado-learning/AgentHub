from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.services import run_store
from app.api.services.decision_service import (
    confirm_step,
    decline_step,
    get_decision,
    list_decisions_for_run,
    list_pending_confirmations,
    upsert_pending,
)


router = APIRouter(tags=["run-decisions"])


class ConfirmRequest(BaseModel):
    fingerprint: str = Field(min_length=64, max_length=64)
    actor: str | None = None
    note: str | None = None


class DeclineRequest(BaseModel):
    fingerprint: str = Field(min_length=64, max_length=64)
    actor: str | None = None
    reason: str | None = Field(default=None, max_length=512)


class UpsertRequest(BaseModel):
    step_id: str
    agent_id: str
    authority: str
    task: str = ""
    artifact_count: int = 0


@router.get("/runs/pending-confirmations")
def read_all_pending_confirmations() -> dict:
    """Every pending confirmation across every run.

    The decision store does not key on conversation_id, so this is the
    cheap way for the front end to render a global "approval needed"
    banner.
    """

    return {"pending_confirmations": list_pending_confirmations()}


@router.get("/runs/{run_id}/pending-confirmations")
def read_pending_for_run(run_id: str) -> dict:
    decisions = [
        d for d in list_decisions_for_run(run_id) if d.get("status") == "pending"
    ]
    return {"run_id": run_id, "pending_confirmations": decisions}


def _decide(run_id: str, step_id: str, payload, approve: bool):
    from app.api.services.execution_service import lock_for, resume_run

    with lock_for(run_id):
        snapshot = run_store.load_run_result(run_id)
        decision = get_decision(run_id, step_id)
        if snapshot is None or decision is None:
            raise HTTPException(status_code=404, detail="Run or decision not found")
        if decision.get("fingerprint") != payload.fingerprint:
            raise HTTPException(
                status_code=409, detail="Action changed; refresh before deciding"
            )
        if decision["status"] in {"applied", "failed", "rejected"}:
            return {"decision": decision}
        if snapshot.get("status") != "waiting_approval":
            raise HTTPException(
                status_code=409, detail="Run is not waiting for approval"
            )
        try:
            if approve:
                confirm_step(
                    run_id=run_id,
                    step_id=step_id,
                    actor=payload.actor,
                    note=payload.note,
                    fingerprint=payload.fingerprint,
                )
            else:
                decline_step(
                    run_id=run_id,
                    step_id=step_id,
                    actor=payload.actor,
                    reason=payload.reason,
                    fingerprint=payload.fingerprint,
                )
            response = resume_run(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"decision": get_decision(run_id, step_id), "response": response}


@router.post("/runs/{run_id}/steps/{step_id}/confirm")
def confirm(run_id: str, step_id: str, request: ConfirmRequest) -> dict:
    return _decide(run_id, step_id, request, True)


@router.post("/runs/{run_id}/steps/{step_id}/decline")
def decline(run_id: str, step_id: str, request: DeclineRequest) -> dict:
    return _decide(run_id, step_id, request, False)


@router.get("/runs/{run_id}/steps/{step_id}/decision")
def read_decision(run_id: str, step_id: str) -> dict:
    decision = get_decision(run_id, step_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="no decision recorded yet")
    return {"decision": decision}


@router.get("/runs/{run_id}/debug-trace")
def read_debug_trace(run_id: str) -> dict:
    """Return the persisted per-stage trace for one run.

    The chat service snapshots :class:`RunResult.debug_trace` to disk
    before the chat response goes out, so this endpoint can serve
    historical stages long after the harness has finished.

    Stages come back in the order the harness recorded them. An empty
    list means the run is unknown or had tracing disabled.
    """

    snapshot = run_store.load_run_result(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id {run_id}")
    return {
        "run_id": run_id,
        "status": snapshot.get("status", "unknown"),
        "saved_at": snapshot.get("saved_at"),
        "stages": snapshot.get("debug_trace", []),
    }


@router.get("/runs")
def list_runs(conversation_id: str | None = None) -> dict:
    runs = [run_store.load_run_result(key) for key in run_store.list_run_ids()]
    runs = [
        r
        for r in runs
        if r and (not conversation_id or r.get("conversation_id") == conversation_id)
    ]
    return {
        "run_ids": [r["run_id"] for r in runs],
        "runs": [
            {
                key: r.get(key)
                for key in ("run_id", "conversation_id", "status", "updated_at")
            }
            for r in runs
        ],
    }


@router.get("/runs/{run_id}")
def read_run(run_id: str, after: int = 0) -> dict:
    try:
        snapshot = run_store.load_run_result(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    if not snapshot:
        raise HTTPException(status_code=404, detail="Run not found")
    if (
        snapshot.get("raw_messages")
        and not snapshot.get("response")
        and snapshot.get("status")
        in {"success", "failed", "partial_success", "waiting_approval"}
    ):
        snapshot["status"] = "running"
    events = snapshot.get("events", [])
    return {
        key: snapshot.get(key)
        for key in ("run_id", "status", "response", "error", "updated_at")
    } | {"events": events[max(0, after) :], "cursor": len(events)}


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str) -> dict:
    from app.api.services.execution_service import cancel_run

    try:
        snapshot = cancel_run(run_id)
        return {"run_id": run_id, "status": snapshot["status"]}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
