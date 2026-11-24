"""SQLite-backed compatibility API; legacy JSON is imported once, never overwritten.

Each legacy filename is a namespace. BEGIN IMMEDIATE serializes read/modify/write
across threads and processes, including transactions spanning multiple stores.
"""

from __future__ import annotations
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock, local
from typing import Any

_state = local()
_locks: dict[str, RLock] = {}
_registry_lock = RLock()


class JsonStore:
    def __init__(
        self,
        path: Path,
        lock: RLock | None = None,
        *,
        database_path: Path | None = None,
        namespace: str | None = None,
    ) -> None:
        self.path = Path(path).resolve()
        self.db_path = (
            Path(database_path).resolve()
            if database_path
            else self.path.parent / "agenthub.sqlite3"
        )
        self.key = namespace or self.path.name
        with _registry_lock:
            self._lock = _locks.setdefault(str(self.db_path), RLock())

    @contextmanager
    def locked(self) -> Iterator[JsonStore]:
        active = getattr(_state, "connections", None)
        if active is None:
            active = _state.connections = {}
        db_key = str(self.db_path)
        with self._lock:
            if db_key in active:
                yield self
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS stores (name TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                )
                connection.execute("BEGIN IMMEDIATE")
                active[db_key] = connection
                try:
                    yield self
                except BaseException:
                    connection.rollback()
                    raise
                else:
                    connection.commit()
            finally:
                active.pop(db_key, None)
                connection.close()

    def _connection(self) -> sqlite3.Connection:
        return _state.connections[str(self.db_path)]

    def read(self) -> Any:
        with self.locked():
            return self._read_unlocked()

    def write(self, records: Any) -> None:
        with self.locked():
            self._write_unlocked(records)

    def update(self, mutator: Callable[[Any], Any | None]) -> Any:
        with self.locked():
            records = self._read_unlocked()
            mutated = mutator(records)
            if mutated is not None:
                self._write_unlocked(mutated)
                return mutated
            return records

    def _read_unlocked(self) -> Any:
        row = (
            self._connection()
            .execute("SELECT payload FROM stores WHERE name=?", (self.key,))
            .fetchone()
        )
        if row is not None:
            return json.loads(row[0])
        records = (
            json.loads(self.path.read_text(encoding="utf-8") or "[]")
            if self.path.exists()
            else []
        )
        self._write_unlocked(records)
        return records

    def _write_unlocked(self, records: Any) -> None:
        self._connection().execute(
            "INSERT INTO stores(name,payload) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
            (self.key, json.dumps(records, ensure_ascii=False)),
        )


@contextmanager
def transaction(*stores: JsonStore) -> Iterator[None]:
    if not stores:
        yield
        return
    if len({store.db_path for store in stores}) != 1:
        raise ValueError("A transaction must use stores in the same database directory")
    with stores[0].locked():
        yield
