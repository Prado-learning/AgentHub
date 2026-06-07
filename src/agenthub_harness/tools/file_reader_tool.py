from __future__ import annotations

from agenthub_harness.tools.schemas import ToolResult


def file_reader_tool(attachments: list[dict] | None = None, **_: object) -> ToolResult:
    attachments = attachments or []
    if not attachments:
        return ToolResult(
            id="file_reader_result",
            type="file",
            title="No files attached",
            content="No readable files were attached to this message.",
        )

    sections: list[str] = []
    for attachment in attachments:
        filename = attachment.get("filename") or attachment.get("id") or "attachment"
        extracted_text = str(attachment.get("extracted_text") or "").strip()
        if extracted_text:
            sections.append(f"## {filename}\n\n{extracted_text}")
        else:
            sections.append(
                f"## {filename}\n\n"
                f"Type: {attachment.get('mime_type') or attachment.get('type')}\n"
                "This attachment has no extracted text."
            )

    return ToolResult(
        id="file_reader_result",
        type="file",
        title="Attachment Reading Result",
        content="\n\n---\n\n".join(sections),
    )
