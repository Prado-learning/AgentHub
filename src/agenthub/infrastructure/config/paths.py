"""Application paths, independent of the process working directory."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def data_root() -> Path:
    return Path(
        os.environ.get("AGENTHUB_DATA_DIR") or str(PROJECT_ROOT / "agent-workspace")
    ).resolve()


def runtime_dir() -> Path:
    return data_root() / "runtime"


def conversation_workspace(conversation_id: str) -> Path:
    from agenthub.sandbox.path_policy import safe_identifier

    return data_root() / "projects" / safe_identifier(conversation_id)
