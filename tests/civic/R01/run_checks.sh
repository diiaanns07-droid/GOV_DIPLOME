#!/usr/bin/env bash
# R01: all build checks in one go, from the repository root:  bash tests/civic/R01/run_checks.sh [out_dir]
# Python suites, the HTTP web_check, Node suites of the pinned planner and role modules, and the
# browser smokes: round-11 P0 and scenarios, round-12 city navigation incl. an empty registry
# (each starts its own server on a free port with a temporary database).
# Prints PASS/FAIL per step and exits non-zero if any step failed. Writes nothing into the repo.
set -uo pipefail
cd "$(dirname "$0")/../../.."
OUT="${1:-$(mktemp -d)}"
mkdir -p "$OUT"
PY="${PYTHON:-python3}"
fail=0
step() {
    local name="$1"; shift
    local log="$OUT/$(echo "$name" | tr ' /' '__').log"
    if "$@" >"$log" 2>&1; then echo "PASS  $name"; else echo "FAIL  $name  (log: $log)"; fail=1; fi
}
echo "R01 checks on $(git rev-parse --short HEAD 2>/dev/null || echo unknown) -> $OUT"
step "pytest" "$PY" -m pytest -q -p no:cacheprovider tests
step "ui.web_check" "$PY" -B -m ui.web_check
for t in plan resilience whatif school_case school_vs_k05; do step "node govtech/$t" node "tests/govtech/$t.cjs"; done
step "node R03 core" node --test tests/civic/R03/core.test.mjs
step "node R04 core+mock" node --test tests/civic/R04/core.test.cjs tests/civic/R04/contract_mock.test.cjs
step "node R01 explore" node --test tests/civic/R01/explore.test.cjs
if node -e "require('playwright')" >/dev/null 2>&1; then
    step "browser P0 flow" node tests/civic/R01/browser/p0_flow.cjs "$OUT/p0"
    step "browser scenarios" node tests/civic/R01/browser/scenarios_smoke.cjs "$OUT/scenarios"
    step "browser r12 city" node tests/civic/R01/browser/r12_city.cjs "$OUT/r12_city"
    step "browser r12 empty registry" node tests/civic/R01/browser/r12_city.cjs "$OUT/r12_empty" --empty
else
    echo "NOT_RUN browser smokes (playwright not installed)"
fi
exit $fail
