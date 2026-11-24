"""Cooperative cancellation and budgets shared by all steps in one run."""

from __future__ import annotations
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Callable


class RunCancelled(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class RunControl:
    timeout_seconds: float = 300
    max_llm_calls: int = 24
    cancelled: Event = field(default_factory=Event)
    started: float = field(default_factory=time.monotonic)
    llm_calls: int = 0
    _lock: Lock = field(default_factory=Lock)

    def check(self) -> None:
        if self.cancelled.is_set():
            raise RunCancelled("Run cancelled by user")
        if time.monotonic() - self.started >= self.timeout_seconds:
            raise BudgetExceeded("Run deadline exceeded")

    def model_call(self) -> None:
        with self._lock:
            self.check()
            if self.llm_calls >= self.max_llm_calls:
                raise BudgetExceeded("Run model-call budget exceeded")
            self.llm_calls += 1


_scope: ContextVar[tuple[RunControl | None, Callable | None]] = ContextVar(
    "agenthub_run_scope", default=(None, None)
)


@contextmanager
def execution_scope(control: RunControl, emit=None):
    token = _scope.set((control, emit))
    try:
        control.check()
        yield
    finally:
        _scope.reset(token)


def check_cancelled() -> None:
    control, _ = _scope.get()
    if control:
        control.check()


def record_model_call() -> None:
    control, emit = _scope.get()
    if control:
        control.model_call()
    if emit:
        emit("llm.started", {})


def record_usage(usage: dict) -> None:
    _, emit = _scope.get()
    if emit:
        emit("llm.completed", {"usage": usage})


def interruptible_wait(seconds: float) -> None:
    control, _ = _scope.get()
    if control:
        control.cancelled.wait(seconds)
        control.check()
    else:
        time.sleep(seconds)
