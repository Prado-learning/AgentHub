"""Tests for the run lifecycle supervisor in isolation.

The supervisor exists so the harness can run without the HTTP
application. These tests use in-memory ports to prove exactly that: no
FastAPI, no SQLite, no conversation store — just a plan, a run record and
a sandbox.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agenthub.domain.authority import AuthorityTier
from agenthub.domain.plan import Plan, PlanStep
from agenthub.domain.run import RunContext
from agenthub.harness.supervisor import RunSupervisor


class _FakeRunStore:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def load(self, run_id: str) -> dict | None:
        return self.records.get(run_id)

    def update(self, run_id: str, patch: dict) -> dict:
        record = self.records.setdefault(run_id, {})
        record.update(patch)
        return record

    def mutate(self, run_id: str, fn) -> dict:
        self.records[run_id] = fn(self.records.setdefault(run_id, {}))
        return self.records[run_id]

    def save_result(self, run_id: str, result) -> None:
        self.update(run_id, {"raw_messages": result.messages})

    def list_run_ids(self) -> list[str]:
        return list(self.records)


class _FakeDecisions:
    def __init__(self) -> None:
        self.pending: list[tuple[str, dict]] = []
        self.cancelled: list[str] = []
        self.requeued: list[tuple[str, str]] = []
        self.marked: list[tuple[str, str, str]] = []

    def list_for_run(self, run_id: str) -> list[dict]:
        return []

    def upsert_pending(self, run_id: str, **pending) -> None:
        self.pending.append((run_id, pending))

    def mark_execution(self, run_id: str, step_id: str, state: str) -> None:
        self.marked.append((run_id, step_id, state))

    def cancel_pending(self, run_id: str) -> None:
        self.cancelled.append(run_id)

    def requeue_approved(self, run_id: str, note: str) -> None:
        self.requeued.append((run_id, note))


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, result, *, generation_group_id=None) -> dict:
        self.published.append(result.run_id)
        return {"run_id": result.run_id, "status": result.status}


def _supervisor() -> RunSupervisor:
    return RunSupervisor(
        run_store=_FakeRunStore(),
        decisions=_FakeDecisions(),
        publisher=_FakePublisher(),
        adapter_factory=lambda *args, **kwargs: {},
    )


def _context() -> RunContext:
    return RunContext(
        conversation_id="conv_sup",
        message="hello",
        history=[],
        selected_agents=["orchestrator"],
    )


def _plan(*tiers: AuthorityTier) -> Plan:
    return Plan(
        steps=[
            PlanStep(
                id=f"s{index}",
                agent_id="orchestrator",
                task="answer",
                tools=[],
                authority=tier,
            )
            for index, tier in enumerate(tiers, start=1)
        ],
        reason="test",
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def test_execute_context_runs_the_plan_and_records_status() -> None:
    supervisor = _supervisor()

    result = supervisor.execute_context(
        _context(), plan=_plan(AuthorityTier.L1_READONLY), run_id="run_ok"
    )

    assert result.run_id == "run_ok"
    record = supervisor.run_store.load("run_ok")
    assert record["status"] == "running"
    assert record["conversation_id"] == "conv_sup"
    assert "raw_messages" in record


def test_execute_context_releases_the_sandbox_when_it_finishes() -> None:
    supervisor = _supervisor()

    supervisor.execute_context(_context(), plan=_plan(), run_id="run_sb")

    assert supervisor.sandbox_manager.get("run_sb") is None


def test_execute_context_emits_events_through_the_run_store() -> None:
    supervisor = _supervisor()

    result = supervisor.execute_context(
        _context(), plan=_plan(AuthorityTier.L1_READONLY), run_id="run_ev"
    )

    record = supervisor.run_store.load("run_ev")
    assert record["events"], "events should be appended to the run record"
    assert any(e["type"] == "run.started" for e in record["events"])
    assert result.events


def test_execute_context_does_not_publish() -> None:
    supervisor = _supervisor()

    supervisor.execute_context(_context(), plan=_plan(), run_id="run_np")

    assert supervisor.publisher.published == []


def test_execute_context_records_pending_confirmations() -> None:
    supervisor = _supervisor()

    result = supervisor.execute_context(
        _context(), plan=_plan(AuthorityTier.L2_REVERSIBLE), run_id="run_wait"
    )

    assert result.status == "waiting_approval"
    assert len(supervisor.decisions.pending) == 1
    run_id, pending = supervisor.decisions.pending[0]
    assert run_id == "run_wait"
    assert pending["step_id"] == "s1"
    assert "sandbox" in pending, "the approval card carries the boundary"


# ---------------------------------------------------------------------------
# Resume and cancel
# ---------------------------------------------------------------------------


def test_resume_run_refuses_a_run_that_is_not_waiting() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update("run_x", {"status": "running"})

    with pytest.raises(ValueError, match="not waiting for approval"):
        supervisor.resume_run("run_x")


def test_resume_run_refuses_an_unknown_run() -> None:
    supervisor = _supervisor()

    with pytest.raises(ValueError, match="not waiting for approval"):
        supervisor.resume_run("run_missing")


def test_resume_run_publishes_the_resumed_result() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update(
        "run_wait",
        {"status": "waiting_approval", "context": _context().__dict__},
    )

    response = supervisor.resume_run("run_wait")

    assert response["run_id"] == "run_wait"
    assert supervisor.publisher.published == ["run_wait"]


def test_resume_run_discards_the_paused_control() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update(
        "run_ctrl",
        {"status": "waiting_approval", "context": _context().__dict__},
    )
    supervisor.control_for("run_ctrl").llm_calls = 99

    supervisor.resume_run("run_ctrl")

    assert supervisor.control_for("run_ctrl").llm_calls == 0


def test_cancel_run_refuses_an_unknown_run() -> None:
    supervisor = _supervisor()

    with pytest.raises(KeyError):
        supervisor.cancel_run("run_nope")


def test_cancel_run_leaves_a_finished_run_alone() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update("run_done", {"status": "success"})

    snapshot = supervisor.cancel_run("run_done")

    assert snapshot["status"] == "success"


def test_cancel_run_marks_a_running_run_cancelling() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update("run_live", {"status": "running"})

    supervisor.cancel_run("run_live")

    record = supervisor.run_store.load("run_live")
    assert record["status"] == "cancelling"
    assert record["cancel_requested"] is True
    assert supervisor.control_for("run_live").cancelled.is_set()


def test_cancel_run_cancels_a_waiting_run_outright() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update("run_wait", {"status": "waiting_approval"})

    supervisor.cancel_run("run_wait")

    assert supervisor.run_store.load("run_wait")["status"] == "cancelled"
    assert supervisor.decisions.cancelled == ["run_wait"]


# ---------------------------------------------------------------------------
# Concurrency guard
# ---------------------------------------------------------------------------


def test_claim_run_allows_one_active_run_per_conversation() -> None:
    supervisor = _supervisor()

    supervisor.claim_run("run_a", "conv_one")

    assert supervisor.run_store.load("run_a")["status"] == "queued"
    with pytest.raises(ValueError, match="already has an active run"):
        supervisor.claim_run("run_b", "conv_one")


def test_claim_run_allows_a_new_run_once_the_previous_finished() -> None:
    supervisor = _supervisor()
    supervisor.claim_run("run_a", "conv_one")
    supervisor.run_store.update("run_a", {"status": "success"})

    supervisor.claim_run("run_b", "conv_one")

    assert supervisor.run_store.load("run_b")["status"] == "queued"


def test_active_run_for_finds_the_occupying_run() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update("run_a", {"conversation_id": "c", "status": "running"})
    supervisor.run_store.update("run_b", {"conversation_id": "c", "status": "success"})

    assert supervisor.active_run_for("c") == "run_a"
    assert supervisor.active_run_for("other") is None


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


def test_recovery_marks_inflight_runs_interrupted_and_does_not_replay() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update("run_mid", {"status": "running"})
    supervisor.run_store.update("run_q", {"status": "queued"})

    supervisor.recover_interrupted_runs()

    assert supervisor.run_store.load("run_mid")["status"] == "interrupted"
    assert "effects may have occurred" in supervisor.run_store.load("run_mid")["error"]
    assert supervisor.run_store.load("run_q")["status"] == "interrupted"
    assert supervisor.publisher.published == []


def test_recovery_requeues_approvals_granted_before_the_restart() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update(
        "run_wait",
        {
            "status": "waiting_approval",
            "conversation_id": "conv_sup",
            "checkpoint": {
                "pending_confirmations": [
                    {
                        "step_id": "s1",
                        "agent_id": "orchestrator",
                        "authority": "L2",
                        "task": "t",
                        "artifact_count": 0,
                        "fingerprint": "f" * 64,
                    }
                ]
            },
        },
    )

    supervisor.recover_interrupted_runs()

    assert supervisor.decisions.requeued == [
        ("run_wait", "Server restarted before dispatch; please review again.")
    ]
    assert len(supervisor.decisions.pending) == 1


def test_recovery_republishes_an_unpublished_finished_run() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update(
        "run_pub",
        {
            "run_id": "run_pub",
            "status": "success",
            "conversation_id": "conv_sup",
            "raw_messages": [{"role": "agent", "content": "hi"}],
        },
    )

    supervisor.recover_interrupted_runs()

    assert supervisor.publisher.published == ["run_pub"]


def test_recovery_skips_a_run_that_was_already_published() -> None:
    supervisor = _supervisor()
    supervisor.run_store.update(
        "run_pub",
        {
            "status": "success",
            "conversation_id": "conv_sup",
            "raw_messages": [{"role": "agent", "content": "hi"}],
            "response": {"run_id": "run_pub"},
        },
    )

    supervisor.recover_interrupted_runs()

    assert supervisor.publisher.published == []


# ---------------------------------------------------------------------------
# Sandbox ownership
# ---------------------------------------------------------------------------


def test_sandbox_survives_a_run_that_raises(tmp_path, monkeypatch) -> None:
    supervisor = _supervisor()

    class _Exploding:
        def __init__(self, **kwargs) -> None:
            pass

        def run(self, *args, **kwargs):
            raise RuntimeError("boom")

    from agenthub.harness import supervisor as supervisor_module

    monkeypatch.setattr(supervisor_module, "HarnessRunner", _Exploding)

    with pytest.raises(RuntimeError, match="boom"):
        supervisor.execute_context(_context(), plan=_plan(), run_id="run_boom")

    assert supervisor.sandbox_manager.get("run_boom") is None
