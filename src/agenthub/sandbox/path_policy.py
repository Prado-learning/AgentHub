from pathlib import Path
import re


def is_within_workspace(path: Path, workspace: Path) -> bool:
    return path.resolve().is_relative_to(workspace.resolve())


def safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Invalid identifier")
    return value


def resolve_within(root: Path, relative: str) -> Path:
    parts = relative.replace("\\", "/").split("/")
    if not relative or any(part in {"", ".", ".."} or ":" in part for part in parts):
        raise ValueError("Invalid workspace path")
    target = (root / relative).resolve()
    if not is_within_workspace(target, root):
        raise ValueError("Path escapes workspace")
    return target
