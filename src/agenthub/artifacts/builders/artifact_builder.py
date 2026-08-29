"""Central construction of artifact records.

Every artifact record produced by a run is built here so the dict shape
stays consistent and the domain model remains the single schema.
"""

from __future__ import annotations

from typing import Any

from agenthub.domain.artifact import Artifact
from agenthub.tools.schemas import ToolResult


def build_artifact(
    artifact_id: str,
    artifact_type: str,
    title: str,
    content: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one artifact record through the ``Artifact`` domain model."""
    return artifact_to_dict(
        Artifact(
            id=artifact_id,
            type=artifact_type,
            title=title,
            content=content,
            metadata=dict(metadata or {}),
        )
    )


def artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "type": artifact.type,
        "title": artifact.title,
        "content": artifact.content,
        **artifact.metadata,
    }


def tool_result_to_artifact(result: ToolResult) -> dict[str, Any]:
    """Convert one tool execution result into an artifact record."""
    metadata: dict[str, Any] = {}
    if result.language:
        metadata["language"] = result.language
    if result.preview_url:
        metadata["preview_url"] = result.preview_url
    if result.preview_html:
        metadata["preview_html"] = result.preview_html
    metadata.update(result.metadata)
    return build_artifact(
        artifact_id=result.id,
        artifact_type=result.type,
        title=result.title,
        content=result.content,
        metadata=metadata,
    )


def stamp_artifact(
    artifact: dict[str, Any],
    producer_agent_id: str,
    step_id: str,
) -> dict[str, Any]:
    """Attach run provenance (producing agent and step) to an artifact."""
    stamped = {
        **artifact,
        "producer_agent_id": artifact.get("producer_agent_id", producer_agent_id),
        "step_id": step_id,
    }
    if stamped.get("type") == "code" and not stamped.get("file_path"):
        stamped["file_path"] = stamped.get("title", "generated.tsx")
    return stamped
