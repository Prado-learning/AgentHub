"""The four seams AgentHub expects to be extended through.

A framework is a core that names its extension points and gets out of the
way. This module holds those points — adapters, tools, planners and
sandbox backends — as plain registries, so an extension is one
``register_*`` call in the extension's own module rather than an edit to
core code.

Each subsystem keeps its built-ins in its own module and merges this
registry on top, which means importing :mod:`agenthub.registry` alone
yields empty registries: the built-ins arrive when the subsystem that
owns them is imported. That is deliberate — it keeps this module free of
imports and free of cycles.

    from agenthub.registry import register_adapter, register_tool

    register_tool("my_tool", my_tool_function)
    register_adapter("my_cli", lambda **kw: MyCliAdapter(**kw))

A registered name that collides with a built-in overrides it, which is
how a deployment swaps a default implementation without forking.
"""

from __future__ import annotations

from typing import Any, Callable

ADAPTER_BUILDERS: dict[str, Callable[..., Any]] = {}
TOOL_FACTORIES: dict[str, Callable[..., Any]] = {}
PLANNER_FACTORIES: dict[str, Callable[..., Any]] = {}
SANDBOX_BACKENDS: dict[str, Callable[..., Any]] = {}


def register_adapter(name: str, builder: Callable[..., Any]) -> None:
    """Register an adapter builder under ``name``.

    The builder receives the resolved adapter arguments as keyword
    arguments — ``agent_id``, ``name``, ``model``, ``api_key``,
    ``base_url``, ``capabilities``, ``skills`` — and returns an
    :class:`~agenthub.adapters.base.AgentAdapter`.
    """
    ADAPTER_BUILDERS[name] = builder


def register_tool(name: str, factory: Callable[..., Any]) -> None:
    """Register a tool callable under ``name``.

    The callable takes the arguments the harness derives for the step and
    returns a :class:`~agenthub.tools.schemas.ToolResult`.
    """
    TOOL_FACTORIES[name] = factory


def register_planner(name: str, factory: Callable[..., Any]) -> None:
    """Register a planner factory under ``name``.

    The factory returns an object satisfying
    :class:`~agenthub.orchestration.planner.Planner`.
    """
    PLANNER_FACTORIES[name] = factory


def register_sandbox_backend(name: str, factory: Callable[..., Any]) -> None:
    """Register a sandbox backend under ``name``.

    The factory takes a :class:`~agenthub.sandbox.spec.SandboxSpec` and
    returns a :class:`~agenthub.sandbox.base.Sandbox`.
    """
    SANDBOX_BACKENDS[name] = factory


def extension_points() -> dict[str, list[str]]:
    """Names currently registered at each seam, for docs and introspection."""
    return {
        "adapters": sorted(ADAPTER_BUILDERS),
        "tools": sorted(TOOL_FACTORIES),
        "planners": sorted(PLANNER_FACTORIES),
        "sandbox_backends": sorted(SANDBOX_BACKENDS),
    }


def clear_registrations() -> None:
    """Drop every registration. Intended for tests."""
    ADAPTER_BUILDERS.clear()
    TOOL_FACTORIES.clear()
    PLANNER_FACTORIES.clear()
    SANDBOX_BACKENDS.clear()
