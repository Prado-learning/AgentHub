"""python -m agenthub: one local server for API and built web UI."""

import argparse
import os
from agenthub.infrastructure.config.paths import PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description="Start local AgentHub")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--demo", action="store_true", help="Explicit mock mode; ignore .env"
    )
    args = parser.parse_args()
    os.chdir(PROJECT_ROOT)
    if args.demo:
        os.environ.update(
            AGENTHUB_SKIP_ENV_FILE="1",
            ENABLE_REAL_LLM="false",
            ENABLE_LLM_PLANNER="false",
            GATEWAY_ENABLED="false",
        )
    import uvicorn

    uvicorn.run("app.api.main:app", host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
