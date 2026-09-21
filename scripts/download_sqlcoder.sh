#!/usr/bin/env bash
# Download / verify the Defog SQLCoder GGUF used by MarketMind AI.
# Safe to re-run; skips when the file already exists.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export SQLCODER_ENABLED="${SQLCODER_ENABLED:-true}"
export SQLCODER_HF_REPO="${SQLCODER_HF_REPO:-MaziyarPanahi/sqlcoder-7b-2-GGUF}"
export SQLCODER_HF_FILE="${SQLCODER_HF_FILE:-sqlcoder-7b-2.Q3_K_S.gguf}"

echo "Resolving SQLCoder model (${SQLCODER_HF_REPO}/${SQLCODER_HF_FILE})…"
.venv/bin/python - <<'PY'
from backend.services.sql.sqlcoder_service import resolve_model_path, sqlcoder_status
path = resolve_model_path()
print(f"Model ready: {path} ({path.stat().st_size / 1e9:.2f} GB)")
print("Status:", sqlcoder_status())
PY
