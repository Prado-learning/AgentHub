from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


class JsonStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def read(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return []
            return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def write(self, records: list[dict[str, Any]]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

