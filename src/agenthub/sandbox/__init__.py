"""Controlled execution environment for every run.

The sandbox owns the boundary a run's side effects cannot cross: the
filesystem view it may read and write, the processes it may spawn, the
credentials it is handed and the resources it may consume. Nothing in
this package reaches the HTTP application; callers receive a
:class:`~agenthub.sandbox.base.Sandbox` from
:class:`~agenthub.sandbox.manager.SandboxManager` and perform every
side effect through it.

    from agenthub.sandbox import current_sandbox

    sandbox = current_sandbox()          # None outside a run scope
    sandbox.exec(["codex", "--help"])    # every process goes through here
    sandbox.write_path("out.html", b"…") # so does every write
"""

from agenthub.sandbox.audit import ExecRecord, SandboxReport, WriteRecord
from agenthub.sandbox.base import ExecResult, Sandbox, SandboxError
from agenthub.sandbox.manager import (
    SandboxManager,
    current_sandbox,
    require_sandbox,
    sandbox_scope,
)
from agenthub.sandbox.path_policy import (
    is_within_workspace,
    resolve_within,
    safe_identifier,
)
from agenthub.sandbox.spec import (
    CredentialScope,
    NetworkPolicy,
    ResourceLimits,
    SandboxLifetime,
    SandboxSpec,
)
from agenthub.sandbox.workspace_manager import WorkspaceManager

__all__ = [
    "CredentialScope",
    "ExecRecord",
    "ExecResult",
    "LocalSandbox",
    "NetworkPolicy",
    "ResourceLimits",
    "Sandbox",
    "SandboxError",
    "SandboxLifetime",
    "SandboxManager",
    "SandboxReport",
    "SandboxSpec",
    "WorkspaceManager",
    "WriteRecord",
    "current_sandbox",
    "is_within_workspace",
    "require_sandbox",
    "resolve_within",
    "safe_identifier",
    "sandbox_scope",
]


def __getattr__(name: str):
    # Imported lazily so that importing the package never pulls in the
    # backend (and, on Windows, ctypes) unless a sandbox is built.
    if name == "LocalSandbox":
        from agenthub.sandbox.backends.local import LocalSandbox

        return LocalSandbox
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
