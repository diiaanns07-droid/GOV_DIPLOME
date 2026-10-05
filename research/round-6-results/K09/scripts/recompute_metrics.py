"""K09 round-6: независимый пересчёт итоговых чисел по сохранённым predictions.

Не импортирует t1_eval.py: правило «полностью верно» реализовано заново по ANNOTATION_RULES.md (R1–R8):
  эталон ok     -> ответ ok, тот же город, совпадают include/exclude (как множества) и budget;
  эталон не ok  -> ответ не ok, та же причина, тот же город.
Запуск: python3 recompute_metrics.py <каталог results/ с *_predictions.jsonl> [<metrics_*.json ...>]
Печатает JSON: счётчики по системам/наборам, расхождения с полем j.correct и с сохранёнными metrics.
"""
import json, sys
from pathlib import Path


def key_item(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True) if isinstance(x, dict) else x


def same_constraints(a, b):
    a, b = a or {}, b or {}
    return (sorted(map(key_item, a.get("include") or [])) == sorted(map(key_item, b.get("include") or []))
            and sorted(a.get("exclude") or []) == sorted(b.get("exclude") or [])
            and a.get("budget") == b.get("budget"))


def correct(gold, pred):
    if gold["status"] == "ok":
        return pred["status"] == "ok" and pred.get("city") == gold["city"] and same_constraints(pred.get("constraints"), gold["constraints"])
    return pred["status"] != "ok" and pred.get("reason") == gold["reason"] and pred.get("city") == gold["city"]


res_dir = Path(sys.argv[1])
out = {"counts": {}, "row_mismatch_vs_saved_j_correct": [], "metrics_check": []}
for f in sorted(res_dir.glob("*_predictions.jsonl")):
    system, split = f.stem.replace("_predictions", "").split("_", 1)
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    c = {"n": len(rows), "correct": 0, "confident_error": 0, "abstain_on_non_ok": 0, "non_ok": 0, "ids_wrong": []}
    for r in rows:
        ok = correct(r["gold"], r["pred"])
        c["correct"] += ok
        if not ok:
            c["ids_wrong"].append(r["id"])
            if r["pred"]["status"] == "ok":
                c["confident_error"] += 1
        if r["gold"]["status"] != "ok":
            c["non_ok"] += 1
            c["abstain_on_non_ok"] += r["pred"]["status"] != "ok"
        if ok != r["j"]["correct"]:
            out["row_mismatch_vs_saved_j_correct"].append(f"{f.name}:{r['id']}")
    out["counts"][f"{system}/{split}"] = c
for mf in sys.argv[2:]:
    m = json.loads(Path(mf).read_text(encoding="utf-8"))
    for system, per in m["systems"].items():
        for split, block in per.items():
            if not isinstance(block, dict) or "all" not in block:
                if split == "all" or split in ("ru", "kk"):   # external metrics: systems[s] = {all, ru, kk}
                    continue
                continue
            mine = out["counts"].get(f"{system}/{split}")
            saved = block["all"]["fully_correct"]["k"]
            out["metrics_check"].append({"file": Path(mf).name, "system": system, "split": split, "saved_k": saved,
                                         "recomputed_k": mine["correct"] if mine else None, "match": bool(mine) and mine["correct"] == saved})
        if "all" in per:                                            # формат t1_eval_external.py
            mine = out["counts"].get(f"{system}/external")
            saved = per["all"]["fully_correct"]["k"]
            out["metrics_check"].append({"file": Path(mf).name, "system": system, "split": "external", "saved_k": saved,
                                         "recomputed_k": mine["correct"] if mine else None, "match": bool(mine) and mine["correct"] == saved})
print(json.dumps(out, ensure_ascii=False, indent=1))
