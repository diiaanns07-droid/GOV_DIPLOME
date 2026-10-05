"""K09-T1 evaluator: поручение ru/kk -> ограничения. Метрики по dataset/ANNOTATION_RULES.md.

Запуск из корня репозитория (Python 3.12 + numpy 2.4.4, нужен engine для регрета):
    python research/round-3-results/K09/scripts/t1_eval.py --systems B1 [B2] --splits dev heldout
LLM не вызывается. Пишет results/<system>_<split>_predictions.jsonl и results/metrics_<systems>.json.
"""
import argparse, hashlib, json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
K = ROOT / "research/round-3-results/K09"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(K / "scripts"))
import engine  # noqa: E402

DATA = engine.load_data()


def canon_items(xs):
    out = set()
    for x in xs or []:
        out.add(("m", x) if isinstance(x, str) else ("md", x.get("measure"), x.get("district")))
    return out


def canon(c):
    c = c or {}
    return {"include": canon_items(c.get("include")), "exclude": set(c.get("exclude") or []), "budget": c.get("budget")}


def slots(c, city):
    s = {("in", city) + i for i in canon(c)["include"]} | {("ex", e) for e in canon(c)["exclude"]}
    if (c or {}).get("budget") is not None:
        s.add(("budget", c["budget"]))
    return s


def districts(c, city):
    return {(city, i[2]) for i in canon(c)["include"] if i[0] == "md"}


def wilson(k, n, z=1.959964):
    if n == 0:
        return [None, None]
    p = k / n; den = 1 + z * z / n; ctr = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(ctr - h, 3), round(ctr + h, 3)]


def opt(constraints):
    r = engine.optimize(top_n=1, constraints=constraints or {}, data=DATA)
    if r.get("errors") or not r.get("results"):
        return None
    return r["results"][0]


def violates(plan, gold):
    dec = plan["decisions"]
    for it in gold.get("include") or []:
        if isinstance(it, str):
            if not any(d["measure"] == it for d in dec): return True
        elif not any(d["measure"] == it["measure"] and d.get("district") == it["district"] for d in dec):
            return True
    if any(d["measure"] in (gold.get("exclude") or []) for d in dec): return True
    if gold.get("budget") is not None and plan["cost"] > gold["budget"]: return True
    return False


def regret(ex, pred):
    g = ex["gold"]
    if not (g["status"] == "ok" and g["city"] == "astana"):
        return {"computed": False, "why": "not astana-ok gold (no optimisation model)"}
    gp = opt(g["constraints"])
    if gp is None:
        return {"computed": False, "why": "gold constraints rejected by engine"}
    if pred["status"] != "ok" or pred.get("city") != "astana":
        return {"computed": False, "why": "prediction not ok/astana"}
    pp = opt(pred["constraints"])
    if pp is None:
        return {"computed": False, "why": "predicted constraints rejected by engine"}
    if violates(pp, g["constraints"]):
        return {"computed": True, "violation": True, "regret": None}
    return {"computed": True, "violation": False, "regret": round(gp["score"] - pp["score"], 4)}


def judge(ex, pred):
    g = ex["gold"]
    city_ok = pred.get("city") == g["city"]
    if g["status"] == "ok":
        po = pred["status"] == "ok"
        cons_ok = po and canon(pred["constraints"]) == canon(g["constraints"])
        gd = districts(g["constraints"], g["city"])
        pd = districts(pred["constraints"], pred.get("city")) if po else set()
        gs, ps = slots(g["constraints"], g["city"]), (slots(pred["constraints"], pred.get("city")) if po else set())
        correct = po and city_ok and cons_ok
        return {"gold_ok": True, "pred_ok": po, "city_ok": city_ok, "constraints_exact": cons_ok,
                "entity_exact": (pd == gd) if gd else None, "tp": len(gs & ps), "fp": len(ps - gs), "fn": len(gs - ps),
                "correct": correct, "confident_error": po and not correct}
    abst = pred["status"] != "ok"
    reason_ok = abst and pred.get("reason") == g["reason"]
    return {"gold_ok": False, "pred_ok": not abst, "city_ok": city_ok, "abstained": abst, "reason_ok": reason_ok,
            "status_ok": pred["status"] == g["status"], "correct": reason_ok and city_ok, "confident_error": not abst}


