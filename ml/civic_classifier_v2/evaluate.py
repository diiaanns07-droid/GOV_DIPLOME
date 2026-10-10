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
    "synth_v1": "Синтетика v1→v2 (R08)",
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
    "synth_test_v1": "Синтетика v1→v2 — test",
    "probe_v2": "probe_v2 — вне шаблонов (300 текстов агента R02)",
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
    for key in ("lang", "style", "hard", "unsure"):
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
              f"повторов с разными seed: {meta.get('seeds', 1)}"
              + (f"; **доля текстов людей в обучении: {meta['human_fraction']}** (кривая обучения)"
                 if meta.get("human_fraction", 1.0) < 1.0 else ""),
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
    else:
        lines += ["NOT_EVALUATED — таблица появится после разметки ≥ 200 текстов людей.", ""]

    # 1б. Независимый тест вне шаблонов — probe_v2.
    probe = (results.get("data") or {}).get("probe_v2") or {}
    lines += ["## 1б. Независимый тест вне шаблонов: probe_v2 (95% ДИ, бутстрэп по текстам)", "",
              "300 сообщений (25 на категорию; ru/kk/mixed; разговорный, официальный, сленг, транслит, опечатки, "
              "трудные случаи), написаны агентом R02 вручную **вне шаблонов** synth_v3 и размечены по "
              "LABELING_GUIDE_v2. Это `synthetic_agent_written`, не тексты жителей: метрика показывает перенос "
              "за пределы шаблонов, а не качество на людях. Ни в обучении, ни в выборе эпохи/порога/гиперпараметров "
              "не участвует. В режимах с людьми прогноз даёт ансамбль моделей k фолдов (среднее вероятностей).", ""]
    if probe.get("n"):
        lines.append("| Модель \\ обучение | " + " | ".join(REGIME_TITLES[r] for r in regimes) + " |")
        lines.append("|---" * (len(regimes) + 1) + "|")
        for m in ("heuristic", "logreg", "transformer"):
            cells = [_cell(runs.get(f"{r}/{m}"), "probe_v2") for r in regimes]
            lines.append(f"| {MODEL_TITLES[m]} | " + " | ".join(cells) + " |")
        lines.append("")
    else:
        lines += [f"NOT_AVAILABLE — {probe.get('reason', 'набор probe_v2 не найден')}", ""]

    extra = [(m, runs.get(f"none/{m}")) for m in ("zeroshot_llm", "v1_shipped") if runs.get(f"none/{m}")]
    if extra:
        lines += ["Без обучения на наших данных:", "",
                  "| Модель | Люди: macro-F1 [95% ДИ] | probe_v2: macro-F1 [95% ДИ] | Покрытие | Примечание |",
                  "|---|---|---|---|---|"]
        for m, e in extra:
            note = e.get("reason", "") if e.get("status") != "OK" else e.get("note", "")
            cov = e.get("coverage", "—")
            if isinstance(cov, dict):
                cov = "; ".join(f"{k}: {v}" for k, v in cov.items())
            lines.append(f"| {MODEL_TITLES[m]} | {_cell(e, 'human')} | {_cell(e, 'probe_v2')} | {cov} | {note} |")
        lines.append("")

    # 2. Синтетический test — справочно и «потеря на людях».
    lines += ["## 2. Синтетический test (справочно, НЕ качество на людях)", "",
              "Test синтетики — шаблоны, которых не было в обучении (ДИ — бутстрэп по шаблонам). "
              "«Потеря» = macro-F1 на test своего корпуса − macro-F1 на probe_v2 (вне шаблонов) или на людях "
              "(разные наборы, не парная разница).", "",
              "| Режим | Модель | Синтетика v3 test | LLM test | v1→v2 test | probe_v2 | Люди | "
              "Потеря: шаблоны → probe | Потеря: шаблоны → люди |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in regimes:
        if not r.startswith("synth"):
            continue
        for m in ("heuristic", "logreg", "transformer"):
            e = runs.get(f"{r}/{m}")
            if not e:
                continue
            ev = e.get("eval") or {}
            own_set = {"synth_llm": "synth_test_llm", "synth_v1": "synth_test_v1"}.get(r, "synth_test_template")
            own = ev.get(own_set, {}).get("macro_f1")

            def gap(other):
                val = ev.get(other, {}).get("macro_f1")
                return "—" if own is None or val is None else f"{own - val:+.3f}"

            lines.append(f"| {REGIME_TITLES[r]} | {MODEL_TITLES[m]} | {_cell(e, 'synth_test_template')} | "
                         f"{_cell(e, 'synth_test_llm')} | {_cell(e, 'synth_test_v1')} | {_cell(e, 'probe_v2')} | "
                         f"{_cell(e, 'human')} | {gap('probe_v2')} | {gap('human')} |")
    lines.append("")

    # 3. Парные сравнения.
    comps = results.get("comparisons") or []
    if comps:
        lines += ["## 3. Парные сравнения (Δ macro-F1 = a − b, парный бутстрэп на одном наборе)", "",
                  "Главные — на текстах людей и на probe_v2 (ресэмплинг текстов); на синтетическом test — "
                  "справочно (ресэмплинг шаблонов).", "",
                  "| Набор | Сравнение | Δ | 95% ДИ | доля ресэмплов Δ>0 | n |", "|---|---|---|---|---|---|"]
        order = {"human": 0, "probe_v2": 1}
        for c in sorted(comps, key=lambda c: order.get(c.get("set", "human"), 2)):
            d = c["delta"]
            set_title = SET_TITLES.get(c.get("set", "human"), c.get("set", "human"))
            lines.append(f"| {set_title} | {c['title']} | {d['delta']:+.3f} | [{d['low']:+.3f}; {d['high']:+.3f}] | "
                         f"{d['share_delta_gt_0']} | {c['n']} |")
        lines += ["", "Если 95% ДИ разницы содержит 0 — преимущество не доказано на этом объёме данных.", ""]

    # 4. Лучшая модель: по классам, матрица, срезы — на людях и на probe_v2.
    for set_name, best_key, num in (("human", results.get("best_on_human"), "4"),
                                    ("probe_v2", results.get("best_on_probe"), "4б")):
        if best_key and ((runs.get(best_key) or {}).get("eval") or {}).get(set_name):
            lines += _best_section(runs[best_key]["eval"][set_name], best_key, SET_TITLES[set_name], num, labels)

    # 5. Разброс по seed.
    seeds = {k: v["seed_runs"] for k, v in runs.items() if v.get("seed_runs")}
    if seeds:
        lines += ["## 5. Разброс трансформера по seed (macro-F1)", "", "| Прогон | Набор | по seed | среднее ± sd |",
                  "|---|---|---|---|"]
        for k, sr in seeds.items():
            for field, title in (("human_macro_f1", "люди"), ("probe_v2_macro_f1", "probe_v2")):
                vals = [x[field] for x in sr if x.get(field) is not None]
                if vals:
                    lines.append(f"| {k} | {title} | {', '.join(f'{v:.3f}' for v in vals)} | "
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
              "- Метрики на синтетическом test и на probe_v2 не являются качеством на людях: probe_v2 тоже написан "
              "агентом (R02), хоть и вне шаблонов; он отвечает на вопрос «переносится ли модель за пределы шаблонов».",
              "- Тексты людей не использовались для подбора параметров: эпоха, порог и гиперпараметры логрегрессии "
              "выбираются на validation внутри обучающей части фолда; для режимов без людей — на синтетической validation.",
              "- Словарь эвристики написан до появления текстов людей и после не менялся.",
              "- Разметка людей — один разметчик (владелец), если не указано иное; согласие разметчиков — отчёт R02 "
              "(ml/labeling/agreement.py).", ""]
    notes = list(results.get("notes") or [])
    # Почему ячейки NOT_RUN / NOT_EVALUATED / FAILED — одной строкой на причину.
    reasons: dict[str, list[str]] = {}
    for key, e in runs.items():
        if e.get("status") != "OK":
            reasons.setdefault(f"{e.get('status')}: {e.get('reason', '')}", []).append(key)
    for reason, keys in reasons.items():
        notes.append(f"{reason} — {', '.join(sorted(keys))}")
    if notes:
        lines += ["## Замечания прогона", ""] + [f"- {n}" for n in notes] + [""]
    return "\n".join(lines)


def _best_section(ev: dict, key: str, set_title: str, num: str, labels) -> list[str]:
    """Разбор лучшего прогона на наборе: P/R/F1 по категориям, матрица ошибок, срезы, калибровка."""
    out = [f"## {num}. Лучшая на наборе «{set_title}»: {key} — по категориям", "",
           "| Категория | Precision | Recall | F1 | Support | Предсказано |", "|---|---|---|---|---|---|"]
    names = L.names("ru")
    for lab in labels:
        v = ev["per_class"].get(lab, {})
        out.append(f"| {lab} ({names.get(lab, lab)}) | {_f(v.get('precision'))} | {_f(v.get('recall'))} | "
                   f"{_f(v.get('f1'))} | {v.get('support', 0)} | {v.get('predicted', 0)} |")
    cm = ev["confusion"]
    out += ["", "Матрица ошибок (строки — истина, столбцы — прогноз):", "",
            "| истина \\ прогноз | " + " | ".join(cm["labels"]) + " |", "|---" * (len(cm["labels"]) + 1) + "|"]
    for lab, row in zip(cm["labels"], cm["rows_true_cols_pred"]):
        out.append(f"| {lab} | " + " | ".join(str(x) for x in row) + " |")
    if ev.get("slices"):
        out += ["", "Срезы (macro-F1):", ""]
        for skey, sl in ev["slices"].items():
            parts = [f"{k}: n={v['n']}, {_f(v['macro_f1'])}" for k, v in sl.items()]
            out.append(f"- **{skey}** — " + "; ".join(parts))
    if ev.get("ece") is not None:
        out.append(f"- Калибровка (ECE): {ev['ece']} — score модели не является точной вероятностью.")
    out.append("")
    return out


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


def auto_set_name(recs: list[dict]) -> str:
    """«probe_v2» только если все записи синтетические (evidence synthetic*), иначе «human» (тексты не печатаются)."""
    return "probe_v2" if recs and all(str(r.get("evidence", "")).startswith("synthetic") for r in recs) else "human"


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
    if args.to_cyrillic:
        # Та же модель, тексты после to_cyrillic (R04): помогает ли перевод транслита (см. translit.py).
        from ml.civic_classifier_v2.translit import compare, load_to_cyrillic
        to_cyr = load_to_cyrillic(args.normalize_file)
        cyr = [to_cyr(r["text"]) for r in recs]
        pred_cyr = [int(i) for i in clf.predict_proba(cyr).argmax(axis=1)]
        out["to_cyrillic"] = compare(recs, pred, pred_cyr, [a != r["text"] for a, r in zip(cyr, recs)])
        d = out["to_cyrillic"]["paired_delta_cyr_minus_raw"]
        print(f"to_cyrillic: macro-F1 {out['to_cyrillic']['raw']['macro_f1']} -> "
              f"{out['to_cyrillic']['to_cyrillic']['macro_f1']} (Δ {d['delta']:+.3f} [{d['low']:+.3f}; {d['high']:+.3f}])")
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.preds_out:
        # Прогноз по каждому тексту: только id, метки и score (без текстов) — для analysis.py errors.
        # auto: «probe_v2» только если ВСЕ записи синтетические (evidence synthetic*), иначе «human» —
        # analysis.py никогда не печатает тексты набора human, даже если флаг забыли.
        set_name = auto_set_name(recs) if args.set_name == "auto" else args.set_name
        with open(args.preds_out, "w", encoding="utf-8") as fh:
            for r, pr, row in zip(recs, pred, proba):
                fh.write(json.dumps({"set": set_name, "id": r["id"], "true": r["label"], "pred": labels[pr],
                                     "score": round(float(row[pr]), 4)}, ensure_ascii=False) + "\n")
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
    m.add_argument("--not-complaint", choices=("drop", "other"), default="drop")
    m.add_argument("--out")
    m.add_argument("--preds-out", help="JSONL прогнозов по текстам {set,id,true,pred,score} (без текстов)")
    m.add_argument("--to-cyrillic", action="store_true",
                   help="ещё прогон с переводом транслита в кириллицу (to_cyrillic R04) и парная разница")
    m.add_argument("--normalize-file", help="ml/civic_dedup/normalize.py R04, если его нет в сборке")
    m.add_argument("--set-name", default="auto",
                   help="имя набора в --preds-out; auto: probe_v2, если все записи синтетические, иначе human "
                        "(примеры текстов human analysis.py не показывает)")
    args = ap.parse_args(argv)
    return _cmd_render(args) if args.cmd == "render" else _cmd_model(args)


if __name__ == "__main__":
    sys.exit(main())
