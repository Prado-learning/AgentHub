"""REST endpoints for L2 / L3 user decisions.

Three endpoints back the front-end approval queue:

* ``GET /runs/{run_id}/pending-confirmations`` — refresh the queue for
  one run.
* ``GET /runs/pending-confirmations`` — refresh the queue for every run
  (used by a global banner).
* ``POST /runs/{run_id}/steps/{step_id}/confirm`` — flip to ``applied``.
* ``POST /runs/{run_id}/steps/{step_id}/decline`` — flip to ``rejected``.

All endpoints are backed by :mod:`app.api.services.decision_service`
which holds the on-disk JSON store; the harness writes
``upsert_pending`` records whenever a step requests confirmation, and
this router resolves them.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    actor: str | None = None
    note: str | None = None


class DeclineRequest(BaseModel):
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
    decisions = [d for d in list_decisions_for_run(run_id) if d.get("status") == "pending"]
    return {"run_id": run_id, "pending_confirmations": decisions}


@router.post("/runs/{run_id}/pending-confirmations")
def register_pending(run_id: str, request: UpsertRequest) -> dict:
    """Idempotently register a pending confirmation.

    Normally the harness does this on every L2/L3 success. This endpoint
    exists so a caller who replays an older trace can rebuild the queue
    without re-running the plan.
    """

    record = upsert_pending(
        run_id=run_id,
        step_id=request.step_id,
        agent_id=request.agent_id,
        authority=request.authority,
        task=request.task,
        artifact_count=request.artifact_count,
    )
    return {"decision": record}


@router.post("/runs/{run_id}/steps/{step_id}/confirm")
def confirm(run_id: str, step_id: str, request: ConfirmRequest | None = None) -> dict:
    payload = request or ConfirmRequest()
    try:
        decision = confirm_step(
            run_id=run_id,
            step_id=step_id,
            actor=payload.actor,
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"decision": decision}


@router.post("/runs/{run_id}/steps/{step_id}/decline")
def decline(run_id: str, step_id: str, request: DeclineRequest | None = None) -> dict:
    payload = request or DeclineRequest()
    try:
        decision = decline_step(
            run_id=run_id,
            step_id=step_id,
            actor=payload.actor,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"decision": decision}


@router.get("/runs/{run_id}/steps/{step_id}/decision")
def read_decision(run_id: str, step_id: str) -> dict:
    decision = get_decision(run_id, step_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="no decision recorded yet")
    return {"decision": decision}