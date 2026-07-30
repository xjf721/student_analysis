#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ "$SCRIPT_PATH" == */* ]]; then
    SCRIPT_DIR="${SCRIPT_PATH%/*}"
else
    SCRIPT_DIR="."
fi
PROJECT_DIR="$(cd "$SCRIPT_DIR" && pwd -P)"
cd "$PROJECT_DIR"

if [[ -x ".venv/bin/python" ]]; then
    PYTHON_EXE=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_EXE="$(command -v python)"
else
    echo "[ERROR] Python 3 was not found. Install Python or create .venv first." >&2
    exit 1
fi

exec "$PYTHON_EXE" scripts/export_release.py "$@"
