#!/usr/bin/env bash
# R11 · полный UX-разбор сборки R01 одной командой (сервер сборки уже поднят, CIVIC_DEMO=1, сотрудник создан).
#   bash tests/civic/R11/review/review_build.sh <порт> <папка> <файл-пароля> [SHA сборки для missing_keys]
# Что делает: сценарий демо 1366/375 × ru/kk (build_shots), непереведённые строки на 5 экранах (ru_kk_same FULL),
# витрина ui-kit на сервере сборки (browser_check --base), ключи модулей вне словаря R11 (missing_keys, если дан SHA),
# кабинет сотрудника в ҚАЗ (staff_kk_check) и кнопки шага 6 демо у «Хан Шатыр» (demo_step6_check).
# Пароль сотрудника читается из файла и нигде не печатается. Итог — <папка>/SUMMARY.txt.
set -u
PORT="$1"; OUT="$2"; PW="$3"; SHA="${4:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../../.." && pwd)"
BASE="http://127.0.0.1:$PORT"
export NODE_PATH="${NODE_PATH:-$(npm root -g)}"
mkdir -p "$OUT"
node "$HERE/build_shots.cjs" "$BASE" "$OUT/shots" r "$PW" > "$OUT/build_shots.log" 2>&1
FULL=1 node "$HERE/ru_kk_same.cjs" "$BASE/" > "$OUT/ru_kk_same.json" 2>&1
node "$ROOT/tests/civic/R11/browser_check.cjs" --base "$BASE" > "$OUT/kit.log" 2>&1
[ -n "$SHA" ] && python3 "$ROOT/tests/civic/R11/tools/missing_keys.py" "$SHA" web/civic web/index.html > "$OUT/missing_keys.txt" 2>&1
mkdir -p "$OUT/staff"
node "$HERE/staff_kk_check.cjs" "$BASE/" "$OUT/staff" "$PW" > "$OUT/staff.log" 2>&1
node "$HERE/demo_step6_check.cjs" "$BASE/" "$PW" "$OUT/step6-1366-kk.png" > "$OUT/step6.log" 2>&1
{
  echo "Сборка: ${SHA:-(SHA не указан)} · $BASE"
  steps=$(grep -c . "$OUT/build_shots.log"); fails=$(grep -c "НЕ ПРОШЛО" "$OUT/build_shots.log")
  echo "Сценарий демо: $((steps - fails)) из $steps шагов"
  grep "НЕ ПРОШЛО" "$OUT/build_shots.log" | cut -c1-200
  python3 - "$OUT/ru_kk_same.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
ok = {"Карта", "РУС", "Алматы", "Алматы ·"}
bad = {k: [x for x in v if x not in ok] for k, v in d.items()}
print("Русские строки в ҚАЗ:", sum(len(v) for v in bad.values()), "·", ", ".join(f"{k} {len(v)}" for k, v in bad.items()))
for k, v in bad.items():
    for x in v[:5]:
        print("   ", k, "—", x[:100])
PY
  echo "Витрина ui-kit (CSP сборки): $(grep -c '^PASS' "$OUT/kit.log") из 4"
  [ -n "$SHA" ] && echo "Ключи вне словаря: $(tail -1 "$OUT/missing_keys.txt")"
  echo "Кабинет сотрудника в ҚАЗ:"; sed 's/^/   /' "$OUT/staff.log"
  echo "Шаг 6 демо («Хан Шатыр»):"; sed 's/^/   /' "$OUT/step6.log"
} > "$OUT/SUMMARY.txt"
cat "$OUT/SUMMARY.txt"
