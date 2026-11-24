"""Every test gets disposable persistence; never use the developer's .env or data."""

import os
import sys
import tempfile
from pathlib import Path
import pytest

_session_data = tempfile.TemporaryDirectory(prefix="agenthub-tests-")
os.environ["AGENTHUB_DATA_DIR"] = _session_data.name
os.environ["AGENTHUB_SKIP_ENV_FILE"] = "1"
os.environ["ENABLE_REAL_LLM"] = "false"
os.environ["ENABLE_LLM_PLANNER"] = "false"


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    from agenthub.infrastructure.persistence.json_store import JsonStore
    from app.api.services import execution_service

    monkeypatch.setenv("AGENTHUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_REAL_LLM", "false")
    monkeypatch.setenv("ENABLE_LLM_PLANNER", "false")
    monkeypatch.delenv("GATEWAY_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    execution_service._controls.clear()
    for name, module in list(sys.modules.items()):
        if not name.startswith(("app.api.", "agenthub.")) or module is None:
            continue
        for attr, value in list(vars(module).items()):
            if isinstance(value, JsonStore):
                monkeypatch.setattr(module, attr, JsonStore(tmp_path / value.key))
            elif attr in {
                "RUNTIME_DIR",
                "RUNS_DIR",
                "BACKUP_DIR",
                "UPLOAD_DIR",
                "PREVIEW_DIR",
                "DEPLOYMENT_DIR",
            } and isinstance(value, Path):
                monkeypatch.setattr(
                    module,
                    attr,
                    tmp_path if attr == "RUNTIME_DIR" else tmp_path / attr.lower(),
                )
