from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import RLock
from typing import Any


class JsonStore:
    """JSON-file backed record list.

    ``update`` holds the store lock across the whole read-modify-write cycle,
    so concurrent updates cannot lose each other's changes. ``read`` and
    ``write`` only protect a single call: use them for read-only access or
    full replacement, never for read-then-modify-then-write.
    """

    def __init__(self, path: Path, lock: RLock | None = None) -> None:
        self.path = path
        self._lock = lock or RLock()

    def read(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_unlocked()

    def write(self, records: list[dict[str, Any]]) -> None:
        with self._lock:
            self._write_unlocked(records)

    def update(
        self,
        mutator: Callable[[list[dict[str, Any]]], list[dict[str, Any]] | None],
    ) -> list[dict[str, Any]]:
        """Atomically apply ``mutator`` to the record list.

        The mutator receives the current records and returns the new records,
        or ``None`` to leave the store unchanged. Returning ``None`` skips the
        write entirely, so mutations that find nothing to change stay cheap.
        """
        with self._lock:
            records = self._read_unlocked()
            mutated = mutator(records)
            if mutated is None:
                return records
            self._write_unlocked(mutated)
            return mutated

    @contextmanager
    def locked(self) -> Iterator[JsonStore]:
        """Hold the store lock across several calls (compound transactions)."""
        with self._lock:
            yield self

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def _write_unlocked(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@contextmanager
def transaction(*stores: JsonStore) -> Iterator[None]:
    """Lock several stores at once for a compound read-modify-write.

    Always pass the stores in the same order at every call site to avoid
    deadlocks when the stores do not share a lock.
    """
    with ExitStack() as stack:
        for store in stores:
            stack.enter_context(store.locked())
        yield
