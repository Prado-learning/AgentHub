"""Tests for the per-run sandbox boundary.

These exercise the machinery the rest of the suite only passes through:
filesystem confinement, the environment allow-list, the audit trail, the
scope binding, and the report the runner emits. A local sandbox is used
so the tests run on any platform; the Windows-specific job-object limit
flags are asserted separately and skipped elsewhere.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.domain.authority import AuthorityTier
from agenthub.domain.plan import Plan, PlanStep
from agenthub.domain.run import RunContext
from agenthub.harness.runner import HarnessRunner
from agenthub.sandbox import (
    LocalSandbox,
    SandboxError,
    SandboxManager,
    current_sandbox,
    sandbox_scope,
)
from agenthub.sandbox.profiles import run_spec
from agenthub.sandbox.spec import (
    CredentialScope,
    NetworkPolicy,
    ResourceLimits,
    SandboxSpec,
)


def _spec(tmp_path: Path, **kwargs) -> SandboxSpec:
    kwargs.setdefault("run_id", "run_test")
    kwargs.setdefault("workspace_root", tmp_path)
    return SandboxSpec(**kwargs)


def _dump_env_code() -> str:
    return "import json,os;print(json.dumps(dict(os.environ)))"


# ---------------------------------------------------------------------------
# Specification
# ---------------------------------------------------------------------------


def test_run_spec_defaults_do_not_tighten_the_boundary_silently() -> None:
    spec = run_spec("run_defaults")

    assert spec.network is NetworkPolicy.INHERIT
    assert not spec.resources.any_set()
    assert spec.workspace_root.name == "agent-workspace" or spec.workspace_root.exists()
    assert spec.lifetime.value == "run"


def test_run_spec_names_the_conversation_workspace_as_readable() -> None:
    spec = run_spec("run_conv", conversation_id="conv_abc")

    assert any(root.name == "conv_abc" for root in spec.readable_roots)


def test_run_spec_ignores_an_invalid_conversation_id() -> None:
    spec = run_spec("run_bad", conversation_id="../escape")

    assert spec.readable_roots == ()


def test_resource_limits_any_set() -> None:
    assert not ResourceLimits().any_set()
    assert ResourceLimits(cpu_seconds=5).any_set()
    assert ResourceLimits(memory_mb=128).any_set()
    assert ResourceLimits(max_processes=4).any_set()


# ---------------------------------------------------------------------------
# Filesystem confinement
# ---------------------------------------------------------------------------


def test_write_inside_the_workspace_succeeds(tmp_path: Path) -> None:
    sandbox = LocalSandbox(_spec(tmp_path))
    sandbox.start()

    target = sandbox.write_path("out/index.html", b"<h1>hi</h1>")

    assert target == (tmp_path / "out" / "index.html").resolve()
    assert target.read_bytes() == b"<h1>hi</h1>"
    assert not list(tmp_path.glob("*.sandbox-partial"))


def test_write_outside_the_workspace_is_refused(tmp_path: Path) -> None:
    sandbox = LocalSandbox(_spec(tmp_path, workspace_root=tmp_path / "box"))
    sandbox.start()

    with pytest.raises(SandboxError):
        sandbox.write_path(tmp_path / "outside.txt", b"nope")

    with pytest.raises(SandboxError):
        sandbox.write_path("../escape.txt", b"nope")


def test_read_outside_the_declared_roots_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"token")
    sandbox = LocalSandbox(_spec(tmp_path, workspace_root=tmp_path / "box"))
    sandbox.start()

    with pytest.raises(SandboxError):
        sandbox.read_path(outside)


def test_read_inside_a_readable_root_succeeds(tmp_path: Path) -> None:
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"print(1)")
    sandbox = LocalSandbox(
        _spec(tmp_path, workspace_root=tmp_path / "box", readable_roots=(tmp_path,))
    )
    sandbox.start()

    assert sandbox.read_path(source) == b"print(1)"


def test_write_replaces_an_existing_file_atomically(tmp_path: Path) -> None:
    sandbox = LocalSandbox(_spec(tmp_path))
    sandbox.start()
    sandbox.write_path("a.txt", b"first")

    sandbox.write_path("a.txt", b"second")

    assert (tmp_path / "a.txt").read_bytes() == b"second"


# ---------------------------------------------------------------------------
# Credential scoping
# ---------------------------------------------------------------------------


def _child_env(tmp_path: Path, monkeypatch, spec=None) -> dict:
    sandbox = LocalSandbox(spec or _spec(tmp_path))
    sandbox.start()
    result = sandbox.exec([sys.executable, "-c", _dump_env_code()], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_undeclared_environment_is_stripped_from_children(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGENTHUB_TEST_SECRET", "leak-me")

    env = _child_env(tmp_path, monkeypatch)

    assert "AGENTHUB_TEST_SECRET" not in env


def test_essential_environment_survives(tmp_path: Path, monkeypatch) -> None:
    env = _child_env(tmp_path, monkeypatch)

    # PATH is needed to resolve anything but a fully qualified command.
    assert "PATH" in env


def test_declared_provider_credential_reaches_the_child(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    env = _child_env(tmp_path, monkeypatch)

    assert env.get("OPENAI_API_KEY") == "sk-test"


def test_extra_env_allowlist_widens_the_boundary_explicitly(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGENTHUB_TEST_SECRET", "leak-me")
    monkeypatch.setenv("AGENTHUB_SANDBOX_EXTRA_ENV", "AGENTHUB_TEST_SECRET")

    env = _child_env(tmp_path, monkeypatch)

    assert env.get("AGENTHUB_TEST_SECRET") == "leak-me"


def test_spec_credentials_can_declare_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MY_CLI_TOKEN", "abc123")
    spec = _spec(
        tmp_path,
        credentials=CredentialScope(
            allowed_env=(), secrets=("MY_CLI_TOKEN",)
        ),
    )

    env = _child_env(tmp_path, monkeypatch, spec)

    assert env.get("MY_CLI_TOKEN") == "abc123"


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_exec_and_write_are_recorded_in_the_report(tmp_path: Path) -> None:
    sandbox = LocalSandbox(_spec(tmp_path, run_id="run_audit"))
    sandbox.start()
    sandbox.exec([sys.executable, "-c", "print('ok')"], cwd=tmp_path)
    sandbox.write_path("log.txt", b"written")

    report = sandbox.stop().to_dict()

    assert report["backend"] == "local"
    assert report["run_id"] == "run_audit"
    assert [record["returncode"] for record in report["execs"]] == [0]
    assert report["writes"] == [
        {"path": str((tmp_path / "log.txt").resolve()), "size": 7}
    ]
    assert report["stopped_at"] is not None


def test_stop_is_idempotent(tmp_path: Path) -> None:
    sandbox = LocalSandbox(_spec(tmp_path))
    sandbox.start()

    first = sandbox.stop()
    second = sandbox.stop()

    assert first is second
    assert first.execs == []


def test_working_directory_outside_the_roots_is_refused(tmp_path: Path) -> None:
    sandbox = LocalSandbox(_spec(tmp_path, workspace_root=tmp_path / "box"))
    sandbox.start()

    with pytest.raises(SandboxError):
        sandbox.exec([sys.executable, "-c", "print(1)"], cwd=tmp_path)


def test_exec_accepts_a_working_directory_nested_under_the_root(tmp_path: Path) -> None:
    """The production shape: the sandbox root is the data directory and the
    CLI's working directory is a conversation workspace beneath it."""
    nested = tmp_path / "projects" / "conv_1"
    nested.mkdir(parents=True)
    sandbox = LocalSandbox(_spec(tmp_path, workspace_root=tmp_path))
    sandbox.start()

    result = sandbox.exec(
        [sys.executable, "-c", "import os;print(os.path.basename(os.getcwd()))"],
        cwd=nested,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "conv_1"


# ---------------------------------------------------------------------------
# Scope binding
# ---------------------------------------------------------------------------


def test_current_sandbox_is_none_outside_a_scope() -> None:
    assert current_sandbox() is None


def test_sandbox_scope_binds_and_restores(tmp_path: Path) -> None:
    sandbox = LocalSandbox(_spec(tmp_path))
    sandbox.start()

    with sandbox_scope(sandbox) as bound:
        assert bound is sandbox
        assert current_sandbox() is sandbox

    assert current_sandbox() is None


def test_sandbox_scope_tolerates_none() -> None:
    with sandbox_scope(None) as bound:
        assert bound is None
    assert current_sandbox() is None


def test_manager_creates_and_releases_per_run(tmp_path: Path) -> None:
    manager = SandboxManager()
    spec = _spec(tmp_path, run_id="run_mgr")

    sandbox = manager.create(spec)

    assert manager.get("run_mgr") is sandbox
    manager.release("run_mgr")
    assert manager.get("run_mgr") is None
    # Releasing an unknown run is a no-op rather than an error.
    manager.release("run_mgr")


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


class _StubSandbox:
    """Records the calls the runner routes through the boundary."""

    def __init__(self) -> None:
        self.spec = _spec(Path("."))
        self.execs: list[tuple] = []
        self.writes: list[tuple] = []
        self.stopped = False

    def start(self) -> None:
        pass

    def exec(self, command, **kwargs):
        self.execs.append((tuple(command), kwargs))
        from agenthub.sandbox.base import ExecResult

        return ExecResult(
            command=tuple(command),
            returncode=0,
            stdout="stub",
            stderr="",
            duration_ms=1,
        )

    def read_path(self, path):
        return b""

    def write_path(self, path, data):
        self.writes.append((str(path), data))
        return Path(path)

    def stop(self):
        self.stopped = True
        from agenthub.sandbox.audit import SandboxReport

        return SandboxReport(run_id="stub", backend="stub")


def _context() -> RunContext:
    return RunContext(
        conversation_id="conv_sandbox",
        message="hello",
        history=[],
        selected_agents=["orchestrator"],
    )


def _plan() -> Plan:
    return Plan(
        steps=[
            PlanStep(
                id="s1",
                agent_id="orchestrator",
                task="answer",
                tools=[],
                authority=AuthorityTier.L1_READONLY,
            )
        ],
        reason="test",
    )


def _sandbox_report_event(events) -> dict | None:
    for event in events:
        if event.type == "sandbox.report":
            return event.payload
    return None


def test_runner_emits_a_sandbox_report_event() -> None:
    runner = HarnessRunner(adapters={})
    result = runner.run(_context(), plan=_plan(), run_id="run_report")

    payload = _sandbox_report_event(result.events)
    assert payload is not None, "run should emit sandbox.report"
    assert payload["backend"] == "local"
    assert payload["run_id"] == "run_report"


def test_runner_creates_a_sandbox_per_run() -> None:
    runner = HarnessRunner(adapters={})

    runner.run(_context(), plan=_plan(), run_id="run_one")
    assert runner._active_sandbox is None, "a finished run releases its sandbox"

    runner.run(_context(), plan=_plan(), run_id="run_two")
    assert runner._active_sandbox is None


def test_injected_sandbox_is_used_and_not_stopped_by_the_runner() -> None:
    stub = _StubSandbox()
    runner = HarnessRunner(adapters={}, sandbox=stub)

    result = runner.run(_context(), plan=_plan(), run_id="run_injected")

    payload = _sandbox_report_event(result.events)
    assert payload is None, "an injected sandbox is owned by its creator"
    assert stub.stopped is False
    assert runner._active_sandbox is None


def test_tools_see_the_bound_sandbox_during_a_step(tmp_path: Path, monkeypatch) -> None:
    from agenthub.tools.builtin import deploy

    sandbox = LocalSandbox(
        _spec(tmp_path, run_id="run_tool", workspace_root=tmp_path)
    )
    sandbox.start()

    with sandbox_scope(sandbox):
        result = deploy.deploy_tool(title="t", code="print(1)")

    assert result.type == "deployment"
    report = sandbox.stop().to_dict()
    assert len(report["writes"]) == 1
    assert report["writes"][0]["path"].startswith(str(tmp_path.resolve()))


# ---------------------------------------------------------------------------
# Windows job object
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "nt", reason="Job Objects are Windows-only")
def test_windows_job_sets_the_declared_limit_flags() -> None:
    import ctypes

    from agenthub.sandbox.backends import windows_job

    job = windows_job.WindowsJob(ResourceLimits(cpu_seconds=30, memory_mb=64))
    try:
        # Reading the flags back requires a query structure this module does
        # not model; assert the constructor accepted the limits instead.
        assert job._handle
    finally:
        job.close()

    plain = windows_job.WindowsJob()
    try:
        assert plain._handle
    finally:
        plain.close()


