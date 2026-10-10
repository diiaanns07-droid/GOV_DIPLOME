"""Аудит меток LLM-синтетики llm_v1: какие тексты, возможно, размечены не той категорией.

Метка в llm_v1 — категория, которую попросили у LLM (R02 llm_synth.py); человек её не проверял. Если LLM написала
текст про другую тему, в обучение попадает шум. Здесь — оценка этого шума без людей, в духе confident learning:
  1. логрегрессия (метод v1, гиперпараметры как у synth_all в LOCAL-4) обучается на k-1 фолдах llm_v1 и
     предсказывает k-й (out-of-fold): у каждого текста есть вероятность «его» метки от модели, которая его не видела;
  2. кандидат = p(своей метки) < --low и другая категория получила ≥ --high;
  3. «согласие с v3» — то же мнение у модели, обученной только на шаблонной v3 (другой генератор, другой автор).
Это КАНДИДАТЫ на проверку человеком, не доказанные ошибки: часть — честно спорные тексты (несколько тем).

    python -m ml.civic_classifier_v2.label_audit --llm-v1 DIR --synth-v3 DIR
Результат: results/LLM_LABEL_AUDIT.md (+ .json с id кандидатов). Тексты llm_v1 синтетические — их можно показывать.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import LLM_V1_DIR, RESULTS_DIR, SYNTH_V3_DIR

# Гиперпараметры логрегрессии, выбранные по validation в LOCAL-4 для synth_all (results/experiments.json).
HYPER = {"C": 64.0, "class_weight": None, "keyword_scale": 1.0}


def oof_proba(records: list[dict], k: int, seed: int) -> np.ndarray:
    """Вероятности out-of-fold [n, 12] логрегрессией с фиксированными гиперпараметрами."""
    from ml.civic_classifier_v2 import logreg
    labs = L.labels()
    out = np.zeros((len(records), len(labs)))
    for test_idx in D.stratified_kfold(records, k, seed):
        test = set(test_idx)
        train = [r for i, r in enumerate(records) if i not in test]
        model, _ = logreg.fit(train, [], seed, grid=[HYPER], labels=labs)
        out[test_idx] = model.predict_proba([records[i]["text"] for i in test_idx])
    return out


def audit(records: list[dict], proba: np.ndarray, proba_v3: np.ndarray | None, low: float, high: float) -> dict:
    labs = L.labels()
    idx = {lab: i for i, lab in enumerate(labs)}
    cands = []
    for i, r in enumerate(records):
        own = float(proba[i, idx[r["label"]]])
        best = int(proba[i].argmax())
        if own < low and labs[best] != r["label"] and proba[i, best] >= high:
            row = {"id": r["id"], "label": r["label"], "suggested": labs[best], "p_label": round(own, 3),
                   "p_suggested": round(float(proba[i, best]), 3), "split": r["split"], "lang": r["lang"],
                   "style": r.get("style", ""), "text": r["text"]}
            if proba_v3 is not None:
                row["v3_agrees"] = labs[int(proba_v3[i].argmax())] == labs[best]
            cands.append(row)
    by_label = Counter(c["label"] for c in cands)
    total = Counter(r["label"] for r in records)
    pairs = Counter((c["label"], c["suggested"]) for c in cands)
    return {"n": len(records), "candidates": len(cands), "share": round(len(cands) / max(1, len(records)), 4),
            "v3_agrees": sum(1 for c in cands if c.get("v3_agrees")),
            "by_label": {lab: {"candidates": by_label.get(lab, 0), "n": total.get(lab, 0),
                               "share": round(by_label.get(lab, 0) / max(1, total.get(lab, 0)), 3)} for lab in labs},
            "top_pairs": [{"label": a, "suggested": b, "n": n} for (a, b), n in pairs.most_common(12)],
            "items": sorted(cands, key=lambda c: (c["label"], c["p_label"]))}


def render(res: dict, args) -> str:
    names = L.names("ru")
    out = ["# Аудит меток LLM-синтетики llm_v1 (R03)", "",
           "> Сгенерировано `python -m ml.civic_classifier_v2.label_audit`. Метки llm_v1 — категория из запроса к LLM, "
           "людьми не проверены. Ниже — **кандидаты** на неверную метку по мнению моделей, а не доказанные ошибки.", "",
           f"- Текстов: {res['n']}; кандидатов: **{res['candidates']} ({res['share']:.1%})**; из них модель на шаблонной "
           f"v3 (другой генератор) согласна с предложенной категорией: {res['v3_agrees']}.",
           f"- Правило: out-of-fold p(своей метки) < {args.low} и другая категория ≥ {args.high}; логрегрессия "
           f"{json.dumps(HYPER)}, {args.folds}-fold, seed {args.seed}.", "",
           "## По категориям", "", "| Категория (метка LLM) | Кандидатов | Текстов | Доля |", "|---|---|---|---|"]
    for lab, v in res["by_label"].items():
        out.append(f"| {names[lab]} ({lab}) | {v['candidates']} | {v['n']} | {v['share']:.1%} |")
    out += ["", "## Частые пары «метка LLM → что видит модель»", "", "| Метка | Предлагает модель | Текстов |", "|---|---|---|"]
    for p in res["top_pairs"]:
        out.append(f"| {names[p['label']]} | {names[p['suggested']]} | {p['n']} |")
    out += ["", f"## Примеры (до {args.examples} на категорию; v3 — согласна ли модель на шаблонной v3)", "",
            "| id | Текст (до 150 знаков) | Метка | Модель | p(метки) | v3 |", "|---|---|---|---|---|---|"]
    shown = Counter()
    for c in res["items"]:
        if shown[c["label"]] >= args.examples:
            continue
        shown[c["label"]] += 1
        t = c["text"].replace("|", "/").replace("\n", " ")
        t = t if len(t) <= 150 else t[:147] + "…"
        out.append(f"| {c['id']} | {t} | {c['label']} | {c['suggested']} | {c['p_label']} | "
                   f"{'да' if c.get('v3_agrees') else 'нет'} |")
    out += ["", "Как читать: часть кандидатов — правила трудных случаев, где метка LLM верна по гайду, а ошибается модель "
            "(например, «нет света на остановке» → lighting, модель говорит transport). Настоящий шум чаще в «Другом»: "
            "по запросу «другое» LLM пишет жалобы с конкретной проблемой, а по гайду вопрос с проблемой относится к теме "
            "проблемы.", "",
            "Что делать: R02/владелец просматривают кандидатов (особенно с «v3: да»); подтверждённые ошибки исправить "
            "в llm_v1 или исключить, затем повторить experiments (RUN.txt шаг 6) — так измеряется вклад шума меток.", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.label_audit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm-v1", default=str(LLM_V1_DIR))
    ap.add_argument("--synth-v3", default=str(SYNTH_V3_DIR), help="для «второго мнения» модели на шаблонной v3")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--low", type=float, default=0.2)
    ap.add_argument("--high", type=float, default=0.6)
    ap.add_argument("--examples", type=int, default=6)
    ap.add_argument("--out", default=str(RESULTS_DIR / "LLM_LABEL_AUDIT.md"))
    args = ap.parse_args(argv)

    from ml.civic_classifier_v2 import logreg
    llm, _ = D.load_corpus(Path(args.llm_v1), source="llm_v1", evidence="synthetic_llm")
    proba = oof_proba(llm, args.folds, args.seed)
    proba_v3 = None
    try:
        v3, _ = D.load_corpus(Path(args.synth_v3), source="synth_v3", evidence="synthetic_template")
        D.ensure_splits(v3, args.seed)
        tr = [r for r in v3 if r["split"] in ("train", "val")]
        model, _ = logreg.fit(tr, [], args.seed, grid=[HYPER], labels=L.labels())
        proba_v3 = model.predict_proba([r["text"] for r in llm])
    except FileNotFoundError:
        pass
    res = audit(llm, proba, proba_v3, args.low, args.high)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(res, args), encoding="utf-8")
    meta = {k: v for k, v in res.items() if k != "items"}
    meta["candidate_ids"] = [c["id"] for c in res["items"]]
    meta["rule"] = {"low": args.low, "high": args.high, "folds": args.folds, "seed": args.seed, "logreg": HYPER}
    out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{out}: кандидатов {res['candidates']} из {res['n']} ({res['share']:.1%}); v3 согласна: {res['v3_agrees']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