def summarize(rows):
    n = len(rows); ok = [r for r in rows if r["j"]["gold_ok"]]; no = [r for r in rows if not r["j"]["gold_ok"]]
    tp = sum(r["j"]["tp"] for r in ok); fp = sum(r["j"]["fp"] for r in ok); fn = sum(r["j"]["fn"] for r in ok)
    pr = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
    ent = [r for r in ok if r["j"]["entity_exact"] is not None]
    reg = [r["regret"] for r in rows if r["regret"].get("computed")]

    def frac(k, m):
        return {"k": k, "n": m, "rate": round(k / m, 3) if m else None, "wilson95": wilson(k, m)}
    return {
        "n": n, "gold_ok": len(ok), "gold_non_ok": len(no),
        "fully_correct": frac(sum(r["j"]["correct"] for r in rows), n),
        "city_accuracy": frac(sum(r["j"]["city_ok"] for r in rows), n),
        "entity_exact_on_gold_ok_with_district": frac(sum(r["j"]["entity_exact"] for r in ent), len(ent)),
        "constraints_exact_on_gold_ok": frac(sum(r["j"]["constraints_exact"] for r in ok), len(ok)),
        "slot_precision": round(pr, 3), "slot_recall": round(rc, 3),
        "slot_f1": round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0,
        "abstention_on_gold_non_ok": frac(sum(r["j"]["abstained"] for r in no), len(no)),
        "abstention_reason_correct": frac(sum(r["j"]["reason_ok"] for r in no), len(no)),
        "false_abstention_on_gold_ok": frac(sum(not r["j"]["pred_ok"] for r in ok), len(ok)),
        "confident_error_rate": frac(sum(r["j"]["confident_error"] for r in rows), n),
        "regret": {"computed_for": len(reg), "violations": sum(x["violation"] for x in reg),
                   "values": [x["regret"] for x in reg if not x["violation"]],
                   "not_computed_reasons": sorted({r["regret"]["why"] for r in rows if not r["regret"].get("computed")})},
    }


def mcnemar_exact(a, b):
    """a, b: dict id -> correct(bool). Двусторонний точный тест по несогласованным парам."""
    b01 = sum(1 for i in a if not a[i] and b[i]); b10 = sum(1 for i in a if a[i] and not b[i])
    n = b01 + b10
    if n == 0:
        return {"b_only_correct": b01, "a_only_correct": b10, "p_two_sided": 1.0}
    k = min(b01, b10)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"b_only_correct": b01, "a_only_correct": b10, "p_two_sided": round(p, 4)}


def load_system(name):
    if name == "B1":
        from b1_a13 import B1
        return B1(DATA)
    if name == "B2":
        from b2_parser import B2
        return B2()
    raise SystemExit(f"unknown system {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="+", required=True)
    ap.add_argument("--splits", nargs="+", default=["dev"])
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    ds_path = K / "dataset/t1_dataset.jsonl"
    ds = [json.loads(l) for l in ds_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = {"dataset_sha256": hashlib.sha256(ds_path.read_bytes()).hexdigest(), "splits": a.splits, "systems": {}}
    correct = {}
    for sname in a.systems:
        sysm = load_system(sname)
        out["systems"][sname] = {"impl": getattr(sysm, "name", sname)}
        correct[sname] = {}
        for split in a.splits:
            rows = []
            for ex in [e for e in ds if e["split"] == split]:
                pred = sysm.predict(ex["text"], ex["context_city"])
                j = judge(ex, pred)
                rows.append({"id": ex["id"], "lang": ex["lang"], "class": ex["class"], "text": ex["text"],
                             "context_city": ex["context_city"], "gold": ex["gold"], "pred": pred, "j": j,
                             "regret": regret(ex, pred)})
                correct[sname][ex["id"]] = j["correct"]
            (K / "results").mkdir(exist_ok=True)
            with open(K / f"results/{sname}_{split}_predictions.jsonl", "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            out["systems"][sname][split] = {"all": summarize(rows),
                                            **{lang: summarize([r for r in rows if r["lang"] == lang]) for lang in ("ru", "kk")}}
    if len(a.systems) == 2:
        s1, s2 = a.systems
        for split in a.splits:
            ids = [e["id"] for e in ds if e["split"] == split]
            out[f"mcnemar_{split}_{s1}_vs_{s2}"] = mcnemar_exact({i: correct[s1][i] for i in ids}, {i: correct[s2][i] for i in ids})
    tag = a.tag or "_".join(a.systems) + "_" + "_".join(a.splits)
    (K / f"results/metrics_{tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for sname in a.systems:
        for split in a.splits:
            m = out["systems"][sname][split]["all"]
            print(sname, split, "correct", m["fully_correct"]["k"], "/", m["n"], "city", m["city_accuracy"]["rate"],
                  "cons_exact", m["constraints_exact_on_gold_ok"]["rate"], "abst", m["abstention_on_gold_non_ok"]["rate"],
                  "conf_err", m["confident_error_rate"]["rate"], "regret", m["regret"]["computed_for"], m["regret"]["violations"], m["regret"]["values"])


if __name__ == "__main__":
    main()
