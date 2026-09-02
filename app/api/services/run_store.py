"""Persist :class:`agenthub.domain.run.RunResult` so the front end can
replay the debug trace after the run completes.

The harness exposes ``debug_trace`` on :class:`RunResult` while the
process is alive, but the chat endpoint returns only the chat payload
to the client. To make the trace observable after the chat response
goes out, the chat service persists a serialised snapshot to disk and
the ``/runs/{run_id}/debug-trace`` endpoint reads it back.

We use one file per ``run_id`` so reads are O(1) and the store cannot
leak memory if runs accumulate. Writes go through
:class:`JsonStore.update` so concurrent chat pipelines cannot lose each
other's stages.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.api.services.conversation_store import JsonStore


RUNTIME_DIR = Path("agent-workspace/runtime")
RUNS_DIR = RUNTIME_DIR / "runs"


def _run_path(run_id: str) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR / f"{run_id}.json"


def _serialise_stage(stage: Any) -> dict[str, Any]:
    """Convert a :class:`StageTrace` (or a plain dict) into JSON-friendly form."""

    if isinstance(stage, dict):
        return dict(stage)
    started = getattr(stage, "started_at", None)
    return {
        "stage_id": getattr(stage, "stage_id", ""),
        "stage_name": getattr(stage, "stage_name", ""),
        "started_at": started.isoformat() if isinstance(started, datetime) else started,
        "cost_ms": getattr(stage, "cost_ms", 0),
        "inputs": dict(getattr(stage, "inputs", {}) or {}),
        "raw_api_data": dict(getattr(stage, "raw_api_data", {}) or {}),
        "branch_hit": getattr(stage, "branch_hit", None),
        "outputs": dict(getattr(stage, "outputs", {}) or {}),
        "error": getattr(stage, "error", None),
        "final": bool(getattr(stage, "final", False)),
    }


def save_run_result(run_id: str, run_result: Any) -> dict[str, Any]:
    """Persist a run snapshot keyed by ``run_id``.

    Returns the dict that was written so callers (and tests) can verify
    the exact payload without re-reading the file.
    """

    snapshot = {
        "run_id": getattr(run_result, "run_id", run_id),
        "status": getattr(run_result, "status", "unknown"),
        "saved_at": datetime.utcnow().isoformat(),
        "events": [dict(event) if isinstance(event, dict) else {
            "type": getattr(event, "type", ""),
            "payload": getattr(event, "payload", {}),
            "created_at": getattr(event, "created_at", "").isoformat()
                if hasattr(getattr(event, "created_at", None), "isoformat")
                else getattr(event, "created_at", ""),
        } for event in getattr(run_result, "events", []) or []],
        "debug_trace": [
            _serialise_stage(stage) for stage in getattr(run_result, "debug_trace", []) or []
        ],
    }
    path = _run_path(run_id)
    store = JsonStore(path)
    store.write(snapshot)
    return snapshot


def load_run_result(run_id: str) -> dict[str, Any] | None:
    """Return the stored snapshot for ``run_id`` or ``None`` when unknown."""

    path = _run_path(run_id)
    if not path.exists():
        return None
    return JsonStore(path).read()


def list_run_ids() -> list[str]:
    """Return every run id currently on disk (sorted)."""

    if not RUNS_DIR.exists():
        return []
    return sorted(p.stem for p in RUNS_DIR.glob("*.json"))


def reset_for_tests() -> None:  # pragma: no cover - test helper
    """Wipe every persisted run. Used by the test suite only."""

    if not RUNS_DIR.exists():
        return
    for path in RUNS_DIR.glob("*.json"):
        path.unlink()
