"""AgentHub public API, loaded lazily to keep infrastructure independent."""

__all__ = ["HarnessRunner", "RunResult"]


def __getattr__(name):
    if name == "HarnessRunner":
        from agenthub.harness.runner import HarnessRunner

        return HarnessRunner
    if name == "RunResult":
        from agenthub.domain.run import RunResult

        return RunResult
    raise AttributeError(name)
