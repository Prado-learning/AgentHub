"""The execution boundary every side effect must cross.

A :class:`Sandbox` is the only object a run is allowed to touch the
outside world through. It is deliberately a small Protocol: process
execution, path reads and path writes. A backend that implements those
three honestly is a sandbox, whatever mechanism it uses underneath —
process groups and rlimits today, containers or micro-VMs later.

The rule the rest of the codebase follows: **if it changes state outside
the current process, it goes through here.** Adapters spawn CLI agents
through :meth:`Sandbox.exec`; tools write files through
:meth:`Sandbox.write_path`; nothing reaches ``subprocess`` or
``open(..., "w")`` on a run-controlled path directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from agenthub.sandbox.audit import SandboxReport
from agenthub.sandbox.spec import SandboxSpec


@dataclass
class ExecResult:
    """Outcome of one process started inside a sandbox."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


class Sandbox(Protocol):
    """Controlled execution environment for exactly one run."""

    spec: SandboxSpec

    def start(self) -> None:
        """Bring the environment up. Idempotent."""

    def exec(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        """Start one process under the spec's limits and return its output.

        The command is always run inside the process tree the backend
        manages, so cancelling the run or closing the sandbox terminates
        it and its descendants.
        """

    def read_path(self, path: Path | str) -> bytes:
        """Read a file the spec allows this run to see."""

    def write_path(self, path: Path | str, data: bytes) -> Path:
        """Write a file inside the sandbox's writable root."""

    def stop(self) -> SandboxReport:
        """Tear the environment down and return its audit trail."""


class SandboxError(RuntimeError):
    """A side effect was refused by the sandbox boundary."""
