#!/usr/bin/env bash
# K01 round 8: run every check against a BUILD SHA (extracted from git objects, not the working tree).
#   bash research/round-8-results/K01/run_all.sh [BUILD_SHA]      (from a GOV_DIPLOME clone after git fetch of the BUILD branch)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"
SHA="${1:-a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
APP="$(cd "$ROOT" && python3 research/round-5-results/K01/extract_build.py --sha "$SHA" --dest "$TMP")" || exit 2
rc=0; run() { echo "== $*"; "$@" || rc=1; }
cd "$HERE"
run node test_planv2.cjs --app-root "$APP"
run node test_state.cjs --app-root "$APP"
run node test_digest.cjs
run env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_planv2_ref
echo "== CLI smoke"
node planv2_cli.cjs validate fixtures/synthetic/shy_valid_basic.json --city shymkent --app-root "$APP" >/dev/null || rc=1
node planv2_cli.cjs validate fixtures/synthetic/shy_invalid_nan.json --city shymkent --app-root "$APP" >/dev/null; [ $? -eq 1 ] || rc=1
echo "target BUILD $SHA -> $([ $rc -eq 0 ] && echo ALL PASS || echo FAILURES)"
exit $rc
