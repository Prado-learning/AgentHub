"""Bounded model/tool loop context. Only explicitly planned proposal/read tools are exposed."""

from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass
from agenthub.harness.control import check_cancelled


@dataclass
class ToolSession:
    schemas: list[dict]
    invoke: object
    max_rounds: int = 8


_session = ContextVar("agenthub_tools", default=None)


def current_tools():
    return _session.get()


@contextmanager
def tool_session(schemas, invoke):
    token = _session.set(ToolSession(schemas, invoke) if schemas else None)
    try:
        yield
    finally:
        _session.reset(token)


def call_tool(session, name, arguments):
    check_cancelled()
    token = _session.set(
        None
    )  # A tool's own model call must not recursively call itself.
    try:
        return session.invoke(name, arguments)
    finally:
        _session.reset(token)


class AgentRuntime:
    def __init__(self, adapter):
        self.adapter = adapter

    def run(self, task, context):
        check_cancelled()
        return self.adapter.run(task, context)
