#!/usr/bin/env bash
# K01 round 9: all checks against a BUILD SHA extracted from git objects.
#   bash research/round-9-results/K01/run_all.sh [BUILD_SHA]     (after git fetch origin claude/beautiful-clarke-sbzomj)
# exit 0: no defect; 1: defect found; resilience integration NOT_RUN is reported, not counted as PASS.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"
SHA="${1:-d865dd4a124291e10dd0b7bb1d9eada20d34c268}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
APP="$(cd "$ROOT" && python3 research/round-5-results/K01/extract_build.py --sha "$SHA" --dest "$TMP")" || exit 2
cd "$HERE"; rc=0
run() { echo "== $*"; "$@"; local c=$?; [ $c -ne 0 ] && rc=1; return 0; }
run node test_compat.cjs --app-root "$APP"
run env NODE_PATH="$(npm root -g)" node browser_atomic.cjs --app-root "$APP"
run node test_resilience_contract.cjs --app-root "$APP"
echo "== node test_public_api.cjs (CORE_SPEC r9 public API validation)"; node test_public_api.cjs --app-root "$APP" || rc=1
echo "== node test_build_r9.cjs (BUILD resilience.js)"; node test_build_r9.cjs --app-root "$APP" --label "BUILD ${SHA:0:7}"; c=$?
[ $c -eq 3 ] && echo "RESILIENCE INTEGRATION: NOT_RUN" || { [ $c -ne 0 ] && rc=1; }
echo "target BUILD $SHA -> $([ $rc -eq 0 ] && echo 'no defect found' || echo 'DEFECTS/FAILURES')"
exit $rc
