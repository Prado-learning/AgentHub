"""Action fingerprints binding an approval to one exact dispatch.

An approval is only meaningful if it names a single concrete action. The
fingerprint hashes everything that determines what will actually happen:
the step's full field set, the complete run context (including upstream
artifacts walked from every dependency ancestor), the adapter and
provider identity, the agent profile, and a hash of the model
credential. Changing any one of them — even swapping the API key —
invalidates a previously granted approval.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from agenthub.adapters.base import AgentTask
from agenthub.domain.plan import PlanStep
from agenthub.domain.run import RunContext
from agenthub.gateway.gateway import GatewayDispatch, _dispatch_key


def action_fingerprint(
    *,
    step: PlanStep,
    context: RunContext,
    adapter,
    profile=None,
) -> str:
    """SHA-256 over the full dispatch identity of ``step``."""
    identity = _dispatch_key(
        adapter,
        GatewayDispatch(
            endpoint=step.agent_id,
            task=AgentTask(
                agent_id=step.agent_id, instruction=step.task, tools=step.tools
            ),
            context=context,
        ),
    )
    payload = {
        "adapter_identity": identity,
        "step": asdict(step),
        "context": asdict(context),
        "profile": asdict(profile) if profile else None,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
