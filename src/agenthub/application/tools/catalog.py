from __future__ import annotations

from agenthub.infrastructure.config.loader import load_yaml_config


class ToolCatalog:
    def list_tools(self) -> list[dict]:
        for path in ("app/configs/tools.yaml",):
            try:
                return load_yaml_config(path).get("tools", [])
            except FileNotFoundError:
                continue
        return []

