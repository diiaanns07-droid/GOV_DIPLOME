"""Подбор порога поиска дублей на парах перефразов R02 и честный отчёт на test.

    python -m ml.civic_dedup.tune                      # n-граммы + понятия (стандартная библиотека)
    python -m ml.civic_dedup.tune --method e5          # после LOCAL-экспорта e5 (numpy, onnxruntime, tokenizers)
    python -m ml.civic_dedup.tune --method all --write-config

Данные: ml/datasets/synth_v3/data/paraphrase_pairs_v3.jsonl (R02): a, b, same_incident, kind, split dev|test.
Протокол (без утечки): параметры (alpha, n-граммы) и порог выбираются ТОЛЬКО на dev; test считается один раз
выбранной настройкой. Правило выбора порога: максимум полноты при точности ≥ 0.90 на dev (ложное «Я тоже»
хуже пропущенного: житель нажмёт «Я тоже», и его другая проблема потеряется); если 0.90 недостижима — максимум F1.

Два сценария оценки:
  geo  — как в приложении: пары kind=same_problem_other_place («та же проблема в другом месте») отсекает
         геофильтр (≤ 200 м / та же цель), поэтому в текстовую оценку не входят. Допущение: разные названные
         места дальше 200 м друг от друга — в синтетике R02 у пар нет координат;
  text — только текст, все пары (нижняя граница: если точка жалобы неточная).
Интервалы — бутстрэп по парам (1000 повторов, seed 20261011), 95 %.
У смешанного метода два режима: пары, где понятия есть в обоих текстах, решает общий порог; пары
«только текст» — порог чистого метода n-грамм (alpha = 1), подобранный на dev до смешанного.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ml.civic_dedup import config as C
from ml.civic_dedup.scorers import NgramConceptScorer

TARGET_PRECISION = 0.90
SEED = 20261011
GEO_EXCLUDED_KIND = "same_problem_other_place"
THRESHOLDS = [round(0.05 + 0.01 * i, 2) for i in range(91)]  # 0.05 … 0.95


def load_pairs(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                rows.append({"a": r["a"], "b": r["b"], "y": bool(r["same_incident"]), "kind": r["kind"],
                             "split": r["split"], "lang": f"{r.get('lang_a', '?')}-{r.get('lang_b', '?')}"})
    if not rows:
        raise ValueError(f"{path}: нет пар")
    return rows


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def score_pairs(scorer, pairs: list[dict]) -> list[tuple[float, float | None]]:
    """[(оценка, свой порог пары или None)]. Свой порог — режим «только текст» у n-грамм (scorers.py)."""
    texts = sorted({p["a"] for p in pairs} | {p["b"] for p in pairs})
    feats = dict(zip(texts, scorer.encode_many(texts)))
    out = []
    for p in pairs:
        a, b = feats[p["a"]], feats[p["b"]]
        fixed = None
        if getattr(scorer, "text_only_threshold", None) is not None and scorer.alpha < 1.0 and scorer.text_only(a, b):
            fixed = scorer.text_only_threshold
        out.append((scorer.score(a, b), fixed))
    return out


def confusion(ys: list[bool], scores: list[tuple[float, float | None]], thr: float) -> dict:
    tp = fp = fn = tn = 0
    for y, (s, fixed) in zip(ys, scores):
        pred = s >= (thr if fixed is None else fixed)
        if pred and y:
            tp += 1
        elif pred:
            fp += 1
        elif y:
            fn += 1
        else:
            tn += 1
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


def subset(pairs, scores, split: str, scenario: str):
    idx = [i for i, p in enumerate(pairs)
           if p["split"] == split and not (scenario == "geo" and p["kind"] == GEO_EXCLUDED_KIND)]
    return [pairs[i] for i in idx], [scores[i] for i in idx]


def choose_threshold(ys, scores) -> tuple[float, str]:
    best = None
    for thr in THRESHOLDS:
        c = confusion(ys, scores, thr)
        if c["precision"] >= TARGET_PRECISION and c["tp"] > 0:
            key = (c["recall"], c["precision"], -thr)
            if best is None or key > best[0]:
                best = (key, thr)
    if best is not None:
        return best[1], f"max recall at precision >= {TARGET_PRECISION}"
    thr = max(THRESHOLDS, key=lambda t: (confusion(ys, scores, t)["f1"], -t))
    return thr, f"precision {TARGET_PRECISION} unreachable on dev: max F1"


def bootstrap(ys, scores, thr: float, n: int = 1000) -> dict:
    rng = random.Random(SEED)
    idx = list(range(len(ys)))
    ps, rs = [], []
    for _ in range(n):
        sample = [rng.choice(idx) for _ in idx]
        c = confusion([ys[i] for i in sample], [scores[i] for i in sample], thr)
        ps.append(c["precision"])
        rs.append(c["recall"])
    ps.sort()
    rs.sort()
    lo, hi = int(0.025 * n), int(0.975 * n) - 1
    return {"precision_ci95": [ps[lo], ps[hi]], "recall_ci95": [rs[lo], rs[hi]]}


def by_kind(pairs, scores, thr: float) -> dict:
    """Для положительных видов — доля найденных (recall), для отрицательных — доля верно отвергнутых."""
    out = {}
    for kind in sorted({p["kind"] for p in pairs}):
        sel = [(p["y"], s, f) for p, (s, f) in zip(pairs, scores) if p["kind"] == kind]
        hit = sum(1 for y, s, f in sel if (s >= (thr if f is None else f)) == y)
        out[kind] = {"n": len(sel), "correct": hit, "rate": round(hit / len(sel), 4),
                     "meaning": "recall" if sel[0][0] else "rejected_correctly",
                     "mean_score": round(sum(s for _y, s, _f in sel) / len(sel), 4),
                     "text_only_share": round(sum(1 for *_x, f in sel if f is not None) / len(sel), 4)}
    return out


def text_only_thresholds(pairs: list[dict]) -> dict[tuple[int, int], float]:
    """Порог чистого метода n-грамм (alpha = 1) на dev — он же порог режима «только текст» смешанного метода."""
    out = {}
    for ng in ((3, 5), (2, 4)):
        scores = score_pairs(NgramConceptScorer(1.0, ng), pairs)
        dev_p, dev_s = subset(pairs, scores, "dev", "geo")
        out[ng] = choose_threshold([p["y"] for p in dev_p], dev_s)[0]
    return out


def candidates(method: str, pairs: list[dict]) -> list[tuple[str, dict, object]]:
    """(метод, параметры, оценщик) — сетка настроек, выбор между ними тоже только по dev."""
    out = []
    if method in ("ngram", "all"):
        text_thr = text_only_thresholds(pairs)
        for alpha in (1.0, 0.7, 0.6, 0.5, 0.4, 0.3):
            for ng in ((3, 5), (2, 4)):
                params = {"alpha": alpha, "ngram_range": list(ng)}
                t_text = None if alpha >= 1.0 else text_thr[ng]
                if t_text is not None:
                    params["text_only_threshold"] = t_text
                out.append((C.FALLBACK_METHOD, params, NgramConceptScorer(alpha, ng, t_text)))
    if method in ("e5", "all"):
        from ml.civic_dedup.e5 import E5Scorer
        base = E5Scorer.load(C.E5_DIR)
        for alpha in (1.0, 0.8, 0.6):
            sc = E5Scorer(base.session, base.tokenizer, meta=base.meta, alpha=alpha)
            out.append(("e5-onnx", {"alpha": alpha}, sc))
    return out


def evaluate(method: str, pairs_path: Path) -> dict:
    pairs = load_pairs(pairs_path)
    report = {"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "pairs_file": str(pairs_path.relative_to(C.REPO_ROOT)) if pairs_path.is_relative_to(C.REPO_ROOT)
              else str(pairs_path), "pairs_sha256": sha256_file(pairs_path),
              "counts": {s: sum(1 for p in pairs if p["split"] == s) for s in ("dev", "test")},
              "evidence": "synthetic (R02 synth_v3 paraphrase pairs); real resident texts NOT_EVALUATED",
              "selection_rule": f"dev, scenario geo: max recall at precision >= {TARGET_PRECISION}",
              "methods": {}}
    for name, params, scorer in candidates(method, pairs):
        t0 = time.perf_counter()
        scores = score_pairs(scorer, pairs)
        elapsed = time.perf_counter() - t0
        dev_p, dev_s = subset(pairs, scores, "dev", "geo")
        thr, rule = choose_threshold([p["y"] for p in dev_p], dev_s)
        dev = confusion([p["y"] for p in dev_p], dev_s, thr)
        entry = {"params": params, "threshold": thr, "rule": rule, "dev_geo": dev,
                 "version": scorer.version, "scoring_seconds": round(elapsed, 2)}
        best = report["methods"].get(name)
        if best is None or (dev["recall"], dev["precision"]) > (best["dev_geo"]["recall"], best["dev_geo"]["precision"]):
            entry["_scores"] = scores
            report["methods"][name] = entry
        report.setdefault("grid", []).append({"method": name, "params": params, "threshold": thr, "dev_geo": dev})
    # test — один раз, только выбранная настройка каждого метода
    for name, entry in report["methods"].items():
        scores = entry.pop("_scores")
        thr = entry["threshold"]
        for scenario in ("geo", "text"):
            tp, ts = subset(pairs, scores, "test", scenario)
            ys = [p["y"] for p in tp]
            entry[f"test_{scenario}"] = {**confusion(ys, ts, thr), **bootstrap(ys, ts, thr)}
        test_pairs = [p for p in pairs if p["split"] == "test"]
        test_scores = [sf for p, sf in zip(pairs, scores) if p["split"] == "test"]
        entry["test_by_kind"] = by_kind(test_pairs, test_scores, thr)
    return report


def meets_target(entry: dict) -> bool:
    return entry["dev_geo"]["precision"] >= TARGET_PRECISION and entry["dev_geo"]["tp"] > 0


def update_config(report: dict) -> dict:
    """Пороги -> dedup_config.json. Метод, не достигший точности 0.90 на dev, выключается (threshold = null).
    Порядок prefer — по полноте на dev; запасной путь n-грамм всегда остаётся в списке последним средством."""
    conf = C.load_config()
    for name, entry in report["methods"].items():
        ok = meets_target(entry)
        conf["methods"].setdefault(name, {}).update({
            "text_only_threshold": None, **entry["params"], "threshold": entry["threshold"] if ok else None,
            "status": "enabled" if ok else f"disabled: precision < {TARGET_PRECISION} on dev",
            "tuned_on": "dev (R02 paraphrase_pairs_v3)",
            "pairs_sha256": report["pairs_sha256"], "tuned_at": report["generated_at"],
            "dev_geo": {k: entry["dev_geo"][k] for k in ("precision", "recall", "f1")},
            "test_geo": {k: entry["test_geo"][k] for k in ("precision", "recall", "f1")}})
    ranked = sorted((name for name, m in conf["methods"].items() if m.get("threshold") is not None),
                    key=lambda name: -(conf["methods"][name].get("dev_geo") or {}).get("recall", 0.0))
    if C.FALLBACK_METHOD not in ranked:
        ranked.append(C.FALLBACK_METHOD)
    conf["prefer"] = ranked
    C.save_config(conf)
    return conf


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_dedup.tune")
    ap.add_argument("--method", choices=("ngram", "e5", "all"), default="ngram")
    ap.add_argument("--pairs", type=Path, default=C.PAIRS_PATH)
    ap.add_argument("--out", type=Path, default=None, help="JSON отчёта (по умолчанию results/dedup_eval_<method>.json)")
    ap.add_argument("--write-config", action="store_true", help="записать пороги в dedup_config.json")
    args = ap.parse_args(argv)
    if not args.pairs.exists():
        print(f"нет файла пар: {args.pairs} (ветка R02, ml/datasets/synth_v3/data/)", file=sys.stderr)
        return 2
    report = evaluate(args.method, args.pairs)
    out = args.out or (C.RESULTS_DIR / f"dedup_eval_{args.method}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, e in report["methods"].items():
        print(f"{name} {e['params']} thr={e['threshold']} dev_geo P={e['dev_geo']['precision']} "
              f"R={e['dev_geo']['recall']} | test_geo P={e['test_geo']['precision']} R={e['test_geo']['recall']} "
              f"F1={e['test_geo']['f1']} | test_text P={e['test_text']['precision']} R={e['test_text']['recall']}")
    if args.write_config:
        update_config(report)
        print(f"пороги записаны в {C.CONFIG_PATH}")
    print(f"отчёт: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
