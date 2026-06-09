from __future__ import annotations

import base64
import binascii
import mimetypes
from pathlib import Path
from uuid import uuid4

from app.api.services.conversation_store import JsonStore


RUNTIME_DIR = Path("agent-workspace/runtime")
UPLOAD_DIR = Path("agent-workspace/uploads")
ATTACHMENTS = JsonStore(RUNTIME_DIR / "attachments.json")

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".html",
    ".css",
    ".yaml",
    ".yml",
}
MAX_EXTRACTED_CHARS = 12000


def save_attachment(
    conversation_id: str,
    filename: str,
    content_base64: str,
    mime_type: str | None = None,
) -> dict:
    safe_name = _safe_filename(filename)
    guessed_mime = mime_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    try:
        content = base64.b64decode(content_base64, validate=True)
    except binascii.Error as exc:
        raise ValueError("Invalid base64 attachment content") from exc

    attachment_id = f"att_{uuid4().hex[:12]}"
    extension = Path(safe_name).suffix.lower()
    target_dir = UPLOAD_DIR / conversation_id
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{attachment_id}{extension}"
    file_path.write_bytes(content)

    attachment_type = "image" if guessed_mime.startswith("image/") else "file"
    record = {
        "id": attachment_id,
        "conversation_id": conversation_id,
        "type": attachment_type,
        "filename": safe_name,
        "mime_type": guessed_mime,
        "size": len(content),
        "file_path": str(file_path),
        "url": f"/attachments/{attachment_id}/content",
        "extracted_text": _extract_text(file_path, guessed_mime),
    }
    records = ATTACHMENTS.read()
    records.append(record)
    ATTACHMENTS.write(records)
    return _public_attachment(record)


def list_attachments(conversation_id: str | None = None) -> list[dict]:
    records = ATTACHMENTS.read()
    if conversation_id:
        records = [
            attachment
            for attachment in records
            if attachment.get("conversation_id") == conversation_id
        ]
    return [_public_attachment(attachment) for attachment in records]


def list_attachment_records(conversation_id: str | None = None) -> list[dict]:
    records = ATTACHMENTS.read()
    if conversation_id:
        records = [
            attachment
            for attachment in records
            if attachment.get("conversation_id") == conversation_id
        ]
    return records


def get_attachment(attachment_id: str) -> dict | None:
    for attachment in ATTACHMENTS.read():
        if attachment.get("id") == attachment_id:
            return _public_attachment(attachment)
    return None


def get_attachment_record(attachment_id: str) -> dict | None:
    for attachment in ATTACHMENTS.read():
        if attachment.get("id") == attachment_id:
            return attachment
    return None


def get_attachments_by_ids(attachment_ids: list[str]) -> list[dict]:
    wanted = set(attachment_ids)
    return [
        _public_attachment(attachment)
        for attachment in ATTACHMENTS.read()
        if attachment.get("id") in wanted
    ]


def get_attachment_records_by_ids(attachment_ids: list[str]) -> list[dict]:
    wanted = set(attachment_ids)
    return [
        attachment
        for attachment in ATTACHMENTS.read()
        if attachment.get("id") in wanted
    ]


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        return "attachment"
    return "".join(char for char in name if char not in '<>:"/\\|?*') or "attachment"


def _extract_text(path: Path, mime_type: str) -> str:
    suffix = path.suffix.lower()
    if not (mime_type.startswith("text/") or suffix in TEXT_EXTENSIONS):
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    return text[:MAX_EXTRACTED_CHARS]


def _public_attachment(attachment: dict) -> dict:
    return {
        key: value
        for key, value in attachment.items()
        if key != "file_path"
    }
