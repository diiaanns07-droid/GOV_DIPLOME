#!/usr/bin/env bash
# Rebuild and check the K07 round-3 prototype from the repository root:
#   bash research/round-3-results/K07/scripts/run_all.sh
# Steps: copy K10 inputs from the fixed SHA (needs `git fetch origin claude/save-work-handoff-j7pc05`),
# graph check, build prototype/data.js, headless user-path test (Node + playwright + preinstalled Chromium).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
K07="$ROOT/research/round-3-results/K07"
VENV="${K07_VENV:-${TMPDIR:-/tmp}/k07r3-venv}"   # outside the repo
PY312="$(command -v python3.12 || true)"
[ -n "$PY312" ] || { echo "python3.12 not found"; exit 1; }
[ -x "$VENV/bin/python" ] || "$PY312" -m venv "$VENV"
"$VENV/bin/pip" install -q -r "$K07/scripts/requirements.txt"
cd "$ROOT"
"$VENV/bin/python" "$K07/scripts/copy_inputs.py"
"$VENV/bin/python" "$K07/scripts/graph_check.py" > /dev/null
"$VENV/bin/python" "$K07/scripts/build_data.py"
node "$K07/tests/user_path.cjs"
