"""P0-3 — ``run_decisions`` REST router and decision service.

The harness side of the equation is already exercised by
``test_authority_and_gateway.py``. This suite covers the persistent
side: the service upserts pending records, the API exposes them, and
``confirm`` / ``decline`` round-trip cleanly.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def decision_service(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Reload the decision service with a tmp path so tests can't
    collide with real persisted data."""

    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    monkeypatch.syspath_prepend(str(tmp_path))

    # Reset module so it picks up the tmp RUNTIME_DIR.
    for module_name in [
        "app.api.services.decision_service",
        "app.api.routers.run_decisions",
    ]:
        sys.modules.pop(module_name, None)

    service = importlib.import_module("app.api.services.decision_service")
    # The module picked up ``Path("agent-workspace/runtime")`` at import
    # time — point its store at our tmp dir.
    service.RUNTIME_DIR = runtime
    service.DECISIONS = service.JsonStore(runtime / "run_decisions.json")
    return service


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Boot a TestClient against the real FastAPI app, but with the
    decision store pointed at a tmp dir so we never write to
    ``agent-workspace/runtime``. Each test gets a fresh dir so cross-test
    state cannot leak."""

    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)

    # Reload decision service and the routers package so the runtime_dir
    # patch takes effect everywhere. Popping ``app.api.routers`` itself
    # forces a fresh re-import of every submodule on the next main import
    # — otherwise the cached package would still expose stale function
    # references whose ``__globals__['DECISIONS']`` points at the original
    # production store.
    for module_name in [
        "app.api.services.decision_service",
        "app.api.routers",
        "app.api.routers.run_decisions",
    ]:
        sys.modules.pop(module_name, None)
    service = importlib.import_module("app.api.services.decision_service")
    service.RUNTIME_DIR = runtime
    service.DECISIONS = service.JsonStore(runtime / "run_decisions.json")

    # Now import the FastAPI app so the router picks up the patched module.
    for module_name in ["app.api.main", "app.api.routers.run_decisions"]:
        sys.modules.pop(module_name, None)
    main_module = importlib.import_module("app.api.main")
    test_client = TestClient(main_module.app)
    # Start every test with an empty store.
    service.DECISIONS.write([])
    return test_client


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


def test_upsert_pending_records_metadata(decision_service) -> None:
    record = decision_service.upsert_pending(
        run_id="r1",
        step_id="s1",
        agent_id="ui_builder",
        authority="L2",
        task="render",
        artifact_count=2,
    )
    assert record["status"] == "pending"
    assert record["run_id"] == "r1"
    assert record["step_id"] == "s1"
    assert record["authority"] == "L2"
    assert record["artifact_count"] == 2
    assert "created_at" in record


def test_upsert_pending_is_idempotent(decision_service) -> None:
    first = decision_service.upsert_pending(
        run_id="r1", step_id="s1", agent_id="x", authority="L2", task="t", artifact_count=0
    )
    second = decision_service.upsert_pending(
        run_id="r1", step_id="s1", agent_id="x", authority="L2", task="t", artifact_count=0
    )
    assert first["created_at"] == second["created_at"]
    # Only one record exists.
    assert len(decision_service.DECISIONS.read()) == 1


def test_confirm_flips_status_and_preserves_actor(decision_service) -> None:
    decision_service.upsert_pending(
        run_id="r1", step_id="s1", agent_id="x", authority="L2", task="t", artifact_count=0
    )
    decision = decision_service.confirm_step(
        run_id="r1", step_id="s1", actor="alice", note="looks good"
    )
    assert decision["status"] == "applied"
    assert decision["confirmed_by"] == "alice"
    assert decision["note"] == "looks good"


def test_confirm_is_idempotent(decision_service) -> None:
    decision_service.upsert_pending(
        run_id="r1", step_id="s1", agent_id="x", authority="L2", task="t", artifact_count=0
    )
    first = decision_service.confirm_step(run_id="r1", step_id="s1", actor="alice")
    stamp = first["updated_at"]
    second = decision_service.confirm_step(run_id="r1", step_id="s1", actor="bob")
    # The second call is a no-op — actor stays as alice, timestamp is stable.
    assert second["confirmed_by"] == "alice"
    assert second["updated_at"] == stamp


def test_decline_records_reason(decision_service) -> None:
    decision_service.upsert_pending(
        run_id="r1", step_id="s1", agent_id="x", authority="L2", task="t", artifact_count=0
    )
    decision = decision_service.decline_step(
        run_id="r1", step_id="s1", actor="bob", reason="out of scope"
    )
    assert decision["status"] == "rejected"
    assert decision["declined_by"] == "bob"
    assert decision["reason"] == "out of scope"


def test_decline_after_confirm_is_rejected(decision_service) -> None:
    decision_service.upsert_pending(
        run_id="r1", step_id="s1", agent_id="x", authority="L2", task="t", artifact_count=0
    )
    decision_service.confirm_step(run_id="r1", step_id="s1")
    # Decline must not overwrite the confirm.
    decision = decision_service.decline_step(run_id="r1", step_id="s1", reason="too late")
    assert decision["status"] == "applied"
    assert "reason" not in decision or decision.get("reason") != "too late"


def test_confirm_unknown_step_raises(decision_service) -> None:
    with pytest.raises(KeyError):
        decision_service.confirm_step(run_id="r1", step_id="missing")


def test_list_pending_filters_to_pending_only(decision_service) -> None:
    decision_service.upsert_pending(
        run_id="r1", step_id="s1", agent_id="x", authority="L2", task="t", artifact_count=0
    )
    decision_service.upsert_pending(
        run_id="r1", step_id="s2", agent_id="x", authority="L3", task="t", artifact_count=0
    )
    decision_service.confirm_step(run_id="r1", step_id="s1")
    pending = decision_service.list_pending_confirmations()
    assert {item["step_id"] for item in pending} == {"s2"}


# ---------------------------------------------------------------------------
# Router / HTTP tests
# ---------------------------------------------------------------------------


def test_router_pending_endpoint_lists_all(client) -> None:
    client.post(
        "/runs/r1/pending-confirmations",
        json={
            "step_id": "s1",
            "agent_id": "ui_builder",
            "authority": "L2",
            "task": "render",
            "artifact_count": 2,
        },
    )
    response = client.get("/runs/r1/pending-confirmations")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "r1"
    assert len(body["pending_confirmations"]) == 1
    assert body["pending_confirmations"][0]["step_id"] == "s1"


def test_router_global_endpoint_aggregates(client) -> None:
    client.post(
        "/runs/r1/pending-confirmations",
        json={"step_id": "s1", "agent_id": "x", "authority": "L2", "task": "", "artifact_count": 0},
    )
    client.post(
        "/runs/r2/pending-confirmations",
        json={"step_id": "s2", "agent_id": "y", "authority": "L3", "task": "", "artifact_count": 0},
    )
    response = client.get("/runs/pending-confirmations")
    assert response.status_code == 200
    body = response.json()
    run_ids = {entry["run_id"] for entry in body["pending_confirmations"]}
    assert run_ids == {"r1", "r2"}


def test_router_confirm_endpoint_returns_updated_record(client) -> None:
    client.post(
        "/runs/r1/pending-confirmations",
        json={"step_id": "s1", "agent_id": "x", "authority": "L2", "task": "", "artifact_count": 0},
    )
    response = client.post(
        "/runs/r1/steps/s1/confirm",
        json={"actor": "alice", "note": "approved"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["status"] == "applied"
    assert body["decision"]["confirmed_by"] == "alice"


def test_router_decline_endpoint_returns_updated_record(client) -> None:
    client.post(
        "/runs/r1/pending-confirmations",
        json={"step_id": "s1", "agent_id": "x", "authority": "L3", "task": "", "artifact_count": 0},
    )
    response = client.post(
        "/runs/r1/steps/s1/decline",
        json={"actor": "bob", "reason": "risky"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["status"] == "rejected"
    assert body["decision"]["reason"] == "risky"


def test_router_confirm_returns_404_for_missing(client) -> None:
    response = client.post(
        "/runs/r1/steps/ghost/confirm",
        json={"actor": "alice"},
    )
    assert response.status_code == 404


def test_router_read_decision_endpoint(client) -> None:
    client.post(
        "/runs/r1/pending-confirmations",
        json={"step_id": "s1", "agent_id": "x", "authority": "L2", "task": "", "artifact_count": 0},
    )
    response = client.get("/runs/r1/steps/s1/decision")
    assert response.status_code == 200
    assert response.json()["decision"]["status"] == "pending"

    response = client.get("/runs/r1/steps/ghost/decision")
    assert response.status_code == 404


def test_router_health_still_works(client) -> None:
    """The router addition should not break the baseline endpoints."""

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}