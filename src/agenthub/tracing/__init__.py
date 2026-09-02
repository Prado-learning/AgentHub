"""Per-stage tracing for deterministic Harness runs.

When ``AGENT_DEBUG`` is unset or falsy, the tracer becomes a
near-zero-overhead no-op so production runs pay nothing for
observability. When ``AGENT_DEBUG`` is truthy, every recorded event and
stage produces a :class:`agenthub.domain.trace.StageTrace` entry that
travels back with ``RunResult.debug_trace`` for replay and audit.
"""

from agenthub.tracing.tracer import FlowTracer, StageRecorder

__all__ = ["FlowTracer", "StageRecorder"]
