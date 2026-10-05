#!/usr/bin/env bash
# Reproduce K07 results from the repository root: bash research/next-round/K07/scripts/run_all.sh
# No network access is needed except PyPI for the venv. Originals in govtech-results/ are only read.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
VENV="${K07_VENV:-${TMPDIR:-/tmp}/k07-venv}"  # outside the repo, nothing to commit
PY312="$(command -v python3.12 || true)"
[ -n "$PY312" ] || { echo "python3.12 not found"; exit 1; }
[ -x "$VENV/bin/python" ] || "$PY312" -m venv "$VENV"
"$VENV/bin/pip" install -q -r "$ROOT/research/next-round/K07/scripts/requirements.txt"
cd "$ROOT"
"$VENV/bin/python" research/next-round/K07/scripts/verify_a04_a05.py
for s in research/next-round/K07/scripts/[0-9][0-9]_*.py; do
  [ -e "$s" ] && "$VENV/bin/python" "$s"
done
