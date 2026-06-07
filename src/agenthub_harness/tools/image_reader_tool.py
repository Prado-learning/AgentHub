from __future__ import annotations

import struct
from pathlib import Path

from agenthub_harness.tools.schemas import ToolResult


def image_reader_tool(attachments: list[dict] | None = None, **_: object) -> ToolResult:
    images = [
        attachment
        for attachment in attachments or []
        if str(attachment.get("mime_type", "")).startswith("image/")
        or attachment.get("type") == "image"
    ]
    if not images:
        return ToolResult(
            id="image_reader_result",
            type="image",
            title="No images attached",
            content="No image attachments were provided.",
        )

    sections = []
    for image in images:
        path = Path(str(image.get("file_path", "")))
        width, height = _image_size(path)
        size_text = f"{width}x{height}" if width and height else "unknown dimensions"
        sections.append(
            "\n".join(
                [
                    f"## {image.get('filename') or image.get('id')}",
                    f"- MIME type: {image.get('mime_type') or 'unknown'}",
                    f"- File size: {image.get('size') or 0} bytes",
                    f"- Image size: {size_text}",
                    "- Visual note: this tool extracted image metadata. For semantic visual understanding, route the task to a vision-capable model or Vision Agent.",
                ]
            )
        )

    return ToolResult(
        id="image_reader_result",
        type="image",
        title="Image Reading Result",
        content="\n\n".join(sections),
    )


def _image_size(path: Path) -> tuple[int | None, int | None]:
    if not path.exists():
        return None, None
    data = path.read_bytes()[:4096]
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        if len(data) >= 10:
            return struct.unpack("<HH", data[6:10])
    if data.startswith(b"\xff\xd8"):
        return _jpeg_size(data)
    return None, None


def _jpeg_size(data: bytes) -> tuple[int | None, int | None]:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        length = int.from_bytes(data[index : index + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 <= len(data):
                height = int.from_bytes(data[index + 3 : index + 5], "big")
                width = int.from_bytes(data[index + 5 : index + 7], "big")
                return width, height
        index += length
    return None, None
