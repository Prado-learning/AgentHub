"""Review-token-bound patch application in a conversation's isolated workspace."""

from __future__ import annotations
import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from uuid import uuid4
from agenthub.infrastructure.config.paths import runtime_dir, conversation_workspace
from agenthub.sandbox.path_policy import resolve_within
from agenthub.infrastructure.persistence.artifacts import get_artifact, update_artifact
from agenthub.infrastructure.persistence.json_store import JsonStore

APPLICATIONS = JsonStore(runtime_dir() / "patch_applications.json")
ROOT_DIR = (
    None  # Optional test override. Production always uses conversation_workspace.
)
BACKUP_DIR = runtime_dir() / "patch-backups"
_patch_lock = RLock()


@dataclass
class FilePatch:
    old_path: str
    new_path: str
    hunks: list[list[str]] = field(default_factory=list)


def _load(artifact_id):
    artifact = get_artifact(artifact_id)
    if not artifact or artifact.get("type") != "diff":
        raise ValueError("Diff artifact not found")
    patches = _parse_unified_diff(str(artifact.get("content") or ""))
    if not patches or any(not p.hunks for p in patches):
        raise ValueError("No valid file hunks found")
    root = (
        Path(ROOT_DIR)
        if ROOT_DIR is not None
        else conversation_workspace(artifact["conversation_id"])
    )
    return artifact, patches, root.resolve()


def _target(root, patch):
    if (
        patch.old_path != "/dev/null"
        and patch.new_path != "/dev/null"
        and patch.old_path != patch.new_path
    ):
        raise ValueError(
            "Renames must be represented as separate delete and create patches"
        )
    name = patch.old_path if patch.new_path == "/dev/null" else patch.new_path
    if any(
        part in {".git", ".env", ".codex", ".agents"} or part.startswith(".env.")
        for part in name.replace("\\", "/").split("/")
    ):
        raise ValueError("Protected file")
    return resolve_within(root, name)


def _bytes(path):
    return path.read_bytes() if path.is_file() else None


def _digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _review_token(artifact, patches, root):
    state = [
        (str(_target(root, p)), _digest(_bytes(_target(root, p)))) for p in patches
    ]
    return hashlib.sha256(
        json.dumps([artifact["content"], state], sort_keys=True).encode()
    ).hexdigest()


def get_structured_diff(artifact_id: str) -> dict:
    with _patch_lock:
        artifact, patches, root = _load(artifact_id)
        files = [_structured_patch(p) for p in patches]
        for i, file in enumerate(files):
            for j, hunk in enumerate(file["hunks"]):
                hunk["id"] = f"{i}:{j}"
        return {
            "artifact_id": artifact_id,
            "status": artifact.get("status"),
            "workspace_dir": str(root),
            "review_token": _review_token(artifact, patches, root),
            "files": files,
        }


def apply_diff_artifact(artifact_id: str, *, review_token=None, hunk_ids=None) -> dict:
    with _patch_lock:
        artifact, patches, root = _load(artifact_id)
        if artifact.get("status") == "applied":
            raise ValueError("Diff is already applied")
        if review_token is not None and review_token != _review_token(
            artifact, patches, root
        ):
            raise ValueError("Diff or workspace changed; review again")
        valid = {f"{i}:{j}" for i, p in enumerate(patches) for j in range(len(p.hunks))}
        selected = valid if hunk_ids is None else set(hunk_ids)
        if not selected or not selected <= valid:
            raise ValueError("Select valid hunks to apply")
        changes = []
        seen = set()
        for i, p in enumerate(patches):
            hunks = [h for j, h in enumerate(p.hunks) if f"{i}:{j}" in selected]
            if not hunks:
                continue
            path = _target(root, p)
            if path in seen:
                raise ValueError("Duplicate target in diff")
            seen.add(path)
            before = _bytes(path)
            if p.old_path == "/dev/null" and before is not None:
                raise ValueError("New file already exists")
            if p.old_path != "/dev/null" and before is None:
                raise ValueError("Original file does not exist")
            text = _apply_file_patch(
                (before or b"").decode("utf-8"),
                FilePatch(p.old_path, p.new_path, hunks),
            )
            if p.new_path == "/dev/null" and (len(hunks) != len(p.hunks) or text):
                raise ValueError("Deletion requires all hunks and an empty result")
            after = None if p.new_path == "/dev/null" else text.encode("utf-8")
            changes.append(
                {
                    "target": str(path.relative_to(root)),
                    "before": base64.b64encode(before).decode()
                    if before is not None
                    else None,
                    "after_hash": _digest(after),
                    "after": after,
                }
            )
        record = {
            "id": f"apply_{uuid4().hex[:12]}",
            "artifact_id": artifact_id,
            "workspace_dir": str(root),
            "changed_files": [c["target"] for c in changes],
            "backups": [{k: v for k, v in c.items() if k != "after"} for c in changes],
            "status": "applying",
        }
        APPLICATIONS.update(
            lambda records: [*records, record]
        )  # crash recovery journal before writes
        written = []
        try:
            for change in changes:
                path = resolve_within(root, change["target"])
                _write(path, change["after"])
                written.append(change)
        except Exception:
            for change in reversed(written):
                _write(resolve_within(root, change["target"]), _before(change))
            _status(record["id"], "failed")
            raise
        record = _status(record["id"], "applied")
        update_artifact(artifact_id, {"status": "applied", "apply_id": record["id"]})
        return record


