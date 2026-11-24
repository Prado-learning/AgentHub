"""Ready-made sandbox specifications for the shapes AgentHub runs in.

A spec is data, so the interesting question is what the *default* run
looks like. Today that is deliberately close to the pre-sandbox
behaviour — the writable root is the AgentHub data directory, network is
inherited, and no resource ceilings are applied — so that introducing the
boundary changes no existing outcome. Operators opt into a tighter
boundary through environment variables rather than through code:

``AGENTHUB_SANDBOX_NETWORK``       none | model_only | allowlist | inherit
``AGENTHUB_SANDBOX_CPU_SECONDS``   total CPU seconds for the process tree
``AGENTHUB_SANDBOX_MEMORY_MB``     per-process memory ceiling
``AGENTHUB_SANDBOX_MAX_PROCESSES`` maximum concurrent processes
"""

from __future__ import annotations

import os
from pathlib import Path

from agenthub.infrastructure.config.paths import data_root
from agenthub.sandbox.spec import (
    CredentialScope,
    NetworkPolicy,
    ResourceLimits,
    SandboxLifetime,
    SandboxSpec,
)


def _int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def network_policy() -> NetworkPolicy:
    raw = os.environ.get("AGENTHUB_SANDBOX_NETWORK", "").strip().lower()
    try:
        return NetworkPolicy(raw)
    except ValueError:
        return NetworkPolicy.INHERIT


def resource_limits() -> ResourceLimits:
    return ResourceLimits(
        cpu_seconds=_int_env("AGENTHUB_SANDBOX_CPU_SECONDS"),
        memory_mb=_int_env("AGENTHUB_SANDBOX_MEMORY_MB"),
        max_processes=_int_env("AGENTHUB_SANDBOX_MAX_PROCESSES"),
    )


def run_spec(
    run_id: str,
    *,
    conversation_id: str | None = None,
    workspace_root: Path | None = None,
    network: NetworkPolicy | None = None,
) -> SandboxSpec:
    """Build the default boundary for one run.

    The writable root is the AgentHub data directory: every artefact a
    run legitimately produces — the conversation workspace, previews,
    deployments, uploads — already lives under it, and nothing outside it
    is reachable through the sandbox. The conversation's own workspace is
    additionally named as a readable root so a CLI agent's working
    directory is explicit rather than incidental.

    ``network`` overrides the environment default; the harness passes the
    strictest boundary its sandbox policy demands for the plan's tiers.
    """
    readable: tuple[Path, ...] = ()
    if conversation_id:
        from agenthub.infrastructure.config.paths import conversation_workspace

        try:
            readable = (conversation_workspace(conversation_id),)
        except ValueError:
            readable = ()
    return SandboxSpec(
        run_id=run_id,
        workspace_root=workspace_root or data_root(),
        readable_roots=readable,
        network=network or network_policy(),
        resources=resource_limits(),
        credentials=CredentialScope(),
        lifetime=SandboxLifetime.RUN,
    )
