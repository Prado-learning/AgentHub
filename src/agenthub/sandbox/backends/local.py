"""Local-process sandbox backend.

This is the default backend and the one that runs today's agents. It
enforces what can be enforced without an operating-system sandbox:

* **Process containment** — every child is placed in a Windows job
  object (``KILL_ON_JOB_CLOSE``) or a POSIX process group, so closing
  the sandbox or cancelling the run terminates the whole tree instead of
  leaving orphans.
* **Resource ceilings** — CPU time, memory and process count are
  applied by the kernel on Windows, and via ``setrlimit`` on POSIX when
  limits are configured.
* **Credential scoping** — the child environment is built from an
  allow-list plus the run's declared secrets, rather than inheriting the
  entire AgentHub process environment.
* **Filesystem boundary** — reads and writes are resolved against the
  spec's roots and refused when they escape.
* **Audit** — every exec and write is recorded for the
  :class:`~agenthub.sandbox.audit.SandboxReport`.

What it deliberately does **not** claim: there is no namespace, no
seccomp filter, no network firewall. A sandboxed CLI still runs as the
AgentHub user and can reach the network unless the process itself is
configured not to. Stronger isolation is a different backend behind the
same :class:`~agenthub.sandbox.base.Sandbox` interface — this module is
the seam, not the ceiling.

``RLIMIT_NPROC`` is intentionally not applied on POSIX: it is accounted
per user ID, so lowering it in one child would also throttle the
AgentHub service itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from agenthub.harness.control import RunCancelled, check_cancelled
from agenthub.sandbox.audit import ExecRecord, SandboxReport, WriteRecord
from agenthub.sandbox.base import ExecResult, SandboxError
from agenthub.sandbox.path_policy import resolve_within
from agenthub.sandbox.spec import ResourceLimits, SandboxSpec

# Variables a sandboxed process may inherit from the AgentHub process.
# Anything not listed here is stripped, so a CLI agent no longer sees the
# whole service environment by default. Extend per run through
# SandboxSpec.credentials.allowed_env.
_DEFAULT_ENV_ALLOW = (
    # POSIX
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TZ",
    "USER",
    "LOGNAME",
    "SHELL",
    # Windows
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "TEMP",
    "TMP",
    "PROGRAMDATA",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)

# Provider credentials an external CLI agent legitimately needs. Only the
# ones actually present in the environment are copied across.
_PROVIDER_ENV_ALLOW = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "STEPFUN_API_KEY",
    "STEPFUN_BASE_URL",
    "STEPFUN_MODEL_NAME",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL_NAME",
    "DOUBAO_API_KEY",
    "DOUBAO_BASE_URL",
    "DOUBAO_MODEL_NAME",
)

_POLL_SECONDS = 0.2


def _extra_env_allow() -> tuple[str, ...]:
    """Operator-supplied additions to the environment allow-list.

    ``AGENTHUB_SANDBOX_EXTRA_ENV`` takes a comma-separated list, so a CLI
    agent that needs an exotic variable can be unblocked without a code
    change — at the cost of explicitly widening the boundary.
    """
    raw = os.environ.get("AGENTHUB_SANDBOX_EXTRA_ENV", "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


class LocalSandbox:
    """Runs one run's side effects in managed child processes."""

    def __init__(self, spec: SandboxSpec) -> None:
        self.spec = spec
        self.report = SandboxReport(run_id=spec.run_id, backend="local")
        self._active: list[tuple[subprocess.Popen, object | None]] = []
        self._stopped = False

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.spec.workspace_root.mkdir(parents=True, exist_ok=True)

    def stop(self) -> SandboxReport:
        if not self._stopped:
            self._stopped = True
            for process, job in self._active:
                self._release(process, job)
            self._active.clear()
            self.report.stop()
        return self.report

    # -- process execution -------------------------------------------------

    def exec(
        self,
        command,
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        check_cancelled()
        parts = tuple(str(part) for part in command)
        if not parts:
            raise SandboxError("Sandbox exec requires a non-empty command")
        working_dir = self._resolve_cwd(cwd)
        child_env = self._child_env(env)
        payload = stdin or ""
        launch_command: tuple[str, ...] = parts
        job = None
        process: subprocess.Popen | None = None
        started = time.monotonic()

        def record(returncode: int, timed_out: bool) -> None:
            self.report.execs.append(
                ExecRecord(
                    command=parts,
                    returncode=returncode,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    timed_out=timed_out,
                )
            )

        if os.name == "nt":
            from agenthub.sandbox.backends.windows_job import BOOTSTRAP, WindowsJob

            job = WindowsJob(self.spec.resources)
            # The bootstrap cannot start the requested CLI until the parent
            # has assigned it to the job and sent the envelope over stdin,
            # which closes the "spawned before it was managed" race.
            launch_command = (sys._base_executable, "-I", "-S", "-c", BOOTSTRAP)
            payload = json.dumps(
                {"command": list(parts), "prompt": payload}, ensure_ascii=False
            )
        try:
            process = subprocess.Popen(
                launch_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=working_dir,
                env=child_env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
                preexec_fn=None if os.name == "nt" else self._apply_posix_limits,
            )
            self._active.append((process, job))
            if job is not None:
                job.assign(process)
            first = True
            while True:
                check_cancelled()
                if timeout is not None and time.monotonic() - started >= timeout:
                    record(-1, True)
                    raise TimeoutError("Sandboxed process exceeded its timeout")
                try:
                    stdout, stderr = process.communicate(
                        input=payload if first else None, timeout=_POLL_SECONDS
                    )
                except subprocess.TimeoutExpired:
                    first = False
                    continue
                record(process.returncode, False)
                return ExecResult(
                    command=parts,
                    returncode=process.returncode,
                    stdout=stdout or "",
                    stderr=stderr or "",
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
        except TimeoutError:
            raise
        except BaseException:
            record(-1, False)
            raise
        finally:
            # The job handle is closed first: KILL_ON_JOB_CLOSE terminates
            # the whole tree, which is what lets the pipes close and the
            # reap below return immediately. Killing only the direct child
            # would leave grandchildren holding the pipes open.
            self._release(process, job)

    # -- filesystem --------------------------------------------------------

    def read_path(self, path: Path | str) -> bytes:
        check_cancelled()
        target = self._resolve_readable(path)
        if not target.is_file():
            raise SandboxError(f"Sandbox read target is not a file: {target}")
        return target.read_bytes()

    def write_path(self, path: Path | str, data: bytes | str) -> Path:
        check_cancelled()
        target = self._resolve_writable(path)
        payload = data.encode("utf-8") if isinstance(data, str) else data
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(f"{target.name}.sandbox-partial")
        staging.write_bytes(payload)
        os.replace(staging, target)
        self.report.writes.append(WriteRecord(path=str(target), size=len(payload)))
        return target

    # -- internals ---------------------------------------------------------

    def _child_env(self, extra: dict[str, str] | None) -> dict[str, str]:
        allowed = {*_DEFAULT_ENV_ALLOW, *_PROVIDER_ENV_ALLOW}
        allowed.update(self.spec.credentials.allowed_env)
        allowed.update(_extra_env_allow())
        child = {key: value for key, value in os.environ.items() if key in allowed}
        for key in self.spec.credentials.secrets:
            value = os.environ.get(key)
            if value is not None:
                child[key] = value
        if extra:
            child.update({str(k): str(v) for k, v in extra.items()})
        return child

    def _resolve_cwd(self, cwd: Path | None) -> Path:
        target = Path(cwd) if cwd else self.spec.workspace_root
        for root in self.spec.readable_roots_with_workspace():
            base = root.resolve()
            resolved = target.resolve()
            if resolved == base or resolved.is_relative_to(base):
                return resolved
        raise SandboxError(f"Sandbox denies working directory: {target}")

    def _resolve_readable(self, path: Path | str) -> Path:
        candidate = Path(path)
        roots = [root.resolve() for root in self.spec.readable_roots_with_workspace()]
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if any(
                resolved == root or resolved.is_relative_to(root) for root in roots
            ):
                return resolved
            raise SandboxError(f"Sandbox denies read outside its roots: {path}")
        try:
            return resolve_within(self.spec.workspace_root, str(candidate))
        except ValueError as exc:
            raise SandboxError(f"Sandbox denies read of {path}: {exc}") from exc

    def _resolve_writable(self, path: Path | str) -> Path:
        candidate = Path(path)
        root = self.spec.workspace_root.resolve()
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if resolved == root or resolved.is_relative_to(root):
                return resolved
            raise SandboxError(f"Sandbox denies write outside its workspace: {path}")
        try:
            return resolve_within(self.spec.workspace_root, str(candidate))
        except ValueError as exc:
            raise SandboxError(f"Sandbox denies write of {path}: {exc}") from exc

    def _apply_posix_limits(self) -> None:
        """``preexec_fn`` hook applying the spec's resource ceilings.

        Only installed when limits are configured. Python documents
        ``preexec_fn`` as unsafe in multi-threaded processes; the harness
        runs steps on a thread pool, so callers who need POSIX ceilings
        should prefer a backend that applies them outside this process.
        """
        limits: ResourceLimits = self.spec.resources
        import resource

        if limits.cpu_seconds is not None:
            resource.setrlimit(
                resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds)
            )
        if limits.memory_mb is not None:
            ceiling = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        if limits.max_open_files is not None:
            resource.setrlimit(
                resource.RLIMIT_NOFILE,
                (limits.max_open_files, limits.max_open_files),
            )

    def _release(self, process: subprocess.Popen | None, job) -> None:
        """Close the job handle, then reap the direct child."""
        if job is not None:
            try:
                job.close()
            except Exception:
                pass
        if process is not None:
            self._forget(process)
            self._terminate(process)

    def _forget(self, process: subprocess.Popen) -> None:
        self._active = [
            entry for entry in self._active if entry[0] is not process
        ]

    def _terminate(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                # The bootstrap has received no input yet at this point, so
                # no user command could have started.
                process.kill()
            else:
                import signal

                os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.communicate(timeout=5)
        except Exception:
            pass


__all__ = ["LocalSandbox"]
