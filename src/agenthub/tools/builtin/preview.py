from __future__ import annotations

import re
from html import escape

from agenthub.tools.schemas import ToolResult


def preview_tool(title: str = "Todo List Preview", code: str = "") -> ToolResult:
    preview_html, render_mode = build_preview_html_for_code(title, code)
    return ToolResult(
        id="art_003",
        type="preview",
        title=title,
        content=f"Preview generated in {render_mode} mode.",
        preview_url="/artifacts/art_003/preview",
        preview_html=preview_html,
        metadata={"render_mode": render_mode},
    )


def build_preview_html_for_code(title: str, code: str) -> tuple[str, str]:
    html = extract_previewable_html(code)
    if html:
        return _normalize_preview_html(title, html), "html"
    return _code_preview_html(title, code), "code"


def extract_previewable_html(code: str) -> str:
    content = str(code or "").strip()
    if not content:
        return ""

    fenced_html = _extract_html_fence(content)
    if fenced_html:
        return fenced_html

    if _looks_like_full_html(content):
        return content

    return ""


def _extract_html_fence(content: str) -> str:
    fence_pattern = re.compile(r"```(?:html|htm)?\s*([\s\S]*?)```", re.IGNORECASE)
    for match in fence_pattern.finditer(content):
        candidate = match.group(1).strip()
        if _looks_like_full_html(candidate) or _looks_like_html_fragment(candidate):
            return candidate
    return ""


def _looks_like_full_html(content: str) -> bool:
    return bool(
        re.search(r"<!doctype\s+html", content, re.IGNORECASE)
        or re.search(r"<html[\s>]", content, re.IGNORECASE)
        or re.search(r"<body[\s>]", content, re.IGNORECASE)
    )


_FRAGMENT_TAG_PATTERN = re.compile(
    r"<\s*(?:div|span|p|h[1-6]|section|article|main|nav|header|footer|"
    r"ul|ol|li|table|tr|td|th|form|input|button|img|a)\b",
    re.IGNORECASE,
)


def _looks_like_html_fragment(content: str) -> bool:
    """Detect HTML fragments like <div>...</div>, <span>...</span>, etc."""
    return bool(_FRAGMENT_TAG_PATTERN.search(content))


def _normalize_preview_html(title: str, html: str) -> str:
    if _looks_like_full_html(html):
        return html
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
    <style>
      body {{ margin: 0; font-family: Inter, system-ui, sans-serif; background: #ffffff; color: #172033; }}
    </style>
  </head>
  <body>
    {html}
  </body>
</html>"""


def _code_preview_html(title: str, code: str) -> str:
    escaped_code = escape(code or "No source artifact was available.")
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
    <style>
      :root {{ color-scheme: light; }}
      body {{ font-family: Inter, system-ui, sans-serif; margin: 0; padding: 24px; background: #f7fafc; color: #172033; }}
      main {{ max-width: 960px; margin: 0 auto; display: grid; gap: 14px; }}
      .notice {{ border: 1px solid #d7e1ee; border-radius: 8px; background: #ffffff; padding: 16px; box-shadow: 0 10px 30px rgba(20, 34, 60, 0.08); }}
      pre {{ white-space: pre-wrap; background: #182536; color: #d8ecff; padding: 16px; border-radius: 8px; overflow: auto; }}
    </style>
  </head>
  <body>
    <main>
      <section class="notice">
        <h1>{escape(title)}</h1>
        <p>This artifact is not complete HTML, so AgentHub is showing a source preview.</p>
      </section>
      <pre>{escaped_code}</pre>
    </main>
  </body>
</html>"""
