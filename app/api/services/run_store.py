"""Durable run records and legacy snapshot import."""

from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from agenthub.infrastructure.config.paths import runtime_dir
from agenthub.infrastructure.persistence.json_store import JsonStore
from agenthub.sandbox.path_policy import safe_identifier

RUNTIME_DIR = runtime_dir()
RUNS_DIR = RUNTIME_DIR / "runs"


def _run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{safe_identifier(run_id)}.json"


def _store(run_id: str) -> JsonStore:
    return JsonStore(
        _run_path(run_id),
        database_path=RUNTIME_DIR / "agenthub.sqlite3",
        namespace="runs/" + safe_identifier(run_id) + ".json",
    )


def update_run(run_id: str, updates: dict) -> dict:
    return _store(run_id).update(
        lambda old: {
            **(old if isinstance(old, dict) else {}),
            **updates,
            "run_id": run_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def mutate_run(run_id: str, fn) -> dict:
    return _store(run_id).update(lambda old: fn(old if isinstance(old, dict) else {}))


def save_run_result(run_id: str, run_result: Any) -> dict:
    stages = [
        dict(s) if isinstance(s, dict) else asdict(s) for s in run_result.debug_trace
    ]
    for stage in stages:
        if isinstance(stage.get("started_at"), datetime):
            stage["started_at"] = stage["started_at"].isoformat()
    events = [
        {"type": e.type, "payload": e.payload, "created_at": e.created_at.isoformat()}
        if not isinstance(e, dict)
        else e
        for e in run_result.events
    ]
    return update_run(
        run_id,
        {
            "status": run_result.status,
            "conversation_id": getattr(run_result, "conversation_id", ""),
            "events": events,
            "debug_trace": stages,
            "checkpoint": getattr(run_result, "checkpoint", {}),
            "raw_messages": getattr(run_result, "messages", []),
            "raw_artifacts": getattr(run_result, "artifacts", []),
        },
    )


def load_run_result(run_id: str) -> dict | None:
    value = _store(run_id).read()
    return value if isinstance(value, dict) and value else None


def list_run_ids() -> list[str]:
    if not RUNS_DIR.exists() and not (RUNTIME_DIR / "agenthub.sqlite3").exists():
        return []
    # Import older JSON snapshots without removing the originals.
    for path in RUNS_DIR.glob("*.json"):
        if path.stem.startswith(("run_", "workflow_run_")):
            _store(path.stem).read()
    store = _store("run_index")
    with store.locked():
        rows = (
            store._connection()
            .execute("SELECT name FROM stores WHERE name LIKE 'runs/%.json'")
            .fetchall()
        )
    return sorted(
        Path(row[0]).stem
        for row in rows
        if row[0] != "runs/run_index.json" and load_run_result(Path(row[0]).stem)
    )


def reset_for_tests() -> None:
    for run_id in list_run_ids():
        _store(run_id).write({})
