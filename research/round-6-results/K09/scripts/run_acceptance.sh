#!/usr/bin/env bash
# K09 round-6: приёмка воспроизводимости результата T1 на новой сборке.
# Использование (из корня клона GOV_DIPLOME, нужен Python 3.12 + numpy 2.4.4 + jsonschema 4.26.0 в $PY):
#   PY=/path/to/venv/bin/python bash research/round-6-results/K09/scripts/run_acceptance.sh <рабочая_папка> <папка_выходов>
# Ничего не меняет в репозитории: собирает дерево сборки через git archive во временную папку,
# накладывает замороженные инструменты K09 из test_source_sha и сравнивает выходы побайтно.
set -euo pipefail
TARGET=064ed25368341edaa50289bc29e21dda7bdd9440       # claude/beautiful-clarke-sbzomj
SOURCE=e4ac24fcdca2701f6fd674e59cbd485f0de42ece       # claude/save-work-handoff-qho6eq (K09 round-3)
W="${1:?рабочая папка}"; OUT="${2:?папка выходов}"; PY="${PY:?переменная PY с python 3.12}"
REPO="$(git rev-parse --show-toplevel)"
HERE="$REPO/research/round-6-results/K09/scripts"
rm -rf "$W"; mkdir -p "$W" "$OUT"
git -C "$REPO" archive "$TARGET" | tar -x -C "$W"
git -C "$REPO" archive "$SOURCE" research/round-3-results/K09 | tar -x -C "$W"
K="$W/research/round-3-results/K09"
{
echo "## I1 target tree: product code vs SOURCE (engine/agent/data/ui/web/tests/app.py/check.py)"
git -C "$REPO" diff --stat "$SOURCE" "$TARGET" -- engine agent data ui web tests app.py check.py | tail -1 || true
echo "(пусто = идентично)"
echo "## I2 frozen hashes"
(cd "$K" && grep -E '^[0-9a-f]{64}' results/FREEZE_B2_before_heldout.txt | sha256sum -c -)
(cd "$K/dataset" && sha256sum -c DATASET_SHA256.txt)
"$PY" - "$K" <<'PYEOF'
import hashlib, json, sys
K = sys.argv[1]
a = json.load(open(f"{K}/dataset/external_v1/agreement.json"))
for key, f in [("t1_external_sha256", "dataset/external_v1/t1_external.jsonl"), ("raw_sha256", "dataset/external_v1/raw_workflow_output.json")]:
    h = hashlib.sha256(open(f"{K}/{f}", "rb").read()).hexdigest(); print(f"{f}: {'OK' if h == a[key] else 'MISMATCH'}")
PYEOF
} > "$OUT/I1_I2_hashes.txt" 2>&1
cp -a "$K/results" "$W/saved_results"
python3 "$HERE/recompute_metrics.py" "$W/saved_results" "$W"/saved_results/metrics_*.json > "$OUT/I3_recompute_from_saved.json"
( cd "$W"
  "$PY" research/round-3-results/K09/scripts/t1_eval.py --systems B1 --splits dev heldout --tag B1_dev_heldout
  "$PY" research/round-3-results/K09/scripts/t1_eval.py --systems B2 --splits dev --tag B2_dev_frozen
  "$PY" research/round-3-results/K09/scripts/t1_eval.py --systems B1 B2 --splits heldout --tag B1_vs_B2_heldout
  "$PY" research/round-3-results/K09/scripts/ingest_external.py > /dev/null
  "$PY" research/round-3-results/K09/scripts/t1_eval_external.py ) > "$OUT/I4_rerun_stdout.txt" 2>&1
{
echo "## I4 frozen inference rerun on TARGET tree vs saved outputs of SOURCE"
for f in "$W"/saved_results/*; do b=$(basename "$f"); cmp -s "$f" "$K/results/$b" && echo "IDENTICAL results/$b" || echo "DIFFERENT results/$b"; done
for f in t1_external.jsonl agreement.json disagreements.json; do
  cmp -s "$K/dataset/external_v1/$f" <(git -C "$REPO" show "$SOURCE:research/round-3-results/K09/dataset/external_v1/$f") && echo "IDENTICAL external_v1/$f" || echo "DIFFERENT external_v1/$f"; done
} > "$OUT/I4_rerun_compare.txt"
{
echo "## I6 parser wiring in TARGET (prototype, non-input files): K09 code / NL instructions / optimize / network"
git -C "$REPO" grep -n -I -E "b2_parser|t1_eval|b1_a13|baseline_parse|t1_dataset|t1_external" "$TARGET" -- prototypes web ui app.py agent engine || echo "no K09 code references"
git -C "$REPO" grep -n -I -i -E "поручен|instruction|constraints|/api/optimize|optimize\(|<textarea|fetch\(|XMLHttpRequest" "$TARGET" -- prototypes/city-evidence ':(exclude)prototypes/city-evidence/inputs' || echo "no NL-instruction/optimize/network hooks in prototype"
} > "$OUT/I6_wiring.txt" 2>&1
"$PY" - "$K" > "$OUT/repro_new_findings.txt" <<'PYEOF'
import json, sys
sys.path.insert(0, f"{sys.argv[1]}/scripts")
from b2_parser import B2
b = B2()
for text, ctx in [("ЛРТ из плана уберите", "shymkent"), ("Модернизировать тепловые и водопроводные сети в Каратауском районе.", None)]:
    print(repr(text), ctx, "->", json.dumps(b.predict(text, ctx), ensure_ascii=False))
PYEOF
echo "done: $OUT"
