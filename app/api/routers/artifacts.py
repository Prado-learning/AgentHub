from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.api.services.artifact_service import (
    get_artifact,
    get_preview_html,
    list_artifact_versions,
    list_artifacts,
    restore_artifact_version,
    update_artifact,
)
from app.api.services.diff_service import (
    apply_diff_artifact,
    get_structured_diff,
    rollback_diff_application,
)


router = APIRouter(tags=["artifacts"])


class ArtifactUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    language: str | None = None


@router.get("/artifacts/{artifact_id}")
def read_artifact(artifact_id: str) -> dict:
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.patch("/artifacts/{artifact_id}")
def patch_artifact(artifact_id: str, request: ArtifactUpdateRequest) -> dict:
    artifact = update_artifact(artifact_id, request.model_dump(exclude_unset=True))
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"artifact": artifact}


@router.get("/artifacts/{artifact_id}/versions")
def read_artifact_versions(artifact_id: str) -> dict[str, list[dict]]:
    if get_artifact(artifact_id) is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"versions": list_artifact_versions(artifact_id)}


@router.post("/artifacts/{artifact_id}/versions/{version_id}/restore")
def restore_version(artifact_id: str, version_id: str) -> dict:
    artifact = restore_artifact_version(artifact_id, version_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    return {"artifact": artifact}


@router.get("/conversations/{conversation_id}/artifacts")
def read_conversation_artifacts(conversation_id: str) -> dict[str, list[dict]]:
    return {"artifacts": list_artifacts(conversation_id)}


@router.get("/artifacts/{artifact_id}/preview", response_class=HTMLResponse)
def read_artifact_preview(artifact_id: str) -> str:
    html = get_preview_html(artifact_id)
    if html is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    return html


@router.get("/artifacts/{artifact_id}/diff")
def read_artifact_diff(artifact_id: str) -> dict:
    try:
        return get_structured_diff(artifact_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/artifacts/{artifact_id}/apply")
def apply_artifact_diff(artifact_id: str) -> dict:
    try:
        return {"application": apply_diff_artifact(artifact_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/artifacts/{artifact_id}/rollback")
def rollback_artifact_diff(artifact_id: str) -> dict:
    artifact = get_artifact(artifact_id)
    if artifact is None or not artifact.get("apply_id"):
        raise HTTPException(status_code=404, detail="Applied diff not found")
    try:
        return {"application": rollback_diff_application(str(artifact["apply_id"]))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
