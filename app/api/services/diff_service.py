from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from app.api.services.artifact_service import get_artifact, update_artifact
from app.api.services.conversation_store import JsonStore


ROOT_DIR = Path.cwd()
RUNTIME_DIR = Path("agent-workspace/runtime")
BACKUP_DIR = RUNTIME_DIR / "patch-backups"
APPLICATIONS = JsonStore(RUNTIME_DIR / "patch_applications.json")
ALLOWED_PREFIXES = ("app", "src", "tests", "skills")
BLOCKED_NAMES = {".env", ".git"}


@dataclass
class FilePatch:
    old_path: str
    new_path: str
    hunks: list[list[str]] = field(default_factory=list)


def apply_diff_artifact(artifact_id: str) -> dict:
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise ValueError("Artifact not found")
    if artifact.get("type") != "diff":
        raise ValueError("Artifact is not a diff")

    content = str(artifact.get("content") or "")
    patches = _parse_unified_diff(content)
    if not patches:
        raise ValueError("No file patches found in diff artifact")

    apply_id = f"apply_{uuid4().hex[:12]}"
    backup_root = BACKUP_DIR / apply_id
    changed_files: list[str] = []
    backups: list[dict] = []

    try:
        for patch in patches:
            target_path = _resolve_patch_target(patch)
            relative_target = target_path.relative_to(ROOT_DIR)
            original_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            next_text = _apply_file_patch(original_text, patch)

            if target_path.exists():
                backup_path = backup_root / relative_target
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path, backup_path)
                backups.append(
                    {
                        "target": str(relative_target),
                        "backup": str(backup_path),
                    }
                )

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(next_text, encoding="utf-8")
            changed_files.append(str(relative_target))
    except Exception:
        _restore_backups(backups)
        raise

    record = {
        "id": apply_id,
        "artifact_id": artifact_id,
        "changed_files": changed_files,
        "backups": backups,
        "status": "applied",
    }
    records = APPLICATIONS.read()
    records.append(record)
    APPLICATIONS.write(records)
    update_artifact(artifact_id, {"status": "applied", "apply_id": apply_id})
    return record


def get_structured_diff(artifact_id: str) -> dict:
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise ValueError("Artifact not found")
    if artifact.get("type") != "diff":
        raise ValueError("Artifact is not a diff")
    patches = _parse_unified_diff(str(artifact.get("content") or ""))
    return {
        "artifact_id": artifact_id,
        "files": [_structured_patch(patch) for patch in patches],
    }


def rollback_diff_application(apply_id: str) -> dict:
    records = APPLICATIONS.read()
    for record in records:
        if record.get("id") != apply_id:
            continue
        _restore_backups(record.get("backups", []))
        record["status"] = "rolled_back"
        APPLICATIONS.write(records)
        if record.get("artifact_id"):
            update_artifact(str(record["artifact_id"]), {"status": "rolled_back"})
        return record
    raise ValueError("Patch application not found")


def _parse_unified_diff(content: str) -> list[FilePatch]:
    patches: list[FilePatch] = []
    current: FilePatch | None = None
    current_hunk: list[str] | None = None

    for line in content.splitlines():
        if line.startswith("--- "):
            old_path = _clean_diff_path(line[4:].strip())
            current = FilePatch(old_path=old_path, new_path=old_path)
            patches.append(current)
            current_hunk = None
            continue
        if line.startswith("+++ ") and current is not None:
            current.new_path = _clean_diff_path(line[4:].strip())
            continue
        if line.startswith("@@ ") and current is not None:
            current_hunk = [line]
            current.hunks.append(current_hunk)
            continue
        if current_hunk is not None and (
            line.startswith(" ")
            or line.startswith("+")
            or line.startswith("-")
            or line == r"\ No newline at end of file"
        ):
            current_hunk.append(line)

    return patches


def _structured_patch(patch: FilePatch) -> dict:
    files = {
        "old_path": patch.old_path,
        "new_path": patch.new_path,
        "hunks": [],
    }
    for hunk in patch.hunks:
        header = hunk[0]
        match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", header)
        old_no = int(match.group(1)) if match else None
        new_no = int(match.group(2)) if match else None
        lines: list[dict] = []
        for raw_line in hunk[1:]:
            marker = raw_line[:1]
            content = raw_line[1:] if marker in {" ", "+", "-"} else raw_line
            if marker == " ":
                lines.append({"type": "context", "old_no": old_no, "new_no": new_no, "content": content})
                old_no = old_no + 1 if old_no is not None else None
                new_no = new_no + 1 if new_no is not None else None
            elif marker == "-":
                lines.append({"type": "remove", "old_no": old_no, "new_no": None, "content": content})
                old_no = old_no + 1 if old_no is not None else None
            elif marker == "+":
                lines.append({"type": "add", "old_no": None, "new_no": new_no, "content": content})
                new_no = new_no + 1 if new_no is not None else None
        files["hunks"].append({"header": header, "lines": lines})
    return files


def _apply_file_patch(original_text: str, patch: FilePatch) -> str:
    original_lines = original_text.splitlines(keepends=True)
    output: list[str] = []
    cursor = 0

    for hunk in patch.hunks:
        header = hunk[0]
        match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", header)
        if match is None:
            raise ValueError(f"Invalid hunk header: {header}")
        old_start = max(0, int(match.group(1)) - 1)
        if old_start < cursor:
            raise ValueError("Overlapping diff hunks are not supported")

        output.extend(original_lines[cursor:old_start])
        cursor = old_start

        for raw_line in hunk[1:]:
            if raw_line == r"\ No newline at end of file":
                continue
            marker = raw_line[:1]
            value = raw_line[1:] + "\n"
            if marker == " ":
                _assert_line_matches(original_lines, cursor, value)
                output.append(original_lines[cursor])
                cursor += 1
            elif marker == "-":
                _assert_line_matches(original_lines, cursor, value)
                cursor += 1
            elif marker == "+":
                output.append(value)
            else:
                raise ValueError(f"Unsupported diff line: {raw_line}")

    output.extend(original_lines[cursor:])
    return "".join(output)


def _assert_line_matches(lines: list[str], cursor: int, expected: str) -> None:
    if cursor >= len(lines) or lines[cursor].rstrip("\r\n") != expected.rstrip("\r\n"):
        raise ValueError("Diff does not apply cleanly")


def _resolve_patch_target(patch: FilePatch) -> Path:
    candidate = patch.new_path if patch.new_path != "/dev/null" else patch.old_path
    normalized = candidate.replace("\\", "/").lstrip("/")
    if normalized.startswith("a/") or normalized.startswith("b/"):
        normalized = normalized[2:]
    parts = Path(normalized).parts
    if not parts or parts[0] not in ALLOWED_PREFIXES:
        raise ValueError(f"Patch target is outside allowed folders: {candidate}")
    if any(part in BLOCKED_NAMES for part in parts):
        raise ValueError(f"Patch target is blocked: {candidate}")

    target = (ROOT_DIR / normalized).resolve()
    if not str(target).lower().startswith(str(ROOT_DIR.resolve()).lower()):
        raise ValueError(f"Patch target escapes workspace: {candidate}")
    return target


def _clean_diff_path(path: str) -> str:
    return path.split("\t", 1)[0].split(" ", 1)[0]


def _restore_backups(backups: list[dict]) -> None:
    for backup in backups:
        target = ROOT_DIR / str(backup.get("target", ""))
        backup_path = Path(str(backup.get("backup", "")))
        if backup_path.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, target)

