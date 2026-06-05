from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.api.services.artifact_service import get_artifact, get_preview_html


router = APIRouter(tags=["artifacts"])


@router.get("/artifacts/{artifact_id}")
def read_artifact(artifact_id: str) -> dict:
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.get("/artifacts/{artifact_id}/preview", response_class=HTMLResponse)
def read_artifact_preview(artifact_id: str) -> str:
    html = get_preview_html(artifact_id)
    if html is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    return html

