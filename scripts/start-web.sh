#!/bin/bash
# scripts/start-web.sh -- Start HOOK Web UI (FastAPI backend + Vite dev server)
#
# Usage:
#   ./scripts/start-web.sh          # Start both backend and frontend (dev mode)
#   ./scripts/start-web.sh --api    # Start API server only
#   ./scripts/start-web.sh --build  # Build frontend for production
#
set -euo pipefail

HOOK_DIR="${HOOK_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
export HOOK_DIR

PORT="${HOOK_WEB_PORT:-7799}"

case "${1:-}" in
  --api)
    echo "[HOOK] Starting API server on port $PORT..."
    cd "$HOOK_DIR"
    python3 -m uvicorn web.api.server:app --host 0.0.0.0 --port "$PORT"
    ;;
  --build)
    echo "[HOOK] Building frontend..."
    cd "$HOOK_DIR/web"
    npm install
    npm run build
    echo "[HOOK] Frontend built to web/dist/"
    echo "[HOOK] Start with: ./scripts/start-web.sh --api"
    ;;
  *)
    echo "[HOOK] Starting HOOK Web UI (dev mode)..."
    echo "[HOOK]   API:      http://localhost:$PORT"
    echo "[HOOK]   Frontend: http://localhost:5173"
    echo ""

    # Start API server in background
    cd "$HOOK_DIR"
    python3 -m uvicorn web.api.server:app --host 0.0.0.0 --port "$PORT" &
    API_PID=$!

    # Start Vite dev server
    cd "$HOOK_DIR/web"
    if [ ! -d "node_modules" ]; then
      echo "[HOOK] Installing frontend dependencies..."
      npm install
    fi
    npm run dev &
    VITE_PID=$!

    # Handle cleanup
    trap "kill $API_PID $VITE_PID 2>/dev/null; exit" INT TERM
    echo "[HOOK] Press Ctrl+C to stop both servers."
    wait
    ;;
esac
