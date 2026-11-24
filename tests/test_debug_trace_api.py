"""P2 — run snapshot persistence + debug-trace endpoint.

Two layers:

* :mod:`app.api.services.run_store` saves a ``RunResult`` snapshot to
  disk and reloads it.
* :mod:`app.api.routers.run_decisions` exposes
  ``GET /runs/{run_id}/debug-trace`` so the front end can replay a run
  after the chat response is gone.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@dataclass
class _FakeStage:
    stage_id: str = "stage_1"
    stage_name: str = "harness.run"
    cost_ms: int = 12
    inputs: dict = field(default_factory=dict)
    raw_api_data: dict = field(default_factory=dict)
    branch_hit: str | None = "primary"
    outputs: dict = field(default_factory=dict)
    error: str | None = None
    final: bool = False
    started_at: datetime = field(
        default_factory=lambda: datetime(2026, 9, 2, tzinfo=timezone.utc)
    )


@dataclass
class _FakeRunResult:
    run_id: str = "run_test_1"
    status: str = "success"
    events: list = field(default_factory=list)
    debug_trace: list = field(default_factory=list)


@pytest.fixture
def run_store():
    from app.api.services import run_store

    return run_store


def test_save_and_load_run_snapshot(run_store) -> None:
    result = _FakeRunResult(
        run_id="run_xyz",
        status="success",
        debug_trace=[
            _FakeStage(
                stage_id="s1",
                stage_name="harness.run",
                outputs={"stages_planned": 2},
                final=True,
            )
        ],
    )

    snapshot = run_store.save_run_result("run_xyz", result)
    assert snapshot["run_id"] == "run_xyz"
    assert snapshot["status"] == "success"
    assert len(snapshot["debug_trace"]) == 1
    assert snapshot["debug_trace"][0]["stage_name"] == "harness.run"
    assert snapshot["debug_trace"][0]["final"] is True
    assert snapshot["debug_trace"][0]["started_at"].startswith("2026-09-02")

    loaded = run_store.load_run_result("run_xyz")
    assert loaded is not None
    assert loaded["status"] == "success"
    assert loaded["debug_trace"][0]["stage_name"] == "harness.run"


def test_save_run_result_is_idempotent(run_store) -> None:
    run_store.save_run_result("run_keep", _FakeRunResult(run_id="run_keep"))
    run_store.save_run_result(
        "run_keep",
        _FakeRunResult(run_id="run_keep", status="failed"),
    )
    # The second write should replace the snapshot wholesale.
    loaded = run_store.load_run_result("run_keep")
    assert loaded is not None
    assert loaded["status"] == "failed"


def test_load_unknown_run_returns_none(run_store) -> None:
    assert run_store.load_run_result("ghost") is None


def test_list_run_ids_sorted(run_store) -> None:
    run_store.save_run_result("zeta", _FakeRunResult(run_id="zeta"))
    run_store.save_run_result("alpha", _FakeRunResult(run_id="alpha"))
    assert run_store.list_run_ids() == ["alpha", "zeta"]


def test_serialise_stage_accepts_dicts(run_store) -> None:
    """Stages that arrive as plain dicts must serialise without error."""

    result = _FakeRunResult(
        run_id="run_dict",
        debug_trace=[
            {
                "stage_id": "s1",
                "stage_name": "harness.run",
                "started_at": "2026-09-02T00:00:00+00:00",
                "cost_ms": 0,
                "inputs": {},
                "raw_api_data": {},
                "branch_hit": None,
                "outputs": {},
                "error": None,
                "final": False,
            }
        ],
    )
    run_store.save_run_result("run_dict", result)
    loaded = run_store.load_run_result("run_dict")
    assert loaded is not None
    assert loaded["debug_trace"][0]["stage_name"] == "harness.run"


def test_reset_for_tests_wipes_everything(run_store) -> None:
    run_store.save_run_result("run_x", _FakeRunResult(run_id="run_x"))
    run_store.save_run_result("run_y", _FakeRunResult(run_id="run_y"))
    run_store.reset_for_tests()
    assert run_store.list_run_ids() == []


# ---------------------------------------------------------------------------
# Router / HTTP tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from app.api.main import app

    return TestClient(app)


def test_debug_trace_endpoint_returns_persisted_stages(client, run_store) -> None:
    run_store.save_run_result(
        "run_http",
        _FakeRunResult(
            run_id="run_http",
            status="success",
            debug_trace=[
                _FakeStage(stage_id="s1", stage_name="plan"),
                _FakeStage(stage_id="s2", stage_name="execute", final=True),
            ],
        ),
    )
    response = client.get("/runs/run_http/debug-trace")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run_http"
    assert [stage["stage_name"] for stage in body["stages"]] == ["plan", "execute"]
    assert body["stages"][1]["final"] is True


def test_debug_trace_endpoint_404_for_unknown_run(client) -> None:
    response = client.get("/runs/ghost/debug-trace")
    assert response.status_code == 404


def test_list_runs_endpoint(client, run_store) -> None:
    run_store.save_run_result("run_a", _FakeRunResult(run_id="run_a"))
    run_store.save_run_result("run_b", _FakeRunResult(run_id="run_b"))
    response = client.get("/runs")
    assert response.status_code == 200
    assert response.json()["run_ids"] == ["run_a", "run_b"]
