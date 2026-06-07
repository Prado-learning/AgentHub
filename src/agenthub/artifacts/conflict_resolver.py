from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Conflict:
    type: str
    target: str
    producers: list[str]
    resolution: str


def resolve_artifact_conflicts(artifacts: list[dict]) -> tuple[list[dict], list[Conflict]]:
    resolved = _dedupe_artifact_ids(artifacts)
    conflicts = _detect_file_path_conflicts(resolved)
    conflict_artifacts = [_conflict_to_artifact(conflict) for conflict in conflicts]
    return [*resolved, *conflict_artifacts], conflicts


def _dedupe_artifact_ids(artifacts: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    resolved: list[dict] = []
    for artifact in artifacts:
        artifact_id = str(artifact.get("id", "artifact"))
        seen[artifact_id] = seen.get(artifact_id, 0) + 1
        if seen[artifact_id] == 1:
            resolved.append(artifact)
            continue
        resolved.append(
            {
                **artifact,
                "id": f"{artifact_id}_{seen[artifact_id]}",
                "conflict_group": artifact_id,
            }
        )
    return resolved


def _detect_file_path_conflicts(artifacts: list[dict]) -> list[Conflict]:
    by_path: dict[str, list[dict]] = defaultdict(list)
    for artifact in artifacts:
        file_path = artifact.get("file_path")
        if file_path:
            by_path[str(file_path)].append(artifact)

    conflicts: list[Conflict] = []
    for file_path, candidates in by_path.items():
        producers = sorted(
            {
                str(candidate.get("producer_agent_id", candidate.get("id", "unknown")))
                for candidate in candidates
            }
        )
        contents = {str(candidate.get("content", "")) for candidate in candidates}
        if len(candidates) > 1 and len(contents) > 1:
            conflicts.append(
                Conflict(
                    type="file_path",
                    target=file_path,
                    producers=producers,
                    resolution="kept all candidates and emitted a conflict artifact",
                )
            )
    return conflicts


def _conflict_to_artifact(conflict: Conflict) -> dict:
    return {
        "id": f"conflict_{abs(hash((conflict.type, conflict.target))) % 1000000}",
        "type": "conflict",
        "title": f"Conflict: {conflict.target}",
        "content": (
            f"Conflict type: {conflict.type}\n"
            f"Target: {conflict.target}\n"
            f"Producers: {', '.join(conflict.producers)}\n"
            f"Resolution: {conflict.resolution}"
        ),
        "conflict_type": conflict.type,
        "conflict_target": conflict.target,
        "producer_agent_id": "conflict_resolver",
    }

