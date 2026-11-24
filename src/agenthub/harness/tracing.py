"""Stage-level tracing with environment-controlled zero-overhead fallback.

Mirrors the article's ``FlowTracer`` design:

- A single :class:`FlowTracer` is created per run and threaded through
  the harness.
- :meth:`FlowTracer.record_lifecycle` and :meth:`FlowTracer.begin_stage`
  both no-op when the tracer is disabled so production code paths pay
  a single boolean check.
- All recordings funnel into ``FlowTracer.stages`` which the runner
  snapshots onto :attr:`agenthub.domain.run.RunResult.debug_trace`.

The tracer never raises. When disabled it is a sentinel that returns
empty data, lets every ``begin_stage`` block execute a no-op context,
and lets every ``record_lifecycle`` call return ``None``.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from agenthub.domain.trace import StageTrace


_TRUTHY = {"1", "true", "yes", "on"}


def _env_enabled(default: bool = False) -> bool:
    raw = os.environ.get("AGENT_DEBUG")
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUTHY


@dataclass
class StageRecorder:
    """Mutable per-stage handle that finalises into an immutable ``StageTrace``.

    All ``set_*`` methods are silent no-ops when the recorder is the
    :class:`_NullRecorder` sentinel returned by a disabled tracer.
    """

    stage_id: str = ""
    stage_name: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    raw_api_data: dict[str, Any] = field(default_factory=dict)
    branch_hit: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    final: bool = False

    def set_input(self, data: dict[str, Any] | None) -> None:
        if data:
            self.inputs.update(data)

    def set_raw_api(self, data: dict[str, Any] | None) -> None:
        if data:
            self.raw_api_data.update(data)

    def set_branch(self, branch: str) -> None:
        self.branch_hit = branch

    def set_output(self, data: dict[str, Any] | None) -> None:
        if data:
            self.outputs.update(data)

    def set_error(self, err: str) -> None:
        self.error = err

    def set_final(self, is_final: bool, reason: str = "") -> None:
        self.final = bool(is_final)
        if reason:
            self.outputs["final_reason"] = reason


class _NullRecorder(StageRecorder):
    """Sentinel returned by ``FlowTracer.begin_stage`` when tracing is off."""

    def set_input(self, data: dict[str, Any] | None) -> None:  # type: ignore[override]
        return None

    def set_raw_api(self, data: dict[str, Any] | None) -> None:  # type: ignore[override]
        return None

    def set_branch(self, branch: str) -> None:  # type: ignore[override]
        return None

    def set_output(self, data: dict[str, Any] | None) -> None:  # type: ignore[override]
        return None

    def set_error(self, err: str) -> None:  # type: ignore[override]
        return None

    def set_final(self, is_final: bool, reason: str = "") -> None:  # type: ignore[override]
        return None


class FlowTracer:
    """Per-run tracer; zero-overhead when disabled.

    ``enabled`` is resolved once at construction time from the explicit
    argument or the ``AGENT_DEBUG`` environment variable. Production
    callers should rely on the default (env-driven) so a config flip is
    the only change needed to start collecting traces.
    """

    def __init__(self, enabled: bool | None = None) -> None:
        self._enabled = enabled if enabled is not None else _env_enabled()
        self._stages: list[StageTrace] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def stages(self) -> list[StageTrace]:
        """Snapshot of recorded stages; empty list when disabled."""
        return list(self._stages) if self._enabled else []

    def record_lifecycle(
        self,
        stage_id: str,
        stage_name: str,
        payload: dict[str, Any] | None = None,
    ) -> StageTrace | None:
        """Append a one-shot lifecycle entry (e.g. ``run.started``).

        These are written without a context manager because they are
        not nested inside a longer-lived stage.
        """
        if not self._enabled:
            return None
        recorder = StageRecorder(stage_id=stage_id, stage_name=stage_name)
        recorder.set_input(payload)
        trace = self._finalize(recorder)
        self._stages.append(trace)
        return trace

    @contextmanager
    def begin_stage(
        self,
        stage_id: str,
        stage_name: str,
    ) -> Iterator[StageRecorder]:
        recorder: StageRecorder
        if not self._enabled:
            recorder = _NullRecorder()
            yield recorder
            return

        recorder = StageRecorder(stage_id=stage_id, stage_name=stage_name)
        started_at = datetime.now(timezone.utc)
        start_monotonic = time.monotonic()
        try:
            yield recorder
        finally:
            trace = StageTrace(
                stage_id=recorder.stage_id,
                stage_name=recorder.stage_name,
                started_at=started_at,
                cost_ms=int((time.monotonic() - start_monotonic) * 1000),
                inputs=dict(recorder.inputs),
                raw_api_data=dict(recorder.raw_api_data),
                branch_hit=recorder.branch_hit,
                outputs=dict(recorder.outputs),
                error=recorder.error,
                final=recorder.final,
            )
            self._stages.append(trace)

    @staticmethod
    def _finalize(recorder: StageRecorder) -> StageTrace:
        """Build a StageTrace with zero timing; used by ``record_lifecycle``."""
        return StageTrace(
            stage_id=recorder.stage_id,
            stage_name=recorder.stage_name,
            started_at=datetime.now(timezone.utc),
            cost_ms=0,
            inputs=dict(recorder.inputs),
            raw_api_data=dict(recorder.raw_api_data),
            branch_hit=recorder.branch_hit,
            outputs=dict(recorder.outputs),
            error=recorder.error,
            final=recorder.final,
        )
