#!/usr/bin/env bash
# Render build entrypoint — runs from repo root (leave Root Directory blank).
set -euo pipefail
echo "==> pwd: $(pwd)"
echo "==> listing:"
ls -la
if [[ ! -f requirements.txt ]]; then
  echo "ERROR: requirements.txt not found. Clear Root Directory in Render settings (must be empty)."
  exit 1
fi
pip install --upgrade pip
pip install -r requirements.txt
