import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from agenthub.infrastructure.config.env import load_env_file

load_env_file()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from agenthub.infrastructure.config.paths import PROJECT_ROOT
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    agents,
    artifacts,
    attachments,
    chat,
    conversations,
    deployments,
    run_decisions,
)


@asynccontextmanager
async def lifespan(app):
    from app.api.services.execution_service import recover_interrupted_runs

    recover_interrupted_runs()
    yield


app = FastAPI(title="AgentHub", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
)


def _cors_origins() -> tuple[list[str], str | None]:
    """Resolve CORS configuration from environment.

    CORS_ALLOWED_ORIGINS: comma-separated explicit allow-list. When unset,
    the dev defaults below are used (safe for local development).
    Set CORS_ALLOW_LOOPBACK_REGEX=false to disable the loopback regex.
    """
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        return origins, None

    dev_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://0.0.0.0:5173",
        "http://0.0.0.0:3000",
    ]
    allow_loopback = os.environ.get(
        "CORS_ALLOW_LOOPBACK_REGEX", "true"
    ).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    regex = (
        r"^https?://(\[::1\]|localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$"
        if allow_loopback
        else None
    )
    return dev_origins, regex


cors_origins, cors_regex = _cors_origins()
cors_kwargs = {
    "allow_origins": cors_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if cors_regex:
    cors_kwargs["allow_origin_regex"] = cors_regex

app.add_middleware(CORSMiddleware, **cors_kwargs)

for router in (
    chat.router,
    conversations.router,
    agents.router,
    artifacts.router,
    attachments.router,
    deployments.router,
    run_decisions.router,
):
    app.include_router(router)
    app.include_router(router, prefix="/api", include_in_schema=False)


@app.middleware("http")
async def local_browser_boundary(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        allowed = origin in cors_origins or bool(
            cors_regex and origin and re.fullmatch(cors_regex, origin)
        )
        if origin and not allowed:
            return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
        if request.headers.get("content-type", "").split(";", 1)[0] not in {
            "",
            "application/json",
        }:
            return JSONResponse({"detail": "Use application/json"}, status_code=415)
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health", include_in_schema=False)
def api_health():
    return health()


@app.get("/api/runtime-info", include_in_schema=False)
@app.get("/runtime-info")
def runtime_info():
    from agenthub.infrastructure.config.env import env_flag

    return {
        "mode": "configured" if env_flag("ENABLE_REAL_LLM") else "demo",
        "local_only": True,
    }


WEB_DIST = PROJECT_ROOT / "app" / "web" / "dist"
if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def web_index():
    if (WEB_DIST / "index.html").is_file():
        return FileResponse(WEB_DIST / "index.html")
    return JSONResponse(
        {"detail": "Frontend not built. Run npm ci && npm run build in app/web."},
        status_code=503,
    )
