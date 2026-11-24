from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from uuid import uuid4

from agenthub.harness.control import RunCancelled, BudgetExceeded, check_cancelled
from agenthub.runtime.result_parser import upstream_context

from agenthub.adapters.base import AgentResult, AgentTask
from agenthub.domain.run import RunContext
from agenthub.runtime.prompt_builder import format_messages_for_prompt
from agenthub.sandbox import current_sandbox


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
        workspace = Path(context.workspace_dir) if context.workspace_dir else None
        if workspace is None:
            raise ValueError("CLI execution requires a conversation workspace")
        workspace.mkdir(parents=True, exist_ok=True)
        completed = _run_process(
            command,
            _prompt(name, task, context, skills or []),
            workspace,
            _timeout(timeout_env_key),
        )
    except (RunCancelled, BudgetExceeded):
        raise
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
    parts = shlex.split(command_text, posix=os.name != "nt")
    return [
        part[1:-1]
        if os.name == "nt"
        and len(part) > 1
        and part[0] == part[-1]
        and part[0] in {chr(34), chr(39)}
        else part
        for part in parts
    ]


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
        f"Upstream artifacts:\n{upstream_context(context)}\n"
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
        elif language.lower() in {
            "tsx",
            "jsx",
            "ts",
            "js",
            "html",
            "css",
            "python",
            "py",
        }:
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


def _sandbox_for(workspace: Path):
    """The sandbox this CLI call must run inside.

    A run-scoped sandbox is preferred so the process inherits the run's
    boundary, limits and audit trail. When an adapter is exercised
    outside a run, an ephemeral sandbox with the default spec keeps the
    same code path instead of forking back to raw ``subprocess``.
    """
    sandbox = current_sandbox()
    if sandbox is not None:
        return sandbox
    from agenthub.sandbox.backends.local import LocalSandbox
    from agenthub.sandbox.spec import SandboxSpec

    ephemeral = LocalSandbox(
        SandboxSpec(run_id=f"adhoc_{uuid4().hex[:8]}", workspace_root=workspace)
    )
    ephemeral.start()
    return ephemeral


def _run_process(command, prompt, workspace, timeout):
    check_cancelled()
    # Every process the harness starts goes through the sandbox: job
    # object or process group for containment, the spec's ceilings, the
    # credential allow-list, and an audit record.
    return _sandbox_for(workspace).exec(
        command, cwd=workspace, stdin=prompt, timeout=timeout
    )
