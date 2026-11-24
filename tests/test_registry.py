"""Tests for the four extension seams.

These mutate process-global registries, so every test clears them again:
a leaked registration would silently change how later tests build their
adapters and tools.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agenthub.adapters.base import AgentAdapter
from agenthub.sandbox.audit import SandboxReport
from agenthub.sandbox.base import SandboxError


@pytest.fixture(autouse=True)
def _clean_registries():
    from agenthub.registry import clear_registrations

    clear_registrations()
    yield
    clear_registrations()


class _StubAdapter(AgentAdapter):
    def __init__(self) -> None:
        self.ran = False

    def run(self, task, context):  # type: ignore[override]
        self.ran = True
        from agenthub.adapters.base import AgentResult

        return AgentResult(agent_id=task.agent_id, status="success")


def _spec(tmp_path: Path, run_id: str = "run_reg"):
    from agenthub.sandbox.spec import SandboxSpec

    return SandboxSpec(run_id=run_id, workspace_root=tmp_path)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def test_a_registered_tool_overrides_the_builtin_of_the_same_name() -> None:
    from agenthub.registry import register_tool
    from agenthub.tools.executor import build_default_tool_registry

    register_tool("deploy_tool", lambda **kwargs: "overridden")

    registry = build_default_tool_registry()

    assert registry.get("deploy_tool")(title="x") == "overridden"


def test_a_registered_tool_adds_a_new_name() -> None:
    from agenthub.registry import register_tool
    from agenthub.tools.executor import build_default_tool_registry

    register_tool("my_tool", lambda **kwargs: "mine")

    registry = build_default_tool_registry()

    assert "my_tool" in registry.list_ids()
    assert registry.get("my_tool")() == "mine"


def test_the_builtin_tools_are_all_registered() -> None:
    from agenthub.tools.executor import build_default_tool_registry

    ids = build_default_tool_registry().list_ids()

    assert len(ids) == 8
    assert "deploy_tool" in ids


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def test_a_registered_adapter_overrides_the_builtin() -> None:
    from agenthub.adapters.factory import build_agent_adapters
    from agenthub.registry import register_adapter

    register_adapter("mock", lambda **kwargs: _StubAdapter())

    adapters = build_agent_adapters([{"id": "a", "adapter": "mock"}])

    assert isinstance(adapters["a"], _StubAdapter)


def test_a_registered_adapter_adds_a_new_type() -> None:
    from agenthub.adapters.factory import build_agent_adapters
    from agenthub.registry import register_adapter

    register_adapter("my_cli", lambda **kwargs: _StubAdapter())

    adapters = build_agent_adapters([{"id": "a", "adapter": "my_cli"}])

    assert isinstance(adapters["a"], _StubAdapter)


def test_a_misspelled_adapter_fails_loudly_instead_of_mocking() -> None:
    from agenthub.adapters.factory import build_agent_adapters

    with pytest.raises(ValueError, match="Unknown adapter type 'codexx'"):
        build_agent_adapters([{"id": "a", "adapter": "codexx"}])


def test_the_builder_receives_the_resolved_arguments() -> None:
    from agenthub.adapters.factory import build_agent_adapters
    from agenthub.registry import register_adapter

    seen: dict = {}

    def record(**kwargs):
        seen.update(kwargs)
        return _StubAdapter()

    register_adapter("recorder", record)
    build_agent_adapters(
        [{"id": "a", "adapter": "recorder", "capabilities": ["read"]}],
        model="gpt-test",
        api_key="sk-x",
        base_url="https://example.invalid/v1",
    )

    assert seen["agent_id"] == "a"
    assert seen["model"] == "gpt-test"
    assert seen["api_key"] == "sk-x"
    assert seen["base_url"] == "https://example.invalid/v1"
    assert seen["capabilities"] == ["read"]


# ---------------------------------------------------------------------------
# Planners
# ---------------------------------------------------------------------------


def test_a_registered_planner_is_listed() -> None:
    from agenthub.registry import extension_points, register_planner

    register_planner("my_planner", lambda: object())

    assert "my_planner" in extension_points()["planners"]


# ---------------------------------------------------------------------------
# Sandbox backends
# ---------------------------------------------------------------------------


def test_a_registered_backend_is_selectable_by_name(tmp_path, monkeypatch) -> None:
    from agenthub.registry import register_sandbox_backend
    from agenthub.sandbox.manager import SandboxManager

    built: list = []

    class _Recording:
        def __init__(self, spec) -> None:
            self.spec = spec
            built.append(self)

        def start(self) -> None:
            pass

        def stop(self) -> SandboxReport:
            return SandboxReport(run_id=self.spec.run_id, backend="recording")

    register_sandbox_backend("recording", _Recording)
    monkeypatch.setenv("AGENTHUB_SANDBOX_BACKEND", "recording")

    sandbox = SandboxManager().create(_spec(tmp_path))

    assert isinstance(sandbox, _Recording)
    assert built[0] is sandbox


def test_an_unknown_backend_name_fails_loudly(tmp_path, monkeypatch) -> None:
    from agenthub.sandbox.manager import SandboxManager

    monkeypatch.setenv("AGENTHUB_SANDBOX_BACKEND", "firecracker")

    with pytest.raises(SandboxError, match="Unknown sandbox backend"):
        SandboxManager().create(_spec(tmp_path))


def test_an_explicit_factory_overrides_the_environment(tmp_path, monkeypatch) -> None:
    from agenthub.sandbox.backends.local import LocalSandbox
    from agenthub.sandbox.manager import SandboxManager

    monkeypatch.setenv("AGENTHUB_SANDBOX_BACKEND", "does-not-exist")

    sandbox = SandboxManager(backend_factory=LocalSandbox).create(_spec(tmp_path))

    assert isinstance(sandbox, LocalSandbox)


def test_the_local_backend_is_the_default(tmp_path, monkeypatch) -> None:
    from agenthub.sandbox.backends.local import LocalSandbox
    from agenthub.sandbox.manager import backend_name, sandbox_backends

    monkeypatch.delenv("AGENTHUB_SANDBOX_BACKEND", raising=False)

    assert backend_name() == "local"
    assert sandbox_backends()["local"] is LocalSandbox


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


def test_extension_points_report_every_seam() -> None:
    from agenthub.registry import extension_points, register_adapter, register_tool

    register_tool("t1", lambda: None)
    register_adapter("a1", lambda **kw: None)

    points = extension_points()

    assert set(points) == {"adapters", "tools", "planners", "sandbox_backends"}
    assert "t1" in points["tools"]
    assert "a1" in points["adapters"]


def test_the_registry_starts_empty_without_any_registration() -> None:
    from agenthub.registry import extension_points

    points = extension_points()

    assert all(not names for names in points.values())
