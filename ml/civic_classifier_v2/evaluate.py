"""Оценка: метрики одного прогона, таблица RESULTS.md из results/experiments.json, оценка сохранённой модели.

    # перегенерировать RESULTS.md из JSON (без пересчёта):
    python -m ml.civic_classifier_v2.evaluate render --results ml/civic_classifier_v2/results/experiments.json
    # оценить сохранённую модель (PyTorch-папку или ONNX) на файле разметки людей:
    python -m ml.civic_classifier_v2.evaluate model --model ml/civic_classifier_v2/artifacts/final \
        --human private/labels_owner.jsonl --out ml/civic_classifier_v2/results/final_on_human.json

Тексты людей в результаты не попадают: только числа, метки и id.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import RESULTS_DIR
from ml.civic_classifier_v2.metrics import bootstrap, ece, report

REGIME_TITLES = {
    "synth_template": "Шаблонная синтетика v3",
    "synth_llm": "LLM-синтетика llm_v1",
    "synth_all": "Синтетика v3 + LLM",
    "human": "Только люди (k-fold)",
    "mix": "Смесь: синтетика + люди",
}
MODEL_TITLES = {
    "heuristic": "Словарная эвристика (не обучается)",
    "logreg": "v1-метод: логрегрессия на n-граммах + словарь",
    "transformer": "v2: трансформер",
    "zeroshot_llm": "LLM zero-shot (без обучения)",
    "v1_shipped": "v1 как есть (6 категорий → v2)",
}
SET_TITLES = {
    "human": "Тексты людей",
    "synth_test_template": "Синтетика v3 — test (невиданные шаблоны)",
    "synth_test_llm": "LLM-синтетика — test",
}


def evaluate_set(records: list[dict], pred: list[int], proba: np.ndarray | None, labels: tuple[str, ...],
                 grouped: bool) -> dict:
    """Отчёт по одному набору: метрики, 95% ДИ, ECE (если есть вероятности), срезы по языку и «сомневался»."""
    index = {lab: i for i, lab in enumerate(labels)}
    y = [index[r["label"]] for r in records]
    groups = [r["group"] for r in records] if grouped else None
    rep = report(y, pred, labels)
    rep["ci"] = bootstrap(y, pred, len(labels), groups)
    if proba is not None and len(proba):
        top = proba[np.arange(len(pred)), np.asarray(pred, dtype=int)]
        rep["ece"] = ece([int(p == t) for p, t in zip(pred, y)], top.tolist())
    slices = {}
    for key in ("lang", "unsure"):
        vals = sorted({str(r.get(key)) for r in records})
        if len(vals) < 2:
            continue
        slices[key] = {}
        for v in vals:
            idx = [i for i, r in enumerate(records) if str(r.get(key)) == v]
            sub = report([y[i] for i in idx], [pred[i] for i in idx], labels)
            slices[key][v] = {"n": len(idx), "accuracy": sub["accuracy"], "macro_f1": sub["macro_f1"]}
    rep["slices"] = slices
    return rep


# ---------- RESULTS.md ----------

def _f(v, digits=3) -> str:
    return "—" if v is None else f"{v:.{digits}f}"


def _cell(entry: dict | None, set_name: str) -> str:
    if not entry:
        return "—"
    if entry.get("status") != "OK":
        return entry.get("status", "—")
    ev = (entry.get("eval") or {}).get(set_name)
    if not ev or ev.get("macro_f1") is None:
        return "—"
    ci = ev["ci"]["macro_f1"]
    return f"**{_f(ev['macro_f1'])}** [{_f(ci['low'])}–{_f(ci['high'])}]"


def render(results: dict) -> str:
    """Markdown для диплома. Числа берутся только из results (без ручного переписывания)."""
    labels = tuple(results.get("labels") or L.labels())
    regimes = [r for r in results.get("regimes", []) if r in REGIME_TITLES]
    runs = results.get("runs", {})
    he = results.get("human_eval", {})
    lines = ["# Классификатор обращений v2 — результаты эксперимента", "",
             "> Файл сгенерирован `python -m ml.civic_classifier_v2.experiments` "
             "(или `evaluate render`). Не править руками — числа берутся из `results/experiments.json`.", ""]
    meta = results.get("meta", {})
    lines += [f"- Дата прогона: {meta.get('created_at', '—')}; git: `{meta.get('git_sha', '—')}`; "
              f"среда: {meta.get('env_note', '—')}",
              f"- Трансформер: `{meta.get('model_name', '—')}`; seed {meta.get('seed', '—')}; "
              f"повторов с разными seed: {meta.get('seeds', 1)}",
              f"- Режим запуска: **{meta.get('mode', 'full')}**" +
              (" — ПРОВЕРКА КОНВЕЙЕРА на крошечной модели, числа не являются результатом" if meta.get("mode") == "smoke" else ""),
              ""]
    if he.get("status") == "EVALUATED":
        lines += [f"**Оценка на текстах людей:** n = {he['n']} (разметка: {he.get('annotators', '—')}), "
                  f"{he.get('protocol', '')}", ""]
    else:
        lines += [f"**Оценка на текстах людей: {he.get('status', 'NOT_EVALUATED')}** — {he.get('reason', '')}", ""]

    # 1. Главная таблица: macro-F1 на людях.
    lines += ["## 1. Macro-F1 на текстах людей (95% ДИ, бутстрэп по текстам)", "",
              "Строки — модель, столбцы — на чём обучали. Все ячейки посчитаны на одном и том же наборе текстов "
              "людей: для режимов с людьми — прогнозы вне фолда (out-of-fold), модель не видела текст при обучении.", ""]
    if he.get("status") == "EVALUATED":
        lines.append("| Модель \\ обучение | " + " | ".join(REGIME_TITLES[r] for r in regimes) + " |")
        lines.append("|---" * (len(regimes) + 1) + "|")
        for m in ("heuristic", "logreg", "transformer"):
            cells = [_cell(runs.get(f"{r}/{m}"), "human") for r in regimes]
            lines.append(f"| {MODEL_TITLES[m]} | " + " | ".join(cells) + " |")
        lines.append("")
        extra = [(m, runs.get(f"none/{m}")) for m in ("zeroshot_llm", "v1_shipped") if runs.get(f"none/{m}")]
        if extra:
            lines += ["Без обучения на наших данных (тот же набор людей):", "",
                      "| Модель | Macro-F1 [95% ДИ] | Accuracy | Покрытие | Примечание |", "|---|---|---|---|---|"]
            for m, e in extra:
                ev = (e.get("eval") or {}).get("human") or {}
                note = e.get("reason", "") if e.get("status") != "OK" else e.get("note", "")
                lines.append(f"| {MODEL_TITLES[m]} | {_cell(e, 'human')} | {_f(ev.get('accuracy'))} | "
                             f"{e.get('coverage', '—')} | {note} |")
            lines.append("")
    else:
        lines += ["NOT_EVALUATED — таблица появится после разметки ≥ 200 текстов людей.", ""]

    # 2. Синтетический test — справочно и «потеря на людях».
    lines += ["## 2. Синтетический test (справочно, НЕ качество на людях)", "",
              "Test синтетики — шаблоны, которых не было в обучении (ДИ — бутстрэп по шаблонам). "
              "«Потеря» = macro-F1 на синтетическом test − macro-F1 на людях (разные наборы, не парная разница).", "",
              "| Режим | Модель | Синтетика v3 test | LLM test | Люди | Потеря на людях |", "|---|---|---|---|---|---|"]
    for r in regimes:
        if not r.startswith("synth"):
            continue
        for m in ("heuristic", "logreg", "transformer"):
            e = runs.get(f"{r}/{m}")
            if not e:
                continue
            ev = e.get("eval") or {}
            syn = [ev.get(s, {}).get("macro_f1") for s in ("synth_test_template", "synth_test_llm")]
            hum = ev.get("human", {}).get("macro_f1")
            own = syn[0] if r != "synth_llm" else syn[1]
            gap = (own - hum) if (own is not None and hum is not None) else None
            lines.append(f"| {REGIME_TITLES[r]} | {MODEL_TITLES[m]} | {_cell(e, 'synth_test_template')} | "
                         f"{_cell(e, 'synth_test_llm')} | {_cell(e, 'human')} | "
                         f"{'—' if gap is None else f'{gap:+.3f}'} |")
    lines.append("")

    # 3. Парные сравнения.
    comps = results.get("comparisons") or []
    if comps:
        lines += ["## 3. Парные сравнения на текстах людей (Δ macro-F1, парный бутстрэп)", "",
                  "| Сравнение | Δ | 95% ДИ | доля ресэмплов Δ>0 | n |", "|---|---|---|---|---|"]
        for c in comps:
            d = c["delta"]
            lines.append(f"| {c['title']} | {d['delta']:+.3f} | [{d['low']:+.3f}; {d['high']:+.3f}] | "
                         f"{d['share_delta_gt_0']} | {c['n']} |")
        lines += ["", "Если 95% ДИ разницы содержит 0 — преимущество не доказано на этом объёме данных.", ""]

    # 4. Лучшая модель: по классам и матрица.
    best_key = results.get("best_on_human")
    if best_key and runs.get(best_key, {}).get("status") == "OK":
        ev = runs[best_key]["eval"]["human"]
        lines += [f"## 4. Лучшая на людях: {best_key} — по категориям", "",
                  "| Категория | Precision | Recall | F1 | Support | Предсказано |", "|---|---|---|---|---|---|"]
        names = L.names("ru")
        for lab in labels:
            v = ev["per_class"].get(lab, {})
            lines.append(f"| {lab} ({names.get(lab, lab)}) | {_f(v.get('precision'))} | {_f(v.get('recall'))} | "
                         f"{_f(v.get('f1'))} | {v.get('support', 0)} | {v.get('predicted', 0)} |")
        cm = ev["confusion"]
        lines += ["", "Матрица ошибок (строки — истина, столбцы — прогноз):", "",
                  "| истина \\ прогноз | " + " | ".join(cm["labels"]) + " |", "|---" * (len(cm["labels"]) + 1) + "|"]
        for lab, row in zip(cm["labels"], cm["rows_true_cols_pred"]):
            lines.append(f"| {lab} | " + " | ".join(str(x) for x in row) + " |")
        if ev.get("slices"):
            lines += ["", "Срезы:", ""]
            for key, sl in ev["slices"].items():
                parts = [f"{k}: n={v['n']}, macro-F1 {_f(v['macro_f1'])}" for k, v in sl.items()]
                lines.append(f"- **{key}** — " + "; ".join(parts))
        if ev.get("ece") is not None:
            lines.append(f"- Калибровка (ECE): {ev['ece']} — score модели не является точной вероятностью.")
        lines.append("")

    # 5. Разброс по seed.
    seeds = {k: v["seed_runs"] for k, v in runs.items() if v.get("seed_runs")}
    if seeds:
        lines += ["## 5. Разброс трансформера по seed (macro-F1 на людях)", "", "| Прогон | по seed | среднее ± sd |",
                  "|---|---|---|"]
        for k, s in seeds.items():
            vals = [x["human_macro_f1"] for x in s if x.get("human_macro_f1") is not None]
            if vals:
                lines.append(f"| {k} | {', '.join(f'{v:.3f}' for v in vals)} | "
                             f"{np.mean(vals):.3f} ± {np.std(vals, ddof=1) if len(vals) > 1 else 0:.3f} |")
        lines.append("")

    # 6. Данные и честность.
    d = results.get("data", {})
    lines += ["## Данные", ""]
    for name, s in d.items():
        if isinstance(s, dict) and "n" in s:
            lines.append(f"- **{name}**: n={s['n']}; по категориям {s.get('by_label')}; языки {s.get('by_lang')}")
        elif isinstance(s, dict) and s.get("status"):
            lines.append(f"- **{name}**: {s['status']} — {s.get('reason', '')}")
    lines += ["", "## Честность", "",
              "- Синтетика (шаблонная v3 и LLM llm_v1) — synthetic; тексты людей — из Google-формы, "
              "обезличены (ml/labeling/import_form.py), в Git не попадают.",
              "- Метрики на синтетическом test не являются качеством на людях.",
              "- Тексты людей не использовались для подбора параметров: эпоха, порог и гиперпараметры логрегрессии "
              "выбираются на validation внутри обучающей части фолда; для режимов без людей — на синтетической validation.",
              "- Словарь эвристики написан до появления текстов людей и после не менялся.",
              "- Разметка людей — один разметчик (владелец), если не указано иное; согласие разметчиков — отчёт R02 "
              "(ml/labeling/agreement.py).", ""]
    notes = results.get("notes") or []
    if notes:
        lines += ["## Замечания прогона", ""] + [f"- {n}" for n in notes] + [""]
    return "\n".join(lines)


def write_results(results: dict, out_dir: Path = RESULTS_DIR, name: str = "experiments") -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / f"{name}.json"
    mpath = out_dir / ("RESULTS.md" if name == "experiments" else f"{name}.md")
    jpath.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    mpath.write_text(render(results), encoding="utf-8")
    return jpath, mpath


# ---------- CLI ----------

def _cmd_render(args) -> int:
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else Path(args.results).with_name("RESULTS.md")
    out.write_text(render(results), encoding="utf-8")
    print(out)
    return 0


def _cmd_model(args) -> int:
    from ml.civic_classifier_v2 import data as D
    from ml.civic_classifier_v2.predict import Classifier

    clf = Classifier.load(Path(args.model))
    recs, rep = D.load_human([Path(p) for p in args.human], not_complaint=args.not_complaint)
    labels = clf.labels
    proba = clf.predict_proba([r["text"] for r in recs])
    pred = [int(i) for i in proba.argmax(axis=1)]
    out = {"model": clf.model_version, "backend": clf.backend, "load_report": rep,
           "data": D.summary(recs), "human": evaluate_set(recs, pred, proba, labels, grouped=False)}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(f"n={len(recs)} macro-F1={out['human']['macro_f1']} accuracy={out['human']['accuracy']} "
          f"ДИ={out['human']['ci']['macro_f1']}")
    print("Предсказано по категориям:", dict(Counter(labels[p] for p in pred)))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.evaluate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="RESULTS.md из experiments.json")
    r.add_argument("--results", default=str(RESULTS_DIR / "experiments.json"))
    r.add_argument("--out")
    m = sub.add_parser("model", help="оценить сохранённую модель на разметке людей")
    m.add_argument("--model", required=True)
    m.add_argument("--human", nargs="+", required=True)
    m.add_argument("--not-complaint", choices=("other", "drop"), default="other")
    m.add_argument("--out")
    args = ap.parse_args(argv)
    return _cmd_render(args) if args.cmd == "render" else _cmd_model(args)


if __name__ == "__main__":
    sys.exit(main())
