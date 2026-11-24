"""Persist reviewable exact-action approvals. Approval is not execution."""

from __future__ import annotations
from datetime import datetime, timezone
from agenthub.infrastructure.config.paths import runtime_dir
from agenthub.infrastructure.persistence.json_store import JsonStore

RUNTIME_DIR = runtime_dir()
DECISIONS = JsonStore(RUNTIME_DIR / "run_decisions.json")


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def list_pending_confirmations():
    return [d for d in DECISIONS.read() if d.get("status") == "pending"]


def list_decisions_for_run(run_id):
    return [d for d in DECISIONS.read() if d.get("run_id") == run_id]


def get_decision(run_id, step_id):
    return next(
        (d for d in list_decisions_for_run(run_id) if d.get("step_id") == step_id), None
    )


def upsert_pending(
    *,
    run_id,
    step_id,
    agent_id,
    authority,
    task,
    artifact_count,
    fingerprint="",
    **details,
):
    result = None

    def mutate(records):
        nonlocal result
        result = next(
            (
                d
                for d in records
                if d.get("run_id") == run_id and d.get("step_id") == step_id
            ),
            None,
        )
        if result is not None:
            if result.get("fingerprint", "") == fingerprint:
                return None
            if result.get("status") in {"applied", "rejected"}:
                raise ValueError("Cannot replace a final action")
            records = [d for d in records if d is not result]
        result = {
            "run_id": run_id,
            "step_id": step_id,
            "agent_id": agent_id,
            "authority": authority,
            "task": task,
            "artifact_count": artifact_count,
            "fingerprint": fingerprint,
            "status": "pending",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            **details,
        }
        return [*records, result]

    DECISIONS.update(mutate)
    return result


def _decide(run_id, step_id, status, actor=None, note=None, fingerprint=None):
    result = None

    def mutate(records):
        nonlocal result
        result = next(
            (
                d
                for d in records
                if d.get("run_id") == run_id and d.get("step_id") == step_id
            ),
            None,
        )
        if result is None:
            raise KeyError("No pending action")
        if fingerprint is not None and result.get("fingerprint") != fingerprint:
            raise ValueError("Action changed; refresh before confirming")
        if result["status"] == status:
            return None
        if result["status"] != "pending":
            raise ValueError("Decision is already final")
        result["confirmed_by" if status == "approved" else "declined_by"] = (
            actor or "local-user"
        )
        if status == "rejected":
            result["reason"] = note or ""
        result.update(
            status=status,
            updated_at=_utc_now(),
            actor=actor or "local-user",
            note=note or "",
        )
        return records

    DECISIONS.update(mutate)
    return result


def confirm_step(*, run_id, step_id, actor=None, note=None, fingerprint=None):
    return _decide(run_id, step_id, "approved", actor, note, fingerprint)


def decline_step(*, run_id, step_id, actor=None, reason=None, fingerprint=None):
    return _decide(run_id, step_id, "rejected", actor, reason, fingerprint)


def mark_execution(run_id, step_id, status):
    def mutate(records):
        for d in records:
            if (
                d.get("run_id") == run_id
                and d.get("step_id") == step_id
                and d.get("status") == "approved"
            ):
                d.update(status=status, updated_at=_utc_now())
        return records

    DECISIONS.update(mutate)


def cancel_pending(run_id):
    def mutate(records):
        for d in records:
            if d.get("run_id") == run_id and d.get("status") in {"pending", "approved"}:
                d.update(status="cancelled", updated_at=_utc_now())
        return records

    DECISIONS.update(mutate)


def reset_for_tests():
    DECISIONS.write([])
