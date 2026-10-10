"""Кривая обучения по объёму синтетики: нужно ли генерировать больше LLM-синтетики (логрегрессия, CPU).

Опыты на probe_v2 (300 текстов агента вне шаблонов; только оценка, в обучение и выбор не входит):
  A. вся шаблонная v3 + доля LLM-синтетики llm_v1 в train: 0, 25, 50, 100 %;
  B. доля всего обучающего набора v3 + LLM: 25, 50, 100 % (поровну из обоих корпусов).
Validation — v3 + LLM целиком (как synth_all в experiments.py); выбор гиперпараметров по ней, сетка метода v1.
Подвыборки стратифицированы по категории; для долей < 100 % — несколько seed (разброс от выбора подвыборки).
Из train удалены тексты, совпадающие с оценочными наборами (как experiments.py). Только логрегрессия: трансформер
тем же способом — на ноутбуке (здесь не реализовано).

    python -m ml.civic_classifier_v2.synth_curve --synth-v3 DIR --llm-v1 DIR --probe-v2 DIR     # ≈ 15–20 мин, 4 CPU
Результат: results/synth_curve_probe_v2.json (только числа) → таблица 11 в DIPLOMA_TABLES.md (analysis tables).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2 import metrics as M
from ml.civic_classifier_v2.config import LLM_V1_DIR, PROBE_V2_DIR, RESULTS_DIR, SYNTH_V3_DIR, V1_IN_V2_DIR

LLM_SHARES = (0.0, 0.25, 0.5, 1.0)
TOTAL_SHARES = (0.25, 0.5, 1.0)


def subsample(records: list[dict], share: float, seed: int) -> list[dict]:
    """Стратифицированная по категории подвыборка: в каждой категории round(share · n) текстов."""
    if share >= 1.0:
        return list(records)
    rng = random.Random(seed)
    by: dict[str, list[dict]] = {}
    for r in records:
        by.setdefault(r["label"], []).append(r)
    out = []
    for lab in sorted(by):
        rows = by[lab]
        out += rng.sample(rows, round(share * len(rows)))
    return out


def _point(train: list[dict], val: list[dict], probe: list[dict], seed: int, grid) -> dict:
    from ml.civic_classifier_v2 import logreg
    labs = L.labels()
    idx = {lab: i for i, lab in enumerate(labs)}
    t0 = time.perf_counter()
    model, sel = logreg.fit(train, val, seed, grid=grid)
    pred = list(model.predict([r["text"] for r in probe]))
    y = [idx[r["label"]] for r in probe]
    return {"n_train": len(train), "macro_f1": round(M.macro_f1(y, pred, len(labs)), 4),
            "chosen": sel["chosen"], "seconds": round(time.perf_counter() - t0, 1), "_pred": pred}


def _summary(points: list[dict], y: list[int], k: int) -> dict:
    vals = [p["macro_f1"] for p in points]
    first = points[0]
    ci = M.bootstrap(y, first["_pred"], k)["macro_f1"]
    return {"n_train": first["n_train"], "seeds": len(points), "macro_f1_mean": round(sum(vals) / len(vals), 4),
            "macro_f1_min": min(vals), "macro_f1_max": max(vals), "ci_first_seed": ci,
            "chosen": [p["chosen"] for p in points], "seconds": round(sum(p["seconds"] for p in points), 1)}


def run(v3_train: list[dict], llm_train: list[dict], val: list[dict], probe: list[dict], seeds: list[int],
        grid=None, llm_shares=LLM_SHARES, total_shares=TOTAL_SHARES, log=print) -> dict:
    labs = L.labels()
    idx = {lab: i for i, lab in enumerate(labs)}
    y = [idx[r["label"]] for r in probe]
    k = len(labs)
    res = {"llm_share": {}, "total_share": {}}
    preds = {}
    for share in llm_shares:
        pts = []
        for s in (seeds if 0 < share < 1 else seeds[:1]):
            pts.append(_point(v3_train + subsample(llm_train, share, s), val, probe, seeds[0], grid))
            log(f"A: v3 + {share:.0%} LLM, seed {s}: n={pts[-1]['n_train']} macro-F1 {pts[-1]['macro_f1']}")
        res["llm_share"][str(share)] = _summary(pts, y, k)
        preds[("A", share)] = pts[0]["_pred"]
    for share in total_shares:
        if share >= 1.0 and ("A", 1.0) in preds:  # 100 % от всего — та же точка, что A при 100 % LLM
            res["total_share"][str(share)] = res["llm_share"]["1.0"]
            continue
        pts = []
        for s in seeds:
            pts.append(_point(subsample(v3_train, share, s) + subsample(llm_train, share, s), val, probe, seeds[0], grid))
            log(f"B: {share:.0%} от v3 + LLM, seed {s}: n={pts[-1]['n_train']} macro-F1 {pts[-1]['macro_f1']}")
        res["total_share"][str(share)] = _summary(pts, y, k)
        preds[("B", share)] = pts[0]["_pred"]
    # Парные Δ на одних и тех же текстах probe (первый seed): сколько даёт LLM-синтетика и её половина.
    pairs = []
    if ("A", 1.0) in preds and ("A", 0.0) in preds:
        pairs.append(("v3 + 100 % LLM − одна v3", preds[("A", 1.0)], preds[("A", 0.0)]))
    if ("A", 1.0) in preds and ("A", 0.5) in preds:
        pairs.append(("v3 + 100 % LLM − v3 + 50 % LLM", preds[("A", 1.0)], preds[("A", 0.5)]))
    if ("A", 1.0) in preds and ("B", 0.5) in preds:
        pairs.append(("всё v3 + LLM − половина v3 + LLM", preds[("A", 1.0)], preds[("B", 0.5)]))
    res["paired"] = [{"title": t, "delta": M.paired_delta(y, a, b, k)} for t, a, b in pairs]
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.synth_curve", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synth-v3", default=str(SYNTH_V3_DIR))
    ap.add_argument("--llm-v1", default=str(LLM_V1_DIR))
    ap.add_argument("--v1-in-v2", default=str(V1_IN_V2_DIR))
    ap.add_argument("--probe-v2", default=str(PROBE_V2_DIR))
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--subsample-seeds", type=int, default=3, help="seed подвыборки для долей < 100 %")
    ap.add_argument("--fast", action="store_true", help="без перебора: C=64, без весов (выбор synth_all в LOCAL-4)")
    ap.add_argument("--out", default=str(RESULTS_DIR / "synth_curve_probe_v2.json"))
    args = ap.parse_args(argv)

    v3, _ = D.load_corpus(Path(args.synth_v3), source="synth_v3", evidence="synthetic_template")
    llm, _ = D.load_corpus(Path(args.llm_v1), source="llm_v1", evidence="synthetic_llm")
    probe, _ = D.load_corpus(Path(args.probe_v2), source="probe_v2", evidence="synthetic_agent_written")
    for corpus in (v3, llm):
        D.ensure_splits(corpus, args.seed)
    evals = list(probe) + [r for r in v3 + llm if r["split"] == "test"]
    try:
        v1, _ = D.load_corpus(Path(args.v1_in_v2), source="v1_in_v2", evidence="synthetic_template_v1")
        D.ensure_splits(v1, args.seed)
        evals += [r for r in v1 if r["split"] == "test"]
    except FileNotFoundError:
        pass
    v3_tr, d1 = D.drop_leaks([r for r in v3 if r["split"] == "train"], evals)
    llm_tr, d2 = D.drop_leaks([r for r in llm if r["split"] == "train"], evals)
    val, d3 = D.drop_leaks([r for r in v3 + llm if r["split"] == "val"], evals)
    grid = [{"C": 64.0, "class_weight": None, "keyword_scale": 1.0}] if args.fast else None
    seeds = [args.seed + i for i in range(max(1, args.subsample_seeds))]
    t0 = time.perf_counter()
    res = run(v3_tr, llm_tr, val, probe, seeds, grid)
    res = {"what": "логрегрессия (метод v1) на доле синтетики; оценка — probe_v2 (тексты агента R02, не жителей)",
           "train_pool": {"synth_v3": len(v3_tr), "llm_v1": len(llm_tr), "val": len(val),
                          "dropped_leaks": d1 + d2 + d3},
           "hyperparameters": "fixed C=64, no class weight" if args.fast else "validation, сетка метода v1",
           "subsample_seeds": seeds, "seconds_total": round(time.perf_counter() - t0, 1), **res}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for p in res["paired"]:
        d = p["delta"]
        print(f"{p['title']}: {d['delta']:+.3f} [{d['low']:+.3f}; {d['high']:+.3f}]")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
