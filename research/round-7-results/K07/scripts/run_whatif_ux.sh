#!/usr/bin/env bash
# K07 round 7, from the repository root (needs `git fetch origin claude/beautiful-clarke-sbzomj`, Node + playwright):
#   bash research/round-7-results/K07/scripts/run_whatif_ux.sh             # PROPOSAL: BUILD c58a3b2 + patch/city_evidence_whatif_ui.patch
#   bash research/round-7-results/K07/scripts/run_whatif_ux.sh <BUILD_SHA> # a BUILD commit that integrated the UI itself (no patch)
# Extracts prototypes/city-evidence/{web,tests} of the commit byte-exactly into a new temp dir outside the repo, applies the
# patch only for the default base, runs tests/k07r7_whatif_ux.cjs and the BUILD's own tests/conformance.cjs + tests/smoke.cjs
# of the same commit. Writes results/<label>/result.json and results/<label>/build_tests.txt. Nothing in the repo is applied.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
K="$ROOT/research/round-7-results/K07"
BASE="c58a3b2b175cf978ad785fef7f88d8fd9b1338f2"
SHA="${1:-$BASE}"
PATCH="$K/patch/city_evidence_whatif_ui.patch"
W="$(mktemp -d "${TMPDIR:-/tmp}/k07r7-XXXXXX")"
APP="$W/prototypes/city-evidence"
cd "$ROOT"
python3 "$K/scripts/extract_build.py" "$APP" --sha "$SHA"
mkdir -p "$APP/tests"
for f in smoke.cjs conformance.cjs expected_explanations.json; do
  python3 -c "import subprocess,pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(subprocess.check_output(['git','cat-file','blob',sys.argv[2]]))" \
    "$APP/tests/$f" "$SHA:prototypes/city-evidence/tests/$f"
done
if [ "$SHA" = "$BASE" ]; then
  (cd "$W" && git apply --check -p1 "$PATCH" && git apply -p1 "$PATCH")
  LABEL="proposal_on_${SHA:0:7}"; TSHA="${SHA:0:7}+k07patch"
else
  LABEL="build_${SHA:0:7}"; TSHA="$SHA"
fi
set +e
node "$K/tests/k07r7_whatif_ux.cjs" --app-root "$APP" --label "$LABEL" --sha "$TSHA" | tail -1
UX=${PIPESTATUS[0]}
mkdir -p "$K/results/$LABEL"
( cd "$APP" && { echo "conformance: $(node tests/conformance.cjs | tail -1)"; node tests/smoke.cjs "$W/smoke" | grep -E "^(PASS|FAIL)"; } ) > "$K/results/$LABEL/build_tests.txt"
echo "BUILD tests of ${SHA:0:7} on this copy: $(grep -c '^PASS' "$K/results/$LABEL/build_tests.txt") smoke PASS, $(grep -c '^FAIL' "$K/results/$LABEL/build_tests.txt") FAIL; $(head -1 "$K/results/$LABEL/build_tests.txt")"
echo "work dir: $W"
exit "$UX"
