from __future__ import annotations

import sys
from pathlib import Path

from agenthub.adapters import ClaudeCodeAdapter, build_agent_adapters
from agenthub.adapters.base import AgentTask
from agenthub.domain.run import RunContext


def _context() -> RunContext:
    return RunContext(
        conversation_id="conv_demo",
        message="Build a button",
        history=[],
        selected_agents=["claude_code"],
        mode="single",
    )


def _write_fake_cli(tmp_path: Path) -> Path:
    script = tmp_path / "fake_cli.py"
    script.write_text(
        "print('```tsx')\n"
        "print('export default function Demo() { return null; }')\n"
        "print('```')\n",
        encoding="utf-8",
    )
    return script


def test_claude_code_adapter_errors_when_command_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_COMMAND", raising=False)
    adapter = ClaudeCodeAdapter()

    result = adapter.run(AgentTask(agent_id="claude_code", instruction="Build"), _context())

    assert result.status == "error"
    assert "CLAUDE_CODE_COMMAND is not configured" in str(result.error)


def test_claude_code_adapter_errors_when_command_missing(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_COMMAND", "definitely-not-a-real-command-xyz")
    adapter = ClaudeCodeAdapter()

    result = adapter.run(AgentTask(agent_id="claude_code", instruction="Build"), _context())

    assert result.status == "error"
    assert "failed to start" in result.messages[0]["content"]


def test_claude_code_adapter_extracts_code_artifact_from_cli_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    script = _write_fake_cli(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_COMMAND", f"{sys.executable} {script}")
    adapter = ClaudeCodeAdapter()

    result = adapter.run(AgentTask(agent_id="claude_code", instruction="Build"), _context())

    assert result.status == "success"
    assert result.artifacts[0]["type"] == "code"
    assert result.artifacts[0]["language"] == "tsx"


def test_factory_builds_claude_code_adapter_from_config() -> None:
    adapters = build_agent_adapters(
        agent_configs=[
            {
                "id": "claude_code",
                "name": "Claude Code",
                "adapter": "claude_code",
                "capabilities": ["code"],
            }
        ]
    )

    assert isinstance(adapters["claude_code"], ClaudeCodeAdapter)
