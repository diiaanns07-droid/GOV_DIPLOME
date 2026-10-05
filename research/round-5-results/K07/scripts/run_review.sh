#!/usr/bin/env bash
# K07 round 5 REVIEW from the repository root:
#   bash research/round-5-results/K07/scripts/run_review.sh [BUILD_SHA]
# Default BUILD_SHA = baseline K04 @ 0bf27de (needs `git fetch origin claude/beautiful-clarke-sbzomj`).
# Extracts prototypes/city-evidence/web of that commit outside the repo and runs the regression test.
# If research/round-5-results/K07/patch/city_evidence_web.patch exists and BUILD_SHA is the baseline, the patched copy
# is tested too (label "baseline+patch" — a PROPOSAL, not the BUILD's own fix).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
R5="$ROOT/research/round-5-results/K07"
SHA="${1:-0bf27deb8549b325b34a9610402613d745544edb}"
W="${TMPDIR:-/tmp}/k07r5-$SHA"
rm -rf "$W"; mkdir -p "$W"
cd "$ROOT"
python3 "$R5/scripts/extract_build.py" "$W/app" --sha "$SHA" > /dev/null
LABEL=$([ "$SHA" = "0bf27deb8549b325b34a9610402613d745544edb" ] && echo baseline || echo "build-${SHA:0:7}")
node "$R5/tests/k07r5_regressions.cjs" --app-root "$W/app" --label "$LABEL" --sha "$SHA" | tail -1
PATCH="$R5/patch/city_evidence_web.patch"
if [ "$LABEL" = baseline ] && [ -f "$PATCH" ]; then
  mkdir -p "$W/patched/prototypes/city-evidence" && cp -r "$W/app/web" "$W/patched/prototypes/city-evidence/"
  (cd "$W/patched" && git apply --check -p1 "$PATCH" && git apply -p1 "$PATCH")
  node "$R5/tests/k07r5_regressions.cjs" --app-root "$W/patched/prototypes/city-evidence" --label "baseline+patch" --sha "$SHA+patch" | tail -1
fi
