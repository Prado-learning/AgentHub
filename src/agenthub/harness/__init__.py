"""Execution primitives with lazy public exports."""

from importlib import import_module

_EXPORTS = {
    "FallbackChain": "fallback",
    "HarnessRunner": "runner",
    "StepExecutionResult": "runner",
    "RunLimits": "limits",
}


def __getattr__(name):
    if name in _EXPORTS:
        return getattr(import_module(f"agenthub.harness.{_EXPORTS[name]}"), name)
    raise AttributeError(name)