def _before(change):
    return base64.b64decode(change["before"]) if change["before"] is not None else None


def _write(path, data):
    if data is None:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".agenthub-tmp-" + uuid4().hex)
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _status(apply_id, status):
    result = None

    def mutate(records):
        nonlocal result
        for record in records:
            if record["id"] == apply_id:
                record["status"] = status
                result = record
        return records

    APPLICATIONS.update(mutate)
    return result


def rollback_diff_application(apply_id: str) -> dict:
    with _patch_lock:
        record = next((r for r in APPLICATIONS.read() if r["id"] == apply_id), None)
        if not record:
            raise ValueError("Patch application not found")
        if record["status"] == "rolled_back":
            return record
        if record["status"] != "applied":
            raise ValueError("Patch requires manual recovery; inspect the journal")
        root = Path(record["workspace_dir"])
        for c in record["backups"]:
            if _digest(_bytes(resolve_within(root, c["target"]))) != c["after_hash"]:
                raise ValueError(
                    "Workspace changed since application; rollback would overwrite edits"
                )
        for c in reversed(record["backups"]):
            _write(resolve_within(root, c["target"]), _before(c))
        result = _status(apply_id, "rolled_back")
        update_artifact(record["artifact_id"], {"status": "rolled_back"})
        return result


def _parse_unified_diff(content: str) -> list[FilePatch]:
    patches = []
    current = None
    hunk = None
    old_remaining = new_remaining = 0
    for line in content.splitlines():
        if hunk is not None and line == r"\ No newline at end of file":
            hunk.append(line)
            continue
        if hunk is not None and (old_remaining or new_remaining):
            if line[:1] not in {" ", "+", "-"}:
                raise ValueError("Truncated diff hunk")
            hunk.append(line)
            old_remaining -= int(line[0] in {" ", "-"})
            new_remaining -= int(line[0] in {" ", "+"})
            if min(old_remaining, new_remaining) < 0:
                raise ValueError("Invalid hunk line counts")
            continue
        if line.startswith("--- "):
            current = FilePatch(_clean_diff_path(line[4:]), "")
            patches.append(current)
            hunk = None
        elif line.startswith("+++ ") and current:
            current.new_path = _clean_diff_path(line[4:])
        elif line.startswith("@@ ") and current:
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not match:
                raise ValueError("Invalid hunk header")
            old_remaining = int(match.group(2) or 1)
            new_remaining = int(match.group(4) or 1)
            hunk = [line]
            current.hunks.append(hunk)
    if old_remaining or new_remaining:
        raise ValueError("Truncated diff hunk")
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
                lines.append(
                    {
                        "type": "context",
                        "old_no": old_no,
                        "new_no": new_no,
                        "content": content,
                    }
                )
                old_no = old_no + 1 if old_no is not None else None
                new_no = new_no + 1 if new_no is not None else None
            elif marker == "-":
                lines.append(
                    {
                        "type": "remove",
                        "old_no": old_no,
                        "new_no": None,
                        "content": content,
                    }
                )
                old_no = old_no + 1 if old_no is not None else None
            elif marker == "+":
                lines.append(
                    {
                        "type": "add",
                        "old_no": None,
                        "new_no": new_no,
                        "content": content,
                    }
                )
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
        if old_start > len(original_lines):
            raise ValueError("Hunk starts beyond original file")
        if old_start < cursor:
            raise ValueError("Overlapping diff hunks are not supported")

        output.extend(original_lines[cursor:old_start])
        cursor = old_start

        previous_marker = None
        for raw_line in hunk[1:]:
            if raw_line == r"\ No newline at end of file":
                if previous_marker in {"+", " "} and output:
                    output[-1] = output[-1].rstrip("\r\n")
                continue
            previous_marker = raw_line[:1]
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


def _clean_diff_path(path: str) -> str:
    path = path.split("\t", 1)[0]
    return path[2:] if path.startswith(("a/", "b/")) else path
