#!/bin/bash
# R10 · эталон A «лучше 2ГИС» — полный круг проверки одной сборки (или превью preview_overlay.py), по порядку, без
# параллельной нагрузки (замеры времени чувствительны):
#   1 reference_check (47 элементов эталона, «эталон | было | стало»)   2 response_check (правило 4)
#   3 linear_check (правила 1, 2, 3, 5, 6)   4 motion_check (150–250 мс)   5 demo_flow --audit --glass keep
#   6 map_baseline   7 compare_baseline против baseline_8e67c65 (с --control — прогон 8e67c65 на этой же машине)
#   8 glass_check --no-fps (контраст на стекле)
#
#   bash tests/e2e/reference_round.sh <сборка> <папка> "<подпись>" <REFERENCE.html> [<папка «было»> [<контроль 8e67c65>]]
#
# <REFERENCE.html> — из ветки claude/round-14-package: git show origin/claude/round-14-package:research/round-14/design/REFERENCE.html > ref.html
# <папка «было»> — прогон reference_check на R01 c0270448 (в репозитории: research/round-14-results/R10/reference/r0-c0270448).
# <контроль> — папка с e2e/ и map/ от demo_flow.cjs и map_baseline.cjs на сборке 8e67c65 (на этой же машине).
# Итог — <папка>/chain.log (код каждого шага), отчёты шагов в подпапках; код скрипта 0.
set -u
W=${1:?сборка}; O=${2:?папка}; L=${3:?подпись}; REF=${4:?REFERENCE.html}; BEFORE=${5:-}; CTL=${6:-}
cd "$(dirname "$0")/../.."
export NODE_PATH="${NODE_PATH:-$(npm root -g)}"
mkdir -p "$O"; : > "$O/chain.log"
step() { local n=$1; shift; "$@" > "$O/$n.log" 2>&1; echo "$n $?" >> "$O/chain.log"; }
step ref node tests/e2e/reference_check.cjs --ref "$REF" --root "$W" --out "$O/ref" --label "$L" ${BEFORE:+--before "$BEFORE"}
step resp node tests/e2e/response_check.cjs --root "$W" --out "$O/resp" --label "$L"
step lin node tests/e2e/linear_check.cjs --root "$W" --out "$O/lin" --label "$L"
step motion node tests/e2e/motion_check.cjs --root "$W" --out "$O/motion"
step e2e node tests/e2e/demo_flow.cjs --root "$W" --audit --glass keep --out "$O/reg/e2e"
step map node tests/e2e/map_baseline.cjs --root "$W" --out "$O/reg/map" --repeat 3
step cmp node tests/e2e/compare_baseline.cjs --base research/round-14-results/R10/baseline_8e67c65 --new "$O/reg" ${CTL:+--control "$CTL"}
step glass node tests/e2e/glass_check.cjs --root "$W" --out "$O/glass" --no-fps --sizes 1366x768,1024x768,375x812
echo DONE >> "$O/chain.log"
exit 0
