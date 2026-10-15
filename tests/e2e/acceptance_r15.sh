#!/bin/bash
# R10 · раунд 15 · приёмка одной сборки R01 (B1 / B2 / FINAL-5) — все проверки по порядку, браузер — по одному.
#
#   bash tests/e2e/acceptance_r15.sh <папка сборки> <папка отчёта> "<подпись, напр. B1 abcdef12>" [--video] [--quick]
#
# Шаги (код каждого — в <отчёт>/chain.log, вывод — <шаг>.log):
#   pytest   R10_ROOT=<сборка> pytest tests/civic/R10            — точность карты + жёсткие правила API v2
#   api      tests/civic/R10/api_v2.py                            — 46 маршрутов CONTRACT §7 (демо-мир)
#   numbers  tests/civic/R10/consistency.py                       — одни числа во всех разделах (демо-мир)
#   e2e      tests/e2e/demo_flow.cjs --world                      — часть 1 (шаги 1–7 FINAL-4), 1366/375 × ru/kk
#   v2       tests/e2e/demo_flow_v2.cjs                           — сцены 7–9 «Бірге», 1366/1024/375 × ru/kk
#   map      tests/e2e/map_baseline.cjs --repeat 3                — первый значок, загрузка, API
#   ref      tests/e2e/reference_check.cjs --before <FINAL-4>     — эталон A: не хуже FINAL-4 (если есть прогон FINAL-4)
#   video    tests/e2e/demo_video.cjs --world (только с --video)  — ролик ҚАЗ и РУС
# Затем python3 tests/e2e/summary_r15.py <отчёт> → ACCEPTANCE.md и VERDICT.json («можно показывать: да / нет» с причинами).
# --quick — без 1024 в сценах и без эталона (круг на превью роли, ~20 мин).
set -u
W=${1:?папка сборки}; O=${2:?папка отчёта}; L=${3:?подпись}; shift 3
VIDEO=0; QUICK=0
for a in "$@"; do case "$a" in --video) VIDEO=1 ;; --quick) QUICK=1 ;; esac; done
cd "$(dirname "$0")/../.."
export NODE_PATH="${NODE_PATH:-$(npm root -g)}"
REF_HTML=${REF_HTML:-}
REF_BEFORE=${REF_BEFORE:-research/round-15-results/R10/final4-a4937462/ref}
mkdir -p "$O"; : > "$O/chain.log"
echo "label $L" >> "$O/chain.log"; echo "root $W" >> "$O/chain.log"
echo "sha $(git -C "$W" rev-parse --short=8 HEAD 2>/dev/null || echo ?)" >> "$O/chain.log"
step() { local n=$1; shift; local t0=$(date +%s); "$@" > "$O/$n.log" 2>&1; local rc=$?; echo "$n $rc $(( $(date +%s) - t0 ))s" >> "$O/chain.log"; }
step pytest env R10_ROOT="$W" python3 -m pytest -q tests/civic/R10
step api python3 tests/civic/R10/api_v2.py --root "$W" --out "$O/api" --label "$L"
step numbers python3 tests/civic/R10/consistency.py --root "$W" --out "$O/numbers" --label "$L"
step e2e node tests/e2e/demo_flow.cjs --root "$W" --out "$O/e2e" --world
if [ "$QUICK" = 1 ]; then
  step v2 node tests/e2e/demo_flow_v2.cjs --root "$W" --out "$O/v2" --sizes 1366x768,375x812
else
  step v2 node tests/e2e/demo_flow_v2.cjs --root "$W" --out "$O/v2"
fi
step map node tests/e2e/map_baseline.cjs --root "$W" --out "$O/map" --repeat 3 --world
if [ "$QUICK" = 0 ] && [ -n "$REF_HTML" ] && [ -f "$REF_HTML" ]; then
  if [ -d "$REF_BEFORE" ]; then
    step ref node tests/e2e/reference_check.cjs --ref "$REF_HTML" --root "$W" --out "$O/ref" --label "$L" --before "$REF_BEFORE" --world
  else
    step ref node tests/e2e/reference_check.cjs --ref "$REF_HTML" --root "$W" --out "$O/ref" --label "$L" --world
  fi
fi
[ "$VIDEO" = 1 ] && step video node tests/e2e/demo_video.cjs --root "$W" --out "$O/video" --world
python3 tests/e2e/summary_r15.py "$O" > "$O/summary.log" 2>&1
echo DONE >> "$O/chain.log"
exit 0
