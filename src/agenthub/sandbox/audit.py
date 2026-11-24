"""What a sandboxed run actually did.

The report is the audit half of the sandbox: every process it started,
every file it wrote, and every request it refused. It is produced by
:meth:`agenthub.sandbox.base.Sandbox.stop` and travels with the run so
an approval can be shown what a step is about to do, and a completed run
can be reviewed after the fact without re-running anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ExecRecord:
    """One process started inside the sandbox."""

    command: tuple[str, ...]
    returncode: int
    duration_ms: int
    timed_out: bool = False
    denied_reason: str | None = None


@dataclass
class WriteRecord:
    """One file written through the sandbox."""

    path: str
    size: int


@dataclass
class SandboxReport:
    """Audit trail for one sandbox instance."""

    run_id: str
    backend: str
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    stopped_at: datetime | None = None
    execs: list[ExecRecord] = field(default_factory=list)
    writes: list[WriteRecord] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)

    def deny(self, reason: str) -> None:
        self.denied.append(reason)

    def stop(self) -> None:
        self.stopped_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "backend": self.backend,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "execs": [
                {
                    "command": list(record.command),
                    "returncode": record.returncode,
                    "duration_ms": record.duration_ms,
                    "timed_out": record.timed_out,
                    "denied_reason": record.denied_reason,
                }
                for record in self.execs
            ],
            "writes": [
                {"path": record.path, "size": record.size}
                for record in self.writes
            ],
            "denied": list(self.denied),
        }
