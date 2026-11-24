"""Per-stage execution traces.

``StageTrace`` is the immutable record of one stage's inputs, branch
decisions, raw API data, outputs, error, and timing. It travels back
with :class:`agenthub.domain.run.RunResult.debug_trace` so the UI can
replay every stage without re-running the model.

This is a pure domain type: recording and aggregation live in
``agenthub.harness.tracing``; the data shape lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class StageTrace:
    """Snapshot of one stage's execution.

    Mirrors the article's ``FlowTracer`` schema: stage identity, timing,
    inputs the stage saw, the raw API data it consumed, the branch it
    chose, what it produced, and any error. ``final=True`` marks the
    stage that satisfied the run's IsFinal short-circuit condition.
    """

    stage_id: str
    stage_name: str
    started_at: datetime
    cost_ms: int
    inputs: dict[str, Any] = field(default_factory=dict)
    raw_api_data: dict[str, Any] = field(default_factory=dict)
    branch_hit: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    final: bool = False
