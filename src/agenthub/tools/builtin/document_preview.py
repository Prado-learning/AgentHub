from __future__ import annotations

from agenthub.tools.schemas import ToolResult


def document_preview_tool(attachments: list[dict] | None = None, **_: object) -> ToolResult:
    candidates = [
        attachment
        for attachment in attachments or []
        if _is_document(str(attachment.get("mime_type") or ""), str(attachment.get("filename") or ""))
    ]
    if not candidates:
        return ToolResult(
            id="document_preview_result",
            type="document_preview",
            title="No document preview",
            content="No PDF, Word, or PowerPoint attachment was available for preview.",
        )

    first = candidates[0]
    mime_type = str(first.get("mime_type") or "")
    filename = str(first.get("filename") or "Document")
    artifact_type = "presentation_preview" if _is_presentation(mime_type, filename) else "document_preview"
    return ToolResult(
        id="document_preview_result",
        type=artifact_type,
        title=f"Preview: {filename}",
        content=(
            f"Document preview is available for {filename}.\n"
            "PDF files open inline when the browser supports it. Office files are exposed as preview/download cards."
        ),
        preview_url=str(first.get("url") or ""),
        metadata={
            "source_attachment_id": first.get("id"),
            "mime_type": mime_type,
            "filename": filename,
        },
    )


def _is_document(mime_type: str, filename: str) -> bool:
    lowered = filename.lower()
    return (
        mime_type in {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
        or lowered.endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx"))
    )


def _is_presentation(mime_type: str, filename: str) -> bool:
    lowered = filename.lower()
    return "presentation" in mime_type or "powerpoint" in mime_type or lowered.endswith((".ppt", ".pptx"))
