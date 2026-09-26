#!/bin/sh
# Run from simulation. Offline regression gate; browser acceptance is separate.
set -eu
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.cache/uv"
export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
export UV_PYTHON_DOWNLOADS=never
export TMPDIR="$PWD/.tmp"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR"
uv sync --project . --locked --offline
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m coordination_sim smoke
sh scripts/verify_ui.sh
.venv/bin/python -B scripts/check_repository.py
