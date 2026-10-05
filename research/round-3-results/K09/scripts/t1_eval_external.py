"""K09-T1: прогон замороженных B1/B2 на внешнем наборе external_v1 (без изменения t1_eval.py и b2_parser.py).

Запуск из корня репозитория (Python 3.12 + numpy 2.4.4):
    python research/round-3-results/K09/scripts/t1_eval_external.py
"""
import hashlib, json, sys
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K / "scripts"))
import t1_eval as T  # noqa: E402

ds_path = K / "dataset/external_v1/t1_external.jsonl"
ds = [json.loads(l) for l in ds_path.read_text(encoding="utf-8").splitlines() if l.strip()]
out = {"dataset": str(ds_path.relative_to(K)), "dataset_sha256": hashlib.sha256(ds_path.read_bytes()).hexdigest(),
       "b2_sha256": hashlib.sha256((K / "scripts/b2_parser.py").read_bytes()).hexdigest(), "systems": {}}
correct = {}
for name in ("B1", "B2"):
    sysm = T.load_system(name)
    rows = []
    for ex in ds:
        pred = sysm.predict(ex["text"], ex["context_city"])
        j = T.judge(ex, pred)
        rows.append({"id": ex["id"], "lang": ex["lang"], "class": ex["class"], "text": ex["text"],
                     "context_city": ex["context_city"], "gold": ex["gold"], "pred": pred, "j": j, "regret": T.regret(ex, pred)})
    correct[name] = {r["id"]: r["j"]["correct"] for r in rows}
    with open(K / f"results/{name}_external_predictions.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    out["systems"][name] = {"all": T.summarize(rows), **{lg: T.summarize([r for r in rows if r["lang"] == lg]) for lg in ("ru", "kk")}}
out["mcnemar_external_B1_vs_B2"] = T.mcnemar_exact(correct["B1"], correct["B2"])
(K / "results/metrics_B1_vs_B2_external.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for name in ("B1", "B2"):
    for part in ("all", "ru", "kk"):
        m = out["systems"][name][part]
        print(name, part, "n", m["n"], "correct", m["fully_correct"]["k"], m["fully_correct"]["wilson95"],
              "city", m["city_accuracy"]["rate"], "cons", m["constraints_exact_on_gold_ok"]["k"], "/", m["constraints_exact_on_gold_ok"]["n"],
              "abst", m["abstention_on_gold_non_ok"]["k"], "/", m["abstention_on_gold_non_ok"]["n"],
              "reason", m["abstention_reason_correct"]["k"], "false_abst", m["false_abstention_on_gold_ok"]["k"],
              "conf_err", m["confident_error_rate"]["k"], "regret", m["regret"]["computed_for"], "viol", m["regret"]["violations"])
print(out["mcnemar_external_B1_vs_B2"])
