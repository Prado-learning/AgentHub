from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(config_path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return data or {}

