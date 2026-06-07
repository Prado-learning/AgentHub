from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


router = APIRouter(tags=["deployments"])
DEPLOYMENT_DIR = Path("agent-workspace/deployments")


@router.get("/deployments/{deployment_id}/{file_path:path}")
def read_deployment_file(deployment_id: str, file_path: str) -> FileResponse:
    root = (DEPLOYMENT_DIR / deployment_id).resolve()
    target = (root / file_path).resolve()
    if not str(target).lower().startswith(str(root).lower()) or not target.exists():
        raise HTTPException(status_code=404, detail="Deployment file not found")
    return FileResponse(target)
