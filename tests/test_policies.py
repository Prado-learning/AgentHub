from agenthub.policies import AgentPolicy, RunPolicy, ToolPolicy


def test_agent_policy_allows_configured_agent() -> None:
    policy = AgentPolicy(["orchestrator"])

    assert policy.allows("orchestrator")
    assert not policy.allows("ui_builder")


def test_tool_policy_allows_all_when_unconfigured() -> None:
    policy = ToolPolicy()

    assert policy.allows("preview_tool")


def test_tool_policy_empty_list_denies_everything() -> None:
    policy = ToolPolicy(allowed_tools=[])

    assert not policy.allows("preview_tool")
    assert not policy.allows("deploy_tool")


def test_tool_policy_allows_only_configured_tools() -> None:
    policy = ToolPolicy(allowed_tools=["preview_tool"])

    assert policy.allows("preview_tool")
    assert not policy.allows("deploy_tool")


def test_run_policy_limits_steps() -> None:
    policy = RunPolicy(max_steps=2)

    assert policy.allows_step(0)
    assert policy.allows_step(1)
    assert not policy.allows_step(2)


