from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.domain.run import RunContext
from agenthub.runtime.prompt_builder import format_messages_for_prompt


def run_cli_agent(
    *,
    agent_id: str,
    name: str,
    task: AgentTask,
    context: RunContext,
    env_command_key: str,
    default_command: str = "",
    skills: list[str] | None = None,
    timeout_env_key: str = "AGENT_CLI_TIMEOUT_SECONDS",
) -> AgentResult:
    command_text = os.environ.get(env_command_key, default_command).strip()
    if not command_text:
        return AgentResult(
            agent_id=agent_id,
            status="error",
            error=f"{env_command_key} is not configured",
            messages=[_message(agent_id, f"{name} CLI command is not configured.")],
        )

    try:
        command = _split_command(command_text)
        completed = subprocess.run(
            command,
            input=_prompt(name, task, context, skills or []),
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
            timeout=_timeout(timeout_env_key),
            check=False,
        )
    except Exception as exc:
        return AgentResult(
            agent_id=agent_id,
            status="error",
            error=str(exc),
            messages=[_message(agent_id, f"{name} CLI failed to start: {exc}")],
        )

    output = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        detail = stderr or output or f"exit code {completed.returncode}"
        return AgentResult(
            agent_id=agent_id,
            status="error",
            error=detail,
            messages=[_message(agent_id, f"{name} CLI failed: {detail}")],
        )

    content = output or stderr or f"{name} CLI completed without output."
    artifacts = _artifacts_from_output(agent_id, content)
    return AgentResult(
        agent_id=agent_id,
        messages=[_message(agent_id, content)],
        artifacts=artifacts,
    )


def _split_command(command_text: str) -> list[str]:
    return shlex.split(command_text, posix=os.name != "nt")


def _timeout(env_key: str) -> int:
    try:
        return max(5, int(os.environ.get(env_key, "180")))
    except ValueError:
        return 180


def _prompt(name: str, task: AgentTask, context: RunContext, skills: list[str]) -> str:
    history = format_messages_for_prompt(context.history, limit=8, total_limit=4200)
    return (
        f"You are {name} running inside AgentHub.\n"
        f"Conversation: {context.conversation_id}\n"
        f"Mode: {context.mode}\n"
        f"Requested tools: {', '.join(task.tools) or 'none'}\n\n"
        f"Skills:\n{chr(10).join(skills) if skills else 'No extra skills.'}\n\n"
        f"Recent history:\n{history}\n\n"
        f"Task:\n{task.instruction}\n"
    )


def _message(agent_id: str, content: str) -> dict:
    return {
        "role": "agent",
        "sender": agent_id,
        "content": content,
        "format": "markdown",
    }


def _artifacts_from_output(agent_id: str, content: str) -> list[dict]:
    artifacts: list[dict] = []
    for index, match in enumerate(
        re.finditer(r"```([A-Za-z0-9_-]*)\n?([\s\S]*?)```", content),
        start=1,
    ):
        language = match.group(1) or "text"
        body = match.group(2).strip()
        if not body:
            continue
        if language.lower() in {"diff", "patch"} or body.startswith("--- "):
            artifacts.append(
                {
                    "id": f"{agent_id}_diff_{index}",
                    "type": "diff",
                    "title": f"{agent_id} patch {index}",
                    "content": body,
                    "producer_agent_id": agent_id,
                }
            )
        elif language.lower() in {"tsx", "jsx", "ts", "js", "html", "css", "python", "py"}:
            artifacts.append(
                {
                    "id": f"{agent_id}_code_{index}",
                    "type": "code",
                    "title": f"{agent_id} output {index}.{language}",
                    "language": language,
                    "content": body,
                    "producer_agent_id": agent_id,
                }
            )
    return artifacts
