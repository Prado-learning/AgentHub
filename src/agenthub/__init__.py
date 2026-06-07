"""AgentHub application package.

The `agenthub` package is the canonical architecture for the product:
domain models, application use cases, orchestration, harness runtime,
adapters, tools, skills, artifacts, and infrastructure.
"""

from agenthub.orchestration.coordinator import HarnessRunner
from agenthub.domain.run import RunResult

__all__ = ["HarnessRunner", "RunResult"]

