from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from agenthub.infrastructure.config.paths import data_root
from agenthub.sandbox.path_policy import (
    safe_identifier,
    resolve_within,
)

router = APIRouter(tags=["deployments"])
DEPLOYMENT_DIR = data_root() / "deployments"
SANDBOX_HEADERS = {
    "Content-Security-Policy": "sandbox allow-scripts allow-forms",
    "X-Content-Type-Options": "nosniff",
}


@router.get("/deployments/{deployment_id}/{file_path:path}")
def read_deployment_file(deployment_id: str, file_path: str) -> FileResponse:
    try:
        root = resolve_within(DEPLOYMENT_DIR, safe_identifier(deployment_id))
        target = resolve_within(root, file_path)
        if not target.is_file():
            raise ValueError("Missing file")
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail="Deployment file not found"
        ) from exc
    return FileResponse(target, headers=SANDBOX_HEADERS)
