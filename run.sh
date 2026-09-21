#!/usr/bin/env bash
# MarketMind AI — one command to run everything locally
# Usage:  ./run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "==> MarketMind AI"
echo "    $ROOT"

# Keep frontend API URL in sync with this script's backend port
if [[ -d frontend ]]; then
  cat > frontend/.env.local <<EOF
# Auto-written by ./run.sh — matches BACKEND_PORT=${BACKEND_PORT}
VITE_API_BASE_URL=http://127.0.0.1:${BACKEND_PORT}
EOF
fi

# --- .env ---
if [[ ! -f .env ]]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
fi

# --- Python venv ---
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "==> Creating venv + installing requirements (first run only)"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

# --- Frontend deps ---
if [[ -d frontend && ! -d frontend/node_modules ]]; then
  echo "==> npm install (first run only)"
  (cd frontend && npm install)
fi

# --- Free ports if something stale is listening ---
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "==> Freeing port $port (pids: $pids)"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 0.5
  fi
done

echo "==> Backend  → http://127.0.0.1:${BACKEND_PORT}"
.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port "${BACKEND_PORT}" &
BACKEND_PID=$!

cleanup() {
  echo ""
  echo "==> Stopping…"
  kill "${BACKEND_PID}" 2>/dev/null || true
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait until API answers
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    echo "==> Backend ready"
    break
  fi
  sleep 0.4
  if [[ "$i" -eq 60 ]]; then
    echo "!!  Backend did not become ready. Check errors above."
  fi
done

FRONTEND_PID=""
if [[ -d frontend ]]; then
  echo "==> Frontend → http://127.0.0.1:${FRONTEND_PORT}"
  (cd frontend && npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}") &
  FRONTEND_PID=$!
fi

echo ""
echo "============================================================"
echo "  Open the app:   http://127.0.0.1:${FRONTEND_PORT}"
echo "  API:            http://127.0.0.1:${BACKEND_PORT}"
echo "  API docs:       http://127.0.0.1:${BACKEND_PORT}/docs"
echo ""
echo "  Tip: click Load Demo Data, or upload any CSV."
echo "  Press Ctrl+C to stop everything."
echo "============================================================"
echo ""

wait
