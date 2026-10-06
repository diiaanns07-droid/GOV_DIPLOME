#!/usr/bin/env bash
# K07 round 9 — review of the real BUILD page, from the repository root:
#   bash research/round-9-results/K07/scripts/run_r9_review.sh             # BUILD d865dd4 as is, then d865dd4 + K07 r9 patches (copy)
#   bash research/round-9-results/K07/scripts/run_r9_review.sh <BUILD_SHA> # a newer BUILD commit as is (no patch) — integration check
# Needs `git fetch origin claude/beautiful-clarke-sbzomj`, Node + playwright, python3. Extracts web/ + tests/ byte-exactly into a
# new temp dir outside the repo and runs:
#   BUILD's own tests (conformance, whatif, plan, smoke, whatif_smoke, plan_smoke; resilience tests if the commit has them),
#   r8 tests reused unchanged: research/round-8-results/K07/tests/{build_engine_crosscheck,k07r8_build_planner}.cjs,
#   r9 tests: tests/k07r9_n2_scroll.cjs, tests/resilience_k07.test.cjs (K07 adapter on this plan.js vs the Python oracle),
#   tests/k07r9_resilience_ui.cjs (panel in the page; on a build without the panel it reports TEST_INCOMPATIBLE P0).
# Results: research/round-9-results/K07/results/<label>/…  Nothing in prototypes/city-evidence is changed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
K="$ROOT/research/round-9-results/K07"; R8="$ROOT/research/round-8-results/K07"
DEF="d865dd4a124291e10dd0b7bb1d9eada20d34c268"
SHA="${1:-$DEF}"
PATCHES=("$K/patch/build_d865dd4_r9_keyboard.patch")
[ -f "$K/patch/build_d865dd4_r9_resilience_panel.patch" ] && PATCHES+=("$K/patch/build_d865dd4_r9_resilience_panel.patch")
W="$(mktemp -d "${TMPDIR:-/tmp}/k07r9-XXXXXX")"
cd "$ROOT"
python3 "$K/scripts/extract_build.py" "$W/a/prototypes/city-evidence" --sha "$SHA"
review() {  # $1 app dir, $2 label, $3 sha text
  local APP="$1" OUTD="$K/results/$2"
  mkdir -p "$OUTD"
  ( cd "$APP" && for t in conformance whatif plan resilience; do [ -f tests/$t.cjs ] && echo "$t: $(node tests/$t.cjs | tail -1)"; done
    for t in smoke whatif_smoke plan_smoke resilience_smoke; do [ -f tests/$t.cjs ] && node tests/$t.cjs "$W/out-$2" | grep -E "^(PASS|FAIL)" | sed "s/^/$t: /"; done; true ) > "$OUTD/build_tests.txt" 2>&1 || true
  echo "[$2] BUILD tests: $(grep -c ': PASS' "$OUTD/build_tests.txt") browser PASS, $(grep -c ': FAIL' "$OUTD/build_tests.txt") FAIL; $(grep -E '^(conformance|whatif|plan|resilience):' "$OUTD/build_tests.txt" | tr '\n' ' ')"
  echo "[$2] r8 engine vs oracle: $(node "$R8/tests/build_engine_crosscheck.cjs" --app-root "$APP" --out "$OUTD/r8_engine" | tail -1)"
  echo "[$2] r8 browser review: $(node "$R8/tests/k07r8_build_planner.cjs" --app-root "$APP" --label "$2" --sha "$3" --out "$OUTD/r8_browser" | tail -1)"
  echo "[$2] r9 N2 assessment: $(node "$K/tests/k07r9_n2_scroll.cjs" --app-root "$APP" --label "$2" --sha "$3" --out "$OUTD/r9_n2" | tail -1)"
  echo "[$2] r9 resilience adapter on this plan.js (headless, Python oracle): $(node "$K/tests/resilience_k07.test.cjs" --app-root "$APP" --out "$OUTD/r9_resilience_calc" | tail -1)"
  if [ -f "$K/tests/k07r9_resilience_ui.cjs" ]; then
    echo "[$2] r9 resilience UI: $(node "$K/tests/k07r9_resilience_ui.cjs" --app-root "$APP" --label "$2" --sha "$3" --out "$OUTD/r9_resilience" | tail -1)"
  fi
}
set +e
review "$W/a/prototypes/city-evidence" "build_${SHA:0:7}" "$SHA"
if [ "$SHA" = "$DEF" ]; then
  mkdir -p "$W/b/prototypes/city-evidence" && cp -r "$W/a/prototypes/city-evidence/web" "$W/a/prototypes/city-evidence/tests" "$W/b/prototypes/city-evidence/"
  for P in "${PATCHES[@]}"; do (cd "$W/b" && git apply --check -p1 "$P" && git apply -p1 "$P") || { echo "patch does not apply: $P"; exit 4; }; done
  review "$W/b/prototypes/city-evidence" "build_${SHA:0:7}+k07r9" "${SHA:0:7}+k07r9"
fi
echo "work dir: $W"
