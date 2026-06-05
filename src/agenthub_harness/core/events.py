from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RunEvent:
    type: str
    payload: dict[str, Any]
    created_at: datetime = datetime.now(timezone.utc)

