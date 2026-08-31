import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import agents, artifacts, attachments, chat, conversations, deployments


app = FastAPI(title="AgentHub Demo API", version="0.1.0")


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
    allow_loopback = os.environ.get("CORS_ALLOW_LOOPBACK_REGEX", "true").strip().lower() not in {
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

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(agents.router)
app.include_router(artifacts.router)
app.include_router(attachments.router)
app.include_router(deployments.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


