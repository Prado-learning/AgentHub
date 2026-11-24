"""Small deterministic source checks, explicitly scoped as static review."""

import ast
import re
from agenthub.tools.schemas import ToolResult


def code_review_tool(code: str) -> ToolResult:
    findings = []
    patterns = [
        (r"\beval\s*\(", "Dynamic eval executes untrusted input."),
        (
            r"dangerouslySetInnerHTML|\.innerHTML\s*=",
            "HTML injection sink: check sanitization.",
        ),
        (
            r"shell\s*=\s*True",
            "Shell execution: validate input and avoid concatenated commands.",
        ),
        (r"except\s*(?:Exception)?\s*:\s*pass", "Exception is silently discarded."),
    ]
    for number, line in enumerate(code.splitlines(), 1):
        for pattern, message in patterns:
            if re.search(pattern, line):
                findings.append(f"- Line {number}: {message}")
    if re.search(r"^(?:def |class |from \w+ import )", code, re.M):
        try:
            ast.parse(code)
        except SyntaxError as exc:
            findings.append(f"- Line {exc.lineno}: Python syntax error: {exc.msg}")
    summary = (
        "\n".join(findings)
        if findings
        else "- No matching issues in the checks performed."
        if code
        else "- No code provided."
    )
    return ToolResult(
        id="static_review",
        type="review",
        title="Static Code Review",
        content=(
            "Static pattern and Python syntax checks; no execution or correctness guarantee.\n"
            + summary
        ),
    )
