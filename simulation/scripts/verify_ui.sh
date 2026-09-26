#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
node --check ui/app.js
# Capture a fresh evidence path without relying on timestamps or mutable latest links.
judge_data=$(.venv/bin/python -B - <<'PY'
from coordination_sim.benchmark.runner import run
print(run()/'judge-data.json')
PY
)
node tests/ui.test.cjs "$judge_data"
