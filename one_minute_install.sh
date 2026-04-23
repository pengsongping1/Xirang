#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
SETUP_PROVIDER="${1:-}"
SETUP_KEY="${2:-${XIRANG_API_KEY:-}}"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install -e . >/dev/null

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
fi

API_README="${BOOTSTRAP_API:-../third_party/public-apis/README.md}"
LLM_README="${BOOTSTRAP_LLM:-../third_party/free-llm-api-resources/README.md}"
IMPORT_ARGS=()
[ -f "$API_README" ] && IMPORT_ARGS+=(--api-readme "$API_README")
[ -f "$LLM_README" ] && IMPORT_ARGS+=(--llm-readme "$LLM_README")
if [ "${#IMPORT_ARGS[@]}" -gt 0 ]; then
  python scripts/bootstrap_catalogs.py "${IMPORT_ARGS[@]}" >/dev/null 2>&1 || true
fi

if [ -n "$SETUP_PROVIDER" ]; then
  SETUP_ARGS=(--setup "$SETUP_PROVIDER")
  if [ -n "$SETUP_KEY" ]; then
    SETUP_ARGS+=(--api-key "$SETUP_KEY")
  fi
  python -m xirang "${SETUP_ARGS[@]}"
fi

cat <<'EOF'
Xirang is installed.

Quick start:
  source .venv/bin/activate
  python -m xirang --setup openrouter
  python -m xirang --doctor
  python -m xirang -p "你好"

Useful commands:
  /llm presets
  /llm use ollama
  /catalog llm openrouter
  /catalog api weather

One-line install with key:
  ./one_minute_install.sh openrouter YOUR_API_KEY
EOF
