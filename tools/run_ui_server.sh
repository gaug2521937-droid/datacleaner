#!/usr/bin/env bash
# Локальный сервер для UI-проверок (не для прода): DRY_RUN=1, тестовая база в /tmp.
set -euo pipefail
export DATA_KEY="${DATA_KEY:-$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')}"
export DATACLEANER_DB="${DATACLEANER_DB:-/tmp/ui.db}"
export DRY_RUN="${DRY_RUN:-1}"
export LLM_BASE_URL="${LLM_BASE_URL:-https://example.invalid/v1}"
export LLM_API_KEY="${LLM_API_KEY:-sk-local-smoke}"
export LLM_MODEL="${LLM_MODEL:-gpt-6-luna}"
cd "$(dirname "$0")/.."
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8811}"
