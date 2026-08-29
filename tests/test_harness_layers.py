from __future__ import annotations

from agenthub import HarnessRunner
from agenthub.adapters.base import AgentTask
from agenthub.application.agents.runtime_profile import AgentRuntimeProfile
from agenthub.domain.run import RunContext
from agenthub.harness.fallback import FallbackChain
from agenthub.harness.limits import RunLimits
from agenthub.harness.permission import tool_policy_for
from agenthub.policies import AgentPolicy, RunPolicy


def _context(message: str = "hello") -> RunContext:
    return RunContext(
        conversation_id="conv_demo",
        message=message,
        history=[],
        selected_agents=["orchestrator", "ui_builder", "code_reviewer"],
    )


class _FailingAdapter:
    id = "broken"
    name = "Broken"
    capabilities: list[str] = []

    def run(self, task: AgentTask, context: RunContext):  # noqa: ANN001
        raise RuntimeError("boom")


def test_tool_policy_for_denies_all_tools_without_profile() -> None:
    policy = tool_policy_for(None)

    assert not policy.allows("preview_tool")
    assert not policy.allows("deploy_tool")


def test_tool_policy_for_denies_all_tools_for_empty_profile() -> None:
    profile = AgentRuntimeProfile(id="agent", name="Agent", adapter="mock")

    assert not tool_policy_for(profile).allows("preview_tool")


def test_tool_policy_for_allows_configured_tools() -> None:
    profile = AgentRuntimeProfile(
        id="agent", name="Agent", adapter="mock", tools=["preview_tool"]
    )
    policy = tool_policy_for(profile)

    assert policy.allows("preview_tool")
    assert not policy.allows("deploy_tool")


def test_run_limits_enforce_step_budget() -> None:
    limits = RunLimits(run_policy=RunPolicy(max_steps=2))

    assert limits.allows_step(0)
    assert limits.allows_step(1)
    assert not limits.allows_step(2)


def test_fallback_chain_returns_first_success_with_note() -> None:
    chain = FallbackChain()

    result = chain.run(
        "ui_builder",
        AgentTask(agent_id="ui_builder", instruction="build"),
        _context(),
        "provider timeout",
    )

    assert result is not None
    assert result.status == "success"
    assert "Primary adapter failed" in result.messages[0]["content"]
    assert "provider timeout" in result.messages[0]["content"]


def test_fallback_chain_returns_none_when_all_fallbacks_fail() -> None:
    chain = FallbackChain(adapter_factories=[lambda agent_id: _FailingAdapter()])

    result = chain.run(
        "broken",
        AgentTask(agent_id="broken", instruction="build"),
        _context(),
        "boom",
    )

    assert result is None


def test_runner_step_limit_skips_excess_steps() -> None:
    runner = HarnessRunner(
        limits=RunLimits(run_policy=RunPolicy(max_steps=1)),
    )

    result = runner.run(_context("Build a React Todo page"))

    assert result.status == "partial_success"
    skipped_events = [
        event for event in result.events if event.payload.get("reason") == "run step limit exceeded"
    ]
    assert [event.payload["agent_id"] for event in skipped_events] == ["code_reviewer"]


def test_runner_agent_policy_restricts_dispatch() -> None:
    runner = HarnessRunner(agent_policy=AgentPolicy(["orchestrator"]))

    result = runner.run(_context("Build a React Todo page"))

    senders = {message["sender"] for message in result.messages}
    assert senders == {"orchestrator"}