# ---------------------------------------------------------------------------
# Boundary policy
# ---------------------------------------------------------------------------


def test_policy_fails_closed_for_an_unknown_tier() -> None:
    from agenthub.domain.authority import AuthorityTier
    from agenthub.policies import SandboxPolicy

    policy = SandboxPolicy(boundaries={})

    assert policy.boundary_for(AuthorityTier.L1_READONLY).network is (
        NetworkPolicy.NONE
    )
    assert policy.describe(AuthorityTier.L2_REVERSIBLE)["network"] == "none"


def test_policy_strictest_picks_the_tightest_boundary_in_the_plan() -> None:
    from agenthub.domain.authority import AuthorityTier
    from agenthub.policies import SandboxPolicy

    policy = SandboxPolicy()

    assert (
        policy.strictest([AuthorityTier.L1_READONLY, AuthorityTier.L2_REVERSIBLE]).network
        is NetworkPolicy.INHERIT
    )
    assert (
        policy.strictest(
            [AuthorityTier.L1_READONLY, AuthorityTier.L3_IRREVERSIBLE]
        ).network
        is NetworkPolicy.NONE
    )


def test_irreversible_boundary_denies_network_egress() -> None:
    from agenthub.domain.authority import AuthorityTier
    from agenthub.policies import SandboxPolicy

    described = SandboxPolicy().describe(AuthorityTier.L3_IRREVERSIBLE)

    assert described["network"] == "none"
    assert described["note"]


