#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"
uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

cd "$ROOT_DIR/app/web"
npm run dev &
WEB_PID=$!

trap 'kill "$API_PID" "$WEB_PID" 2>/dev/null || true' EXIT
wait
