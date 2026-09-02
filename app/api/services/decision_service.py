"""Storage and queries for L2 / L3 user decisions.

When an agent step finishes with authority tier L2 or L3 the harness
emits ``authority.requires_confirmation`` and surfaces the step on
``run.completed.pending_confirmation_steps``. The user (or an upstream
business gate) then has to either confirm or decline.

This service is the only place that mutates :class:`JsonStore` for
those decisions. It exposes three entry points:

* :func:`list_pending_confirmations` — refresh queue for the front end.
* :func:`confirm_step` — flip the step from ``pending`` to ``applied``,
  emitting an ``authority.confirmed`` event.
* :func:`decline_step` — flip the step from ``pending`` to ``rejected``,
  emitting an ``authority.declined`` event with a reason.

Decisions are immutable once written: a second ``confirm`` on the same
``(run_id, step_id)`` pair returns the existing record without rewriting
the timestamp, so audit trails never go backwards.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.api.services.conversation_store import JsonStore


RUNTIME_DIR = Path("agent-workspace/runtime")
DECISIONS = JsonStore(RUNTIME_DIR / "run_decisions.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decision_key(run_id: str, step_id: str) -> tuple[str, str]:
    return (run_id, step_id)


def list_pending_confirmations() -> list[dict[str, Any]]:
    """Return every decision still in ``pending`` state.

    The front end polls this to render the approval queue without
    re-parsing the whole run trace.
    """

    return [
        item for item in DECISIONS.read() if item.get("status") == "pending"
    ]


def list_decisions_for_run(run_id: str) -> list[dict[str, Any]]:
    return [item for item in DECISIONS.read() if item.get("run_id") == run_id]


def get_decision(run_id: str, step_id: str) -> dict[str, Any] | None:
    key = _decision_key(run_id, step_id)
    return next(
        (
            item
            for item in DECISIONS.read()
            if _decision_key(item.get("run_id", ""), item.get("step_id", "")) == key
        ),
        None,
    )


def upsert_pending(
    *,
    run_id: str,
    step_id: str,
    agent_id: str,
    authority: str,
    task: str,
    artifact_count: int,
) -> dict[str, Any]:
    """Record a step as needing confirmation. Idempotent.

    If a decision already exists for this step the existing record is
    returned unchanged (its timestamp is preserved) — that means an L2
    step emitted later in the run cannot overwrite an early confirm or
    decline.
    """

    key = _decision_key(run_id, step_id)
    existing = next(
        (
            item
            for item in DECISIONS.read()
            if _decision_key(item.get("run_id", ""), item.get("step_id", "")) == key
        ),
        None,
    )
    if existing is not None:
        return existing

    record = {
        "run_id": run_id,
        "step_id": step_id,
        "agent_id": agent_id,
        "authority": authority,
        "task": task,
        "artifact_count": artifact_count,
        "status": "pending",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }

    def _mutate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [*records, record]

    DECISIONS.update(_mutate)
    return record


def confirm_step(
    *,
    run_id: str,
    step_id: str,
    actor: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Mark a step as confirmed by the user.

    Raises :class:`KeyError` when no decision record exists yet — the
    harness is supposed to upsert one when it emits the confirmation
    event, so a missing record indicates the step was never actually
    flagged for confirmation (likely a stale client).
    """

    key = _decision_key(run_id, step_id)
    stamp = _utc_now()

    def _mutate(records: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        for result in records:
            if _decision_key(result.get("run_id", ""), result.get("step_id", "")) == key:
                if result.get("status") == "applied":
                    return None  # already confirmed — leave it alone
                mutated = dict(result)
                mutated["status"] = "applied"
                mutated["updated_at"] = stamp
                if actor is not None:
                    mutated["confirmed_by"] = actor
                if note is not None:
                    mutated["note"] = note
                return [mutated if item is result else item for item in records]
        raise KeyError(f"no pending decision for run={run_id} step={step_id}")

    DECISIONS.update(_mutate)
    decision = get_decision(run_id, step_id)
    assert decision is not None  # mutate either kept it or wrote it
    return decision


def decline_step(
    *,
    run_id: str,
    step_id: str,
    actor: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Mark a step as declined by the user.

    Mirrors :func:`confirm_step` — refuses to rewrite an already-final
    decision, raises :class:`KeyError` when no pending record exists.
    """

    key = _decision_key(run_id, step_id)
    stamp = _utc_now()

    def _mutate(records: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        for result in records:
            if _decision_key(result.get("run_id", ""), result.get("step_id", "")) == key:
                if result.get("status") in {"rejected", "applied"}:
                    return None
                mutated = dict(result)
                mutated["status"] = "rejected"
                mutated["updated_at"] = stamp
                if actor is not None:
                    mutated["declined_by"] = actor
                if reason is not None:
                    mutated["reason"] = reason
                return [mutated if item is result else item for item in records]
        raise KeyError(f"no pending decision for run={run_id} step={step_id}")

    DECISIONS.update(_mutate)
    decision = get_decision(run_id, step_id)
    assert decision is not None
    return decision


def reset_for_tests() -> None:  # pragma: no cover - test helper
    """Wipe the on-disk store. Used by the test suite only."""

    DECISIONS.write([])