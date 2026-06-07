from __future__ import annotations

from typing import Protocol

from agenthub.domain.plan import Plan
from agenthub.domain.run import RunContext


class Planner(Protocol):
    def plan(self, context: RunContext) -> Plan:
        ...