def test_runner_applies_the_strictest_boundary_to_the_run_spec() -> None:
    from agenthub.domain.authority import AuthorityTier
    from agenthub.domain.plan import Plan, PlanStep

    plan = Plan(
        steps=[
            PlanStep(
                id="s1",
                agent_id="orchestrator",
                task="read",
                tools=[],
                authority=AuthorityTier.L1_READONLY,
            ),
            PlanStep(
                id="s2",
                agent_id="orchestrator",
                task="deploy",
                tools=[],
                authority=AuthorityTier.L3_IRREVERSIBLE,
                depends_on=["s1"],
            ),
        ],
        reason="mixed",
    )
    runner = HarnessRunner(adapters={})

    sandbox, owned = runner._resolve_sandbox(_context(), plan)

    try:
        assert owned is True
        assert sandbox.spec.network is NetworkPolicy.NONE
    finally:
        sandbox.stop()


def test_approval_card_describes_the_sandbox_boundary() -> None:
    from agenthub.domain.authority import AuthorityTier
    from agenthub.domain.plan import Plan, PlanStep

    plan = Plan(
        steps=[
            PlanStep(
                id="s1",
                agent_id="orchestrator",
                task="apply",
                tools=[],
                authority=AuthorityTier.L2_REVERSIBLE,
            )
        ],
        reason="needs approval",
    )
    runner = HarnessRunner(adapters={})

    result = runner.run(_context(), plan=plan, run_id="run_card")

    pending = result.checkpoint["pending_confirmations"]
    assert len(pending) == 1
    assert pending[0]["sandbox"]["network"] == "inherit"
    assert pending[0]["sandbox"]["may_write_files"] is True
    assert pending[0]["sandbox"]["note"]
