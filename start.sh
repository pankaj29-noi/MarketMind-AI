#!/usr/bin/env bash
# MarketMind AI — one-command local startup (DEMO MODE friendly)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "==> MarketMind AI startup"
echo "    Project: $ROOT"

# --- .env ---
if [[ ! -f .env ]]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
fi

# Ensure DEMO_MODE is present (auto = demo extraction when no real Groq key)
if ! grep -q '^DEMO_MODE=' .env 2>/dev/null; then
  echo "DEMO_MODE=auto" >> .env
  echo "==> Added DEMO_MODE=auto to .env"
fi

# --- Docker / Postgres ---
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    echo "==> Starting PostgreSQL (docker compose)"
    docker compose up -d
  else
    echo "!!  Docker is installed but not running."
    echo "    Open Docker Desktop on macOS, wait until it is ready, then re-run ./start.sh"
    echo "    Continuing anyway — marketplace demo + Lead DEMO MODE work without Postgres."
  fi
else
  echo "!!  Docker not found. Postgres persistence skipped (in-memory fallbacks still work)."
fi

# --- Python venv ---
if [[ ! -x .venv/bin/python ]]; then
  echo "==> Creating Python venv"
  python3 -m venv .venv
fi
echo "==> Installing Python dependencies"
.venv/bin/pip install -q -r requirements.txt

# --- Frontend deps ---
if [[ -d frontend ]]; then
  if [[ ! -d frontend/node_modules ]]; then
    echo "==> Installing frontend dependencies (npm install)"
    (cd frontend && npm install)
  fi
fi

# --- Free / reuse ports ---
BACKEND_PORT=8000
FRONTEND_PORT=5173

echo "==> Starting backend on http://127.0.0.1:${BACKEND_PORT}"
.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port "${BACKEND_PORT}" &
BACKEND_PID=$!

cleanup() {
  echo "==> Shutting down (pid backend=${BACKEND_PID} frontend=${FRONTEND_PID:-n/a})"
  kill "${BACKEND_PID}" 2>/dev/null || true
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Wait for backend health
for i in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/docs" >/dev/null 2>&1; then
    echo "==> Backend ready"
    break
  fi
  sleep 0.5
  if [[ "$i" -eq 40 ]]; then
    echo "!!  Backend did not become ready in time. Check logs above."
  fi
done

if [[ -d frontend ]]; then
  echo "==> Starting frontend on http://127.0.0.1:${FRONTEND_PORT}"
  (cd frontend && npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}") &
  FRONTEND_PID=$!
fi

echo ""
echo "============================================================"
echo " MarketMind AI is running"
echo "   Frontend:  http://127.0.0.1:${FRONTEND_PORT}"
echo "   Backend:   http://127.0.0.1:${BACKEND_PORT}"
echo "   API docs:  http://127.0.0.1:${BACKEND_PORT}/docs"
echo ""
echo " DEMO MODE: if GROQ_API_KEY is a placeholder, Lead Intelligence"
echo " uses a deterministic demo extractor (NOT a live LLM)."
echo " Set a real GROQ_API_KEY in .env for full LLM mode."
echo "============================================================"
echo " Press Ctrl+C to stop."
echo ""

wait
