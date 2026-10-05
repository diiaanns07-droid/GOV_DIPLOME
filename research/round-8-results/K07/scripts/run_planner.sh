#!/usr/bin/env bash
# K07 round 8, from the repository root (needs `git fetch origin claude/beautiful-clarke-sbzomj`, Node + playwright, python3):
#   bash research/round-8-results/K07/scripts/run_planner.sh             # PROPOSAL: BUILD a5b5e2d + patch/city_evidence_planner.patch
#   bash research/round-8-results/K07/scripts/run_planner.sh <BUILD_SHA> # a BUILD commit that integrated the planner itself
# Extracts prototypes/city-evidence/{web,tests} byte-exactly into a new temp dir outside the repo, applies the patch only
# for the default base (and checks that its modules equal research/round-8-results/K07/web/), then runs
#   tests/plan_calc.test.cjs (headless calculator + Python oracle), tests/k07r8_planner_ui.cjs (browser),
#   the BUILD's own tests of the same commit: conformance.cjs, whatif.cjs, smoke.cjs, whatif_smoke.cjs.
# Results: results/<label>/{result.json, calc/, build_tests.txt}. Nothing in the repo's prototype is changed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
K="$ROOT/research/round-8-results/K07"
BASE="a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d"
SHA="${1:-$BASE}"
PATCH="$K/patch/city_evidence_planner.patch"
W="$(mktemp -d "${TMPDIR:-/tmp}/k07r8-XXXXXX")"
APP="$W/prototypes/city-evidence"
cd "$ROOT"
python3 "$K/scripts/extract_build.py" "$APP" --sha "$SHA"
if [ "$SHA" = "$BASE" ]; then
  (cd "$W" && git apply --check -p1 "$PATCH" && git apply -p1 "$PATCH")
  for f in plan_calc.js plan_runner.js plan_demo.js planner_ui.js; do cmp -s "$APP/web/$f" "$K/web/$f" || { echo "patch module $f differs from $K/web/$f"; exit 4; }; done
  LABEL="proposal_on_${SHA:0:7}"; TSHA="${SHA:0:7}+k07r8patch"
else
  LABEL="build_${SHA:0:7}"; TSHA="$SHA"
fi
mkdir -p "$K/results/$LABEL"
set +e
node "$K/tests/plan_calc.test.cjs" --app-root "$APP" --out "$K/results/$LABEL/calc" | tail -1; CALC=${PIPESTATUS[0]}
node "$K/tests/k07r8_planner_ui.cjs" --app-root "$APP" --label "$LABEL" --sha "$TSHA" | tail -1; UI=${PIPESTATUS[0]}
( cd "$APP" && for t in conformance whatif; do echo "$t: $(node tests/$t.cjs | tail -1)"; done
  for t in smoke whatif_smoke; do node tests/$t.cjs "$W/out" | grep -E "^(PASS|FAIL)" | sed "s/^/$t: /"; done ) > "$K/results/$LABEL/build_tests.txt"
echo "BUILD tests of ${SHA:0:7} on this copy: $(grep -c ': PASS' "$K/results/$LABEL/build_tests.txt") PASS, $(grep -c ': FAIL' "$K/results/$LABEL/build_tests.txt") FAIL; $(grep -E '^(conformance|whatif):' "$K/results/$LABEL/build_tests.txt" | tr '\n' ' ')"
echo "work dir: $W"
[ "$CALC" = 0 ] && [ "$UI" = 0 ]
