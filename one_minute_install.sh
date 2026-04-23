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
  python -m xirang --doctor
  # after your provider is ready:
  python -m xirang -p "你好"

Standard setup:
  cp .env.example .env
  # edit .env and choose the provider you actually use

Common provider examples:
  # Local model path: install Ollama first, then run:
  python -m xirang --setup ollama
  # Cloud providers will ask for a key:
  python -m xirang --setup openai
  python -m xirang --setup deepseek

Useful commands:
  /llm presets
  /llm use ollama
  /catalog llm openrouter
  /catalog api weather

One-line install examples:
  ./one_minute_install.sh ollama
  ./one_minute_install.sh openai YOUR_API_KEY
  ./one_minute_install.sh openrouter YOUR_API_KEY
EOF
