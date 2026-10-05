#!/usr/bin/env bash
# K07 round 4 REVIEW, one command from the repository root:
#   bash research/round-4-results/K07/scripts/run_review.sh
# Needs: git (snapshot 6778ded present locally), python3, node + playwright (preinstalled Chromium). No network.
# Work dir is outside the repo; outputs go to research/round-4-results/K07/results/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
R4="$ROOT/research/round-4-results/K07"
P="research/round-3-results/K07/prototype"
SNAP=6778deda6d3f3a7f27698f651c1b0046d2a9aae9
W="${TMPDIR:-/tmp}/k07r4-review"
rm -rf "$W"; mkdir -p "$W/snapshot" "$W/patched/$P" "$W/r3reg/tests" "$W/r3reg/prototype"
cd "$ROOT"
python3 "$R4/scripts/extract_snapshot.py" "$W/snapshot" > /dev/null
python3 "$R4/scripts/extract_snapshot.py" "$W/patched/$P" > /dev/null
(cd "$W/patched" && git apply --check -p1 "$R4/patch/k07_round3_prototype.patch" && git apply -p1 "$R4/patch/k07_round3_prototype.patch")
node "$R4/tests/review_user_path.cjs" "$W/snapshot" snapshot | tail -1
node "$R4/tests/review_user_path.cjs" "$W/patched/$P" patched | tail -1
# regression: the round-3 test of the same snapshot, run against the patched copy
python3 -c "import subprocess,pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(subprocess.check_output(['git','cat-file','blob','$SNAP:research/round-3-results/K07/tests/user_path.cjs']))" "$W/r3reg/tests/user_path.cjs"
cp "$W/patched/$P/"* "$W/r3reg/prototype/"
node "$W/r3reg/tests/user_path.cjs" | tail -1 || true
cp "$W/r3reg/results/user_path_test.json" "$R4/results/regression_round3_test_on_patched.json"
