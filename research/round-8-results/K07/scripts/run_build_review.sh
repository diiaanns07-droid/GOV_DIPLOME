#!/usr/bin/env bash
# K07 round 8 — independent review of the BUILD planner (city-plan-v2), from the repository root:
#   bash research/round-8-results/K07/scripts/run_build_review.sh             # BUILD d865dd4 (code = 3e1302a), then d865dd4 + K07 fix patch
#   bash research/round-8-results/K07/scripts/run_build_review.sh <BUILD_SHA> # a later BUILD commit as is (no patch)
# Needs `git fetch origin claude/beautiful-clarke-sbzomj`, Node + playwright, python3. Extracts web/ and tests/ of the commit
# byte-exactly into a new temp dir outside the repo and runs:
#   the BUILD's own tests (conformance, whatif, plan, smoke, whatif_smoke, plan_smoke),
#   tests/build_engine_crosscheck.cjs (BUILD plan.js vs the K07 Python oracle),
#   tests/k07r8_build_planner.cjs (browser: user path, refusals, keyboard, 390 px).
# For the default SHA the same is repeated on a copy with patch/build_d865dd4_planner_keyboard_390.patch applied.
# Results: results/build_<sha7>[+k07fix]/{result.json, engine/, build_tests.txt, screenshots/}.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
K="$ROOT/research/round-8-results/K07"
DEF="d865dd4a124291e10dd0b7bb1d9eada20d34c268"
SHA="${1:-$DEF}"
PATCH="$K/patch/build_d865dd4_planner_keyboard_390.patch"
W="$(mktemp -d "${TMPDIR:-/tmp}/k07r8b-XXXXXX")"
cd "$ROOT"
python3 "$K/scripts/extract_build.py" "$W/a/prototypes/city-evidence" --sha "$SHA"
review() {  # $1 app dir, $2 label, $3 sha text
  local APP="$1" OUTD="$K/results/$2"
  mkdir -p "$OUTD"
  ( cd "$APP" && for t in conformance whatif plan; do echo "$t: $(node tests/$t.cjs | tail -1)"; done
    for t in smoke whatif_smoke plan_smoke; do node tests/$t.cjs "$W/out-$2" | grep -E "^(PASS|FAIL)" | sed "s/^/$t: /"; done ) > "$OUTD/build_tests.txt" || true
  echo "[$2] BUILD tests: $(grep -c ': PASS' "$OUTD/build_tests.txt") browser PASS, $(grep -c ': FAIL' "$OUTD/build_tests.txt") FAIL; $(grep -E '^(conformance|whatif|plan):' "$OUTD/build_tests.txt" | tr '\n' ' ')"
  echo "[$2] engine vs oracle: $(node "$K/tests/build_engine_crosscheck.cjs" --app-root "$APP" --out "$OUTD/engine" | tail -1)"
  echo "[$2] browser review: $(node "$K/tests/k07r8_build_planner.cjs" --app-root "$APP" --label "$2" --sha "$3" | tail -1)"
}
set +e
review "$W/a/prototypes/city-evidence" "build_${SHA:0:7}" "$SHA"
if [ "$SHA" = "$DEF" ]; then
  mkdir -p "$W/b/prototypes/city-evidence" && cp -r "$W/a/prototypes/city-evidence/web" "$W/a/prototypes/city-evidence/tests" "$W/b/prototypes/city-evidence/"
  (cd "$W/b" && git apply --check -p1 "$PATCH" && git apply -p1 "$PATCH") || { echo "patch does not apply"; exit 4; }
  review "$W/b/prototypes/city-evidence" "build_${SHA:0:7}+k07fix" "${SHA:0:7}+k07fix"
fi
echo "work dir: $W"
