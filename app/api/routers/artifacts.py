from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.api.services.artifact_service import get_artifact, get_preview_html, list_artifacts
from app.api.services.diff_service import apply_diff_artifact, rollback_diff_application


router = APIRouter(tags=["artifacts"])


@router.get("/artifacts/{artifact_id}")
def read_artifact(artifact_id: str) -> dict:
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.get("/conversations/{conversation_id}/artifacts")
def read_conversation_artifacts(conversation_id: str) -> dict[str, list[dict]]:
    return {"artifacts": list_artifacts(conversation_id)}


@router.get("/artifacts/{artifact_id}/preview", response_class=HTMLResponse)
def read_artifact_preview(artifact_id: str) -> str:
    html = get_preview_html(artifact_id)
    if html is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    return html


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

