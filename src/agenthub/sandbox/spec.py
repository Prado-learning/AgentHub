"""Declarative boundary for one run's execution environment.

A :class:`SandboxSpec` says what a run may touch before anything runs:
the single writable root, extra read-only mounts, whether it may reach
the network, how much CPU/memory/processes it may consume, and which
credentials it is handed. The spec is data — it can be built from
configuration, attached to a plan, or asserted on in tests — while
enforcement lives in the backend (see :mod:`agenthub.sandbox.backends`).

Nothing here reaches the operating system. A spec is a *promise*; only
:class:`agenthub.sandbox.base.Sandbox` keeps it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class NetworkPolicy(str, Enum):
    """Egress allowance for processes started inside the sandbox.

    ``INHERIT`` reproduces the historical local behaviour (the child sees
    whatever the AgentHub process sees). It is the default only so that
    existing CLI agents keep working until their policy is chosen
    explicitly; it is not a boundary.
    """

    NONE = "none"
    MODEL_ONLY = "model_only"
    ALLOWLIST = "allowlist"
    INHERIT = "inherit"


class SandboxLifetime(str, Enum):
    """How long one sandbox instance lives."""

    RUN = "run"
    STEP = "step"


@dataclass(frozen=True)
class ResourceLimits:
    """Hard ceilings applied to every process the sandbox starts.

    ``None`` means "no ceiling" and is the default so that a spec stays
    comparable to the pre-sandbox behaviour until limits are chosen.
    """

    cpu_seconds: int | None = None
    memory_mb: int | None = None
    max_processes: int | None = None
    max_open_files: int | None = None

    def any_set(self) -> bool:
        return any(
            value is not None
            for value in (
                self.cpu_seconds,
                self.memory_mb,
                self.max_processes,
                self.max_open_files,
            )
        )


@dataclass(frozen=True)
class CredentialScope:
    """Which secrets a sandboxed process may see.

    ``allowed_env`` names environment variables copied from the parent
    process; ``secrets`` are injected verbatim. Everything else in the
    parent environment is stripped, so a CLI agent no longer inherits
    the whole service process environment by default.
    """

    allowed_env: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxSpec:
    """The complete boundary description for one run."""

    run_id: str
    workspace_root: Path
    readable_roots: tuple[Path, ...] = ()
    network: NetworkPolicy = NetworkPolicy.INHERIT
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    credentials: CredentialScope = field(default_factory=CredentialScope)
    lifetime: SandboxLifetime = SandboxLifetime.RUN

    def readable_roots_with_workspace(self) -> tuple[Path, ...]:
        return (*self.readable_roots, self.workspace_root)
