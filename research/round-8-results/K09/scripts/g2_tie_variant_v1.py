#!/usr/bin/env python3
"""Post-hoc для v1: G2 с буквальным правилом предрегистрации (ничья по снижению unknown → меньший id, вариант G2id).

Реализованное в v1 правило (−du, cost, id) отличается от текста config v1 («ничьи — меньший id»). Отличие проявляется
только при unknown > 0, т.е. в условии astana_clinic_nobase. Скрипт пересчитывает G2id на основной сетке v1 и пишет
results/g2_tie_variant_v1.json (hit по целям и срезам для G2 из runs.csv и для G2id).
  python3 scripts/g2_tie_variant_v1.py
"""
import csv, json, sys
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09plan import data, suite, experiment as X  # noqa: E402
from k09plan.metric import Problem  # noqa: E402
from k09plan.exact import optimize  # noqa: E402
from k09plan.greedy import greedy_ratio  # noqa: E402
from k09plan.gap import gap  # noqa: E402


def main():
    cfg = json.loads((K / "config/experiment_config.json").read_text(encoding="utf-8"))
    d, sha = data.load_slice(repo=str(K.parents[2]))
    assert sha == data.EXPECTED_DATA_SHA256
    ctxs = {s["id"]: suite.make_context(d, sha, s["city"], s["category"], s["baseline"]) for s in cfg["baselines"]["slices"]}
    g2 = {}
    for r in csv.DictReader(open(K / "results/runs.csv", encoding="utf-8")):
        if r["analysis"] == "main" and r["algorithm"] == "G2":
            g2[(r["scenario_key"], r["objective"])] = int(r["hit"])
    out = {"note": "post-hoc, v1 main grid; G2 — как в runs.csv (−du, cost, id); G2id — (−du, id)", "by_objective": {}, "by_slice": {}}
    cnt = {}
    for an, sid, params, ov in X.scenario_plan(cfg):
        if an != "main":
            continue
        nc, npnt, br, w, ms, rad, seed = params
        sc = suite.make_scenario(ctxs[sid], nc, npnt, br, w, ms, rad, seed, cfg["config_version"])
        key = f"{an}|{sid}|nc{nc}|np{npnt}|br{br}|{w}|ms{ms}|r{rad}|s{seed}"
        pr = Problem(sc["control_points"], ctxs[sid]["sources"], sc["candidates"], rad)
        ex = optimize(pr, sc["budget"], ms, with_pareto=False)
        for o in X.OBJS:
            h = int(gap(o, greedy_ratio(pr, o, sc["budget"], ms, unknown_tie="id")["plan"], ex["objectives"][o])["hit"])
            c = cnt.setdefault((sid, o), [0, 0, 0])
            c[0] += 1; c[1] += g2[(key, o)]; c[2] += h
    for o in X.OBJS:
        n = sum(cnt[(s, o)][0] for s in ctxs); a = sum(cnt[(s, o)][1] for s in ctxs); b = sum(cnt[(s, o)][2] for s in ctxs)
        out["by_objective"][o] = {"n": n, "G2_hits": a, "G2id_hits": b, "G2_rate": round(a / n, 6), "G2id_rate": round(b / n, 6)}
        for s in ctxs:
            n_, a_, b_ = cnt[(s, o)]
            out["by_slice"].setdefault(s, {})[o] = {"n": n_, "G2_hits": a_, "G2id_hits": b_}
    (K / "results/g2_tie_variant_v1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
