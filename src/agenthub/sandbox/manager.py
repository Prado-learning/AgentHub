"""One sandbox per run, bound to the current execution scope.

The manager is the factory and the registry. It creates a sandbox from
a :class:`~agenthub.sandbox.spec.SandboxSpec` using the configured
backend, and :func:`sandbox_scope` binds the live instance to a
``ContextVar`` so code deep inside a step — an adapter spawning a CLI, a
tool writing a file — can reach it with :func:`current_sandbox` without
threading it through every signature.

This mirrors how :mod:`agenthub.harness.control` already binds the
``RunControl`` and event sink: the sandbox is the third ambient object
of a run.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from agenthub.registry import SANDBOX_BACKENDS
from agenthub.sandbox.base import ExecResult, Sandbox, SandboxError
from agenthub.sandbox.spec import SandboxSpec

_current: ContextVar[Sandbox | None] = ContextVar("agenthub_sandbox", default=None)

DEFAULT_BACKEND = "local"


def sandbox_backends() -> dict[str, type]:
    """Named backends: the built-in local one plus anything registered."""
    from agenthub.sandbox.backends.local import LocalSandbox

    return {"local": LocalSandbox, **SANDBOX_BACKENDS}


def backend_name() -> str:
    """The backend ``AGENTHUB_SANDBOX_BACKEND`` selects; ``local`` by default."""
    return os.environ.get("AGENTHUB_SANDBOX_BACKEND", "").strip() or DEFAULT_BACKEND


def current_sandbox() -> Sandbox | None:
    """The sandbox bound to this execution scope, if any."""
    return _current.get()


def require_sandbox() -> Sandbox:
    """The bound sandbox, or an error explaining that there is none."""
    sandbox = _current.get()
    if sandbox is None:
        raise SandboxError(
            "No sandbox is bound to this execution scope; "
            "wrap the run in sandbox_scope() first"
        )
    return sandbox


@contextmanager
def sandbox_scope(sandbox: Sandbox | None) -> Iterator[Sandbox | None]:
    """Bind ``sandbox`` for the duration of the block."""
    if sandbox is None:
        yield None
        return
    token = _current.set(sandbox)
    try:
        yield sandbox
    finally:
        _current.reset(token)


class SandboxManager:
    """Creates sandbox instances for runs and remembers the live ones.

    ``backend_factory`` pins one implementation. When it is omitted the
    backend named by ``AGENTHUB_SANDBOX_BACKEND`` is used, so swapping in
    a stronger isolation mechanism is a configuration change rather than a
    code change — provided it implements the same
    :class:`~agenthub.sandbox.base.Sandbox` interface.
    """

    def __init__(self, backend_factory=None) -> None:
        self._backend_factory = backend_factory
        self._live: dict[str, Sandbox] = {}

    def _resolve_backend(self):
        if self._backend_factory is not None:
            return self._backend_factory
        backends = sandbox_backends()
        name = backend_name()
        if name not in backends:
            raise SandboxError(
                f"Unknown sandbox backend {name!r}; available: {sorted(backends)}"
            )
        return backends[name]

    def create(self, spec: SandboxSpec) -> Sandbox:
        # A resumed run re-enters create() with the same run_id. The
        # previous instance holds no live processes (the run was paused at
        # an approval), so releasing it keeps exactly one sandbox per run
        # instead of leaking the earlier one's handles.
        self.release(spec.run_id)
        sandbox = self._resolve_backend()(spec)
        sandbox.start()
        self._live[spec.run_id] = sandbox
        return sandbox

    def get(self, run_id: str) -> Sandbox | None:
        return self._live.get(run_id)

    def release(self, run_id: str) -> None:
        sandbox = self._live.pop(run_id, None)
        if sandbox is not None:
            sandbox.stop()


__all__ = [
    "DEFAULT_BACKEND",
    "ExecResult",
    "Sandbox",
    "SandboxError",
    "SandboxManager",
    "backend_name",
    "current_sandbox",
    "require_sandbox",
    "sandbox_backends",
    "sandbox_scope",
]
