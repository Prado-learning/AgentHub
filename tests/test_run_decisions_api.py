"""Durable decisions and real approval/resume API, including stale and duplicate requests."""

import pytest
from fastapi.testclient import TestClient
from app.api.main import app
from app.api.services import (
    decision_service as decisions,
    execution_service,
    conversation_service,
    run_store,
)
from agenthub.domain.run import RunContext
from agenthub.domain.plan import Plan, PlanStep
from agenthub.infrastructure.config.paths import conversation_workspace
from agenthub.tools.builtin import deploy


@pytest.fixture
def client():
    return TestClient(app)


def seed(run="r1", step="s1"):
    return decisions.upsert_pending(
        run_id=run,
        step_id=step,
        agent_id="orchestrator",
        authority="L3",
        task="deploy",
        artifact_count=0,
        fingerprint="a" * 64,
    )


def pending_run():
    conversation_service.get_conversation("conv_demo")
    context = RunContext(
        conversation_id="conv_demo",
        message="deploy",
        history=[],
        selected_agents=["orchestrator"],
        workspace_dir=str(conversation_workspace("conv_demo")),
    )
    result = execution_service.execute_context(
        context,
        plan=Plan(
            steps=[
                PlanStep(
                    id="deploy",
                    agent_id="orchestrator",
                    kind="tool",
                    task="Deploy reviewed HTML",
                    tools=["deploy_tool"],
                    arguments={"deploy_tool": {"preview_html": "<h1>Reviewed</h1>"}},
                )
            ],
            reason="test",
        ),
    )
    execution_service.publish_result(result)
    return result.run_id, decisions.list_pending_confirmations()[0]


def test_upsert_idempotent():
    first = seed()
    assert seed()["created_at"] == first["created_at"]
    assert len(decisions.DECISIONS.read()) == 1


def test_approval_is_not_application():
    seed()
    result = decisions.confirm_step(
        run_id="r1", step_id="s1", actor="alice", note="reviewed"
    )
    assert result["status"] == "approved" and result["confirmed_by"] == "alice"
    assert decisions.confirm_step(run_id="r1", step_id="s1", actor="bob") == result


def test_decline_is_final():
    seed()
    result = decisions.decline_step(run_id="r1", step_id="s1", reason="no")
    assert result["status"] == "rejected" and result["reason"] == "no"
    with pytest.raises(ValueError):
        decisions.confirm_step(run_id="r1", step_id="s1")


def test_decline_after_approval_conflicts():
    seed()
    decisions.confirm_step(run_id="r1", step_id="s1")
    with pytest.raises(ValueError):
        decisions.decline_step(run_id="r1", step_id="s1")


def test_unknown_decision_raises():
    with pytest.raises(KeyError):
        decisions.confirm_step(run_id="missing", step_id="x")


def test_pending_lists_filter(client):
    seed()
    seed("r2", "s2")
    decisions.confirm_step(run_id="r1", step_id="s1")
    assert (
        len(client.get("/runs/pending-confirmations").json()["pending_confirmations"])
        == 1
    )
    assert (
        client.get("/runs/r2/pending-confirmations").json()["pending_confirmations"][0][
            "step_id"
        ]
        == "s2"
    )


def test_no_client_can_fabricate_pending_action(client):
    assert (
        client.post(
            "/runs/r1/pending-confirmations", json={"step_id": "fake"}
        ).status_code
        == 405
    )


def test_confirm_executes_and_is_idempotent(client):
    run, decision = pending_run()
    assert not deploy.DEPLOYMENT_DIR.exists()
    url = f"/runs/{run}/steps/deploy/confirm"
    response = client.post(
        url, json={"fingerprint": decision["fingerprint"], "actor": "alice"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"]["status"] == "applied"
    assert len(list(deploy.DEPLOYMENT_DIR.iterdir())) == 1
    assert (
        client.post(url, json={"fingerprint": decision["fingerprint"]}).status_code
        == 200
    )
    assert len(list(deploy.DEPLOYMENT_DIR.iterdir())) == 1
    assert run_store.load_run_result(run)["status"] == "success"


def test_stale_fingerprint_cannot_execute(client):
    run, decision = pending_run()
    assert (
        client.post(
            f"/runs/{run}/steps/deploy/confirm", json={"fingerprint": "b" * 64}
        ).status_code
        == 409
    )
    assert not deploy.DEPLOYMENT_DIR.exists()


def test_rejection_resumes_without_effect(client):
    run, decision = pending_run()
    response = client.post(
        f"/runs/{run}/steps/deploy/decline",
        json={"fingerprint": decision["fingerprint"], "reason": "no"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"]["status"] == "rejected"
    assert run_store.load_run_result(run)["status"] == "failed"
    assert not deploy.DEPLOYMENT_DIR.exists()


def test_cancel_waiting_action_prevents_confirmation(client):
    run, decision = pending_run()
    assert client.post(f"/runs/{run}/cancel", json={}).json()["status"] == "cancelled"
    assert (
        client.post(
            f"/runs/{run}/steps/deploy/confirm",
            json={"fingerprint": decision["fingerprint"]},
        ).status_code
        == 409
    )
    assert not deploy.DEPLOYMENT_DIR.exists()


def test_missing_and_invalid_confirm(client):
    assert (
        client.post(
            "/runs/missing/steps/no/confirm", json={"fingerprint": "a" * 64}
        ).status_code
        == 404
    )
    assert client.post("/runs/missing/steps/no/confirm", json={}).status_code == 422


def test_read_decision_and_health(client):
    seed()
    assert (
        client.get("/runs/r1/steps/s1/decision").json()["decision"]["status"]
        == "pending"
    )
    assert client.get("/runs/r1/steps/unknown/decision").status_code == 404
    assert client.get("/health").json() == {"status": "ok"}
