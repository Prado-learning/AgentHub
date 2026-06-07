from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.services.attachment_service import (
    get_attachment,
    get_attachment_record,
    list_attachments,
    save_attachment,
)
from app.api.services.conversation_service import get_conversation


router = APIRouter(tags=["attachments"])


class AttachmentCreate(BaseModel):
    filename: str
    content_base64: str
    mime_type: str | None = None


@router.post("/conversations/{conversation_id}/attachments")
def create_attachment(conversation_id: str, request: AttachmentCreate) -> dict:
    if get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        attachment = save_attachment(
            conversation_id=conversation_id,
            filename=request.filename,
            content_base64=request.content_base64,
            mime_type=request.mime_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"attachment": attachment}


@router.get("/conversations/{conversation_id}/attachments")
def read_conversation_attachments(conversation_id: str) -> dict[str, list[dict]]:
    return {"attachments": list_attachments(conversation_id)}


@router.get("/attachments/{attachment_id}")
def read_attachment(attachment_id: str) -> dict:
    attachment = get_attachment(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment


@router.get("/attachments/{attachment_id}/content")
def read_attachment_content(attachment_id: str) -> FileResponse:
    attachment = get_attachment_record(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return FileResponse(
        attachment["file_path"],
        media_type=attachment.get("mime_type") or "application/octet-stream",
        filename=attachment.get("filename") or attachment_id,
    )
