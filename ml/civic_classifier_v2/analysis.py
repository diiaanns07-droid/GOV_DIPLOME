"""Таблицы для диплома и разбор ошибок — из готовых результатов, без переобучения.

    # таблицы (Markdown + CSV) из results/experiments.json, final_model_meta.json, onnx_export.json:
    python -m ml.civic_classifier_v2.analysis tables
    # разбор ошибок на probe_v2 по матрицам ошибок (+ примеры текстов, если есть прогнозы по каждому тексту):
    python -m ml.civic_classifier_v2.analysis errors \
        --preds ml/civic_classifier_v2/results/preds_probe_v2_synth_all_logreg.jsonl \
        --probe ml/datasets/probe_v2/probe_v2.jsonl

Тексты печатаются только для probe_v2 и синтетических наборов (их писали агенты). Прогнозы на текстах людей
(set == "human") в примеры не попадают никогда — только числа.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import RESULTS_DIR

REGIMES = ("synth_v1", "synth_template", "synth_llm", "synth_all")
REGIME_RU = {"synth_v1": "v1→v2 (R08)", "synth_template": "шаблонная v3", "synth_llm": "LLM llm_v1",
             "synth_all": "v3 + LLM", "human": "только люди", "mix": "смесь"}
MODELS = ("heuristic", "logreg", "transformer")
MODEL_RU = {"heuristic": "словарь", "logreg": "логрегрессия", "transformer": "трансформер"}
PRIVATE_SETS = {"human"}


def _load(path: Path | None) -> dict:
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def _f(v, d=3) -> str:
    return "—" if v is None else f"{v:.{d}f}"


def _ci(ev: dict | None) -> str:
    if not ev or ev.get("macro_f1") is None:
        return "—"
    c = ev["ci"]["macro_f1"]
    return f"{ev['macro_f1']:.3f} [{c['low']:.3f}–{c['high']:.3f}]"


def _ru_title(title: str) -> str:
    """Названия сравнений из experiments.py («synth_all: трансформер − эвристика») — словами для диплома."""
    head, sep, rest = title.partition(": ")
    head = REGIME_RU.get(head) or MODEL_RU.get(head) or head
    return (head + sep + rest).replace("эвристика", "словарь")


def _ev(runs: dict, key: str, set_name: str) -> dict | None:
    e = runs.get(key) or {}
    return (e.get("eval") or {}).get(set_name) if e.get("status") == "OK" else None


class Table:
    """Таблица, которая пишется и в Markdown, и в CSV (для вставки в Word/Excel)."""

    def __init__(self, slug: str, title: str, header: list[str], note: str = ""):
        self.slug, self.title, self.header, self.note, self.rows = slug, title, header, note, []

    def add(self, *cells) -> None:
        self.rows.append([str(c) for c in cells])

    def markdown(self) -> list[str]:
        out = [f"### {self.title}", ""]
        if self.note:
            out += [self.note, ""]
        out.append("| " + " | ".join(self.header) + " |")
        out.append("|" + "---|" * len(self.header))
        out += ["| " + " | ".join(r) + " |" for r in self.rows]
        return out + [""]

    def write_csv(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self.slug}.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:  # utf-8-sig: Excel открывает кириллицу
            w = csv.writer(fh, delimiter=";")
            w.writerow(self.header)
            w.writerows(self.rows)
        return path


# ---------- таблицы для диплома ----------

def build_tables(exp: dict, final: dict, onnx: dict, folder: Path | None = None) -> list[Table]:
    runs = exp.get("runs") or {}
    labels = tuple(exp.get("labels") or L.labels())
    names = L.names("ru")
    tables: list[Table] = []

    t = Table("t1_probe_v2_macro_f1", "Таблица 1. Macro-F1 на независимом тесте probe_v2 (95% ДИ)",
              ["Модель \\ данные обучения"] + [REGIME_RU[r] for r in REGIMES],
              "probe_v2 — 300 текстов, написанных агентом R02 вручную вне шаблонов (25 на категорию); "
              "не тексты жителей. Бутстрэп 2000 повторов по текстам.")
    for m in MODELS:
        t.add(MODEL_RU[m], *[_ci(_ev(runs, f"{r}/{m}", "probe_v2")) for r in REGIMES])
    pe = (final.get("probe_v2_eval") or {})
    if pe.get("macro_f1") is not None:
        c = pe["ci"]["macro_f1"]
        t.add("итоговая модель (трансформер, v3 + LLM, train.py)", "—", "—", "—",
              f"{pe['macro_f1']:.3f} [{c['low']:.3f}–{c['high']:.3f}]")
    tables.append(t)

    own = {"synth_v1": "synth_test_v1", "synth_template": "synth_test_template", "synth_llm": "synth_test_llm",
           "synth_all": "synth_test_template"}
    t = Table("t2_template_vs_probe", "Таблица 2. Тест «своих» шаблонов против теста вне шаблонов",
              ["Данные обучения", "Модель", "Тест своего корпуса", "probe_v2", "Потеря вне шаблонов"],
              "Тест своего корпуса: невиданные шаблоны того же генератора (для v3 + LLM — тест v3); ДИ по шаблонам. "
              "Потеря = своя метрика − probe_v2 (разные наборы, не парная разница). Отрицательная — probe легче.")
    for r in REGIMES:
        for m in ("logreg", "transformer"):
            a, b = _ev(runs, f"{r}/{m}", own[r]), _ev(runs, f"{r}/{m}", "probe_v2")
            gap = (a["macro_f1"] - b["macro_f1"]) if a and b else None
            t.add(REGIME_RU[r], MODEL_RU[m], _ci(a), _ci(b), "—" if gap is None else f"{gap:+.3f}")
    tables.append(t)

    t = Table("t3_paired_probe_v2", "Таблица 3. Парные сравнения на probe_v2 (Δ macro-F1 = a − b)",
              ["Сравнение", "Δ", "95% ДИ", "Доля ресэмплов Δ > 0", "Вывод"],
              "Парный бутстрэп по текстам. «Доказано», если 95% ДИ не содержит 0.")
    for c in exp.get("comparisons") or []:
        if c.get("set") != "probe_v2":
            continue
        d = c["delta"]
        verdict = "доказано" if (d["low"] > 0 or d["high"] < 0) else "не доказано"
        t.add(_ru_title(c["title"]), f"{d['delta']:+.3f}", f"[{d['low']:+.3f}; {d['high']:+.3f}]", d["share_delta_gt_0"], verdict)
    have = {r[0] for r in t.rows}
    for title, d in paired_files(Path(folder) if folder else RESULTS_DIR):
        if title not in have:
            verdict = "доказано" if (d["low"] > 0 or d["high"] < 0) else "не доказано"
            t.add(title, f"{d['delta']:+.3f}", f"[{d['low']:+.3f}; {d['high']:+.3f}]", d["share_delta_gt_0"], verdict)
    tables.append(t)

    keys = [f"synth_all/{m}" for m in MODELS]
    evs = {k: _ev(runs, k, "probe_v2") for k in keys}
    if all(evs.values()):
        t = Table("t4_per_class_probe_v2", "Таблица 4. F1 по категориям на probe_v2 (обучение на v3 + LLM)",
                  ["Категория", "словарь", "логрегрессия", "трансформер", "Δ трансформер − логрегрессия"],
                  "По 25 текстов на категорию: один текст меняет recall на 0.04 — разницы меньше 0.08 не толковать.")
        for lab in labels:
            f = [evs[k]["per_class"][lab]["f1"] for k in keys]
            t.add(f"{names.get(lab, lab)} ({lab})", *[_f(x, 2) for x in f], f"{f[2] - f[1]:+.2f}")
        t.add("macro-F1", *[_f(evs[k]["macro_f1"]) for k in keys],
              f"{evs[keys[2]]['macro_f1'] - evs[keys[1]]['macro_f1']:+.3f}")
        tables.append(t)

        t = Table("t5_slices_probe_v2", "Таблица 5. Срезы probe_v2: язык, стиль, трудные случаи (обучение на v3 + LLM)",
                  ["Срез", "n", "словарь", "логрегрессия", "трансформер"],
                  "Macro-F1 внутри среза; при n < 30 разброс большой (особенно translit, slang, thanks).")
        sl = {k: evs[k].get("slices") or {} for k in keys}
        for dim, title in (("lang", "язык"), ("style", "стиль"), ("hard", "трудный случай")):
            for val, v in (sl[keys[2]].get(dim) or {}).items():
                t.add(f"{title}: {val}", v["n"], *[_f((sl[k].get(dim) or {}).get(val, {}).get("macro_f1")) for k in keys])
        tables.append(t)

    t = Table("t6_training_cost", "Таблица 6. Обучение трансформера на RTX 4060 Laptop (8 ГБ)",
              ["Данные обучения", "Текстов train / val", "Эпох (лучшая)", "val macro-F1", "Время, с", "Пик GPU, ГБ"],
              "fp16, batch 16 × 2, длина ≤ 128, ранняя остановка по val macro-F1 (терпение 2).")
    for r in REGIMES:
        e = runs.get(f"{r}/transformer") or {}
        tr = e.get("train") or {}
        if e.get("status") == "OK":
            t.add(REGIME_RU[r], f"{tr.get('n_train')} / {tr.get('n_val')}", f"{tr.get('epochs_run')} ({tr.get('best_epoch')})",
                  _f(tr.get("best_val_macro_f1")), tr.get("seconds"), tr.get("gpu_peak_gb"))
    if final.get("model_version"):
        hist = final.get("history") or []
        t.add("итоговая (v3 + LLM)", f"{final.get('n_train')} / {final.get('n_val')}",
              f"{len(hist)} ({final.get('best_epoch')})", _f(final.get("best_val_macro_f1")),
              round(sum(h.get("seconds", 0) for h in hist), 1), (final.get("env") or {}).get("gpu_peak_gb"))
    tables.append(t)

    if onnx:
        chk = onnx.get("check") or {}
        lat = onnx.get("latency_cpu") or {}
        t = Table("t7_onnx", "Таблица 7. Модель для сервера: ONNX int8 на CPU", ["Показатель", "Значение"],
                  f"Источник: results/onnx_export.json ({(lat.get('cpu') or {}).get('processor', '—')}, "
                  f"{(lat.get('cpu') or {}).get('cpu_count', '—')} потоков).")
        sizes = onnx.get("sizes_mb") or {}
        t.add("Размер fp32 / int8, МБ", f"{sizes.get('model.onnx', '—')} / {sizes.get('model.int8.onnx', '—')}")
        t.add("Квантование", f"{(onnx.get('quantize') or {}).get('weight_type', '—')}, per-channel = "
                             f"{(onnx.get('quantize') or {}).get('per_channel', False)}")
        for key, title in (("onnx_fp32_vs_torch", "Совпадение top-1 fp32 с PyTorch"),
                           ("onnx_int8_vs_torch", "Совпадение top-1 int8 с PyTorch")):
            if key in chk:
                t.add(title, f"{chk[key]['argmax_agreement'] * 100:.1f} % (n = {chk.get('n_texts')})")
        for key in ("int8_default_threads", "int8_all_threads", "int8_1_thread"):
            if key in lat:
                t.add(f"Время на текст, {key}", f"{lat[key]['mean_ms']} мс (p95 {lat[key]['p95_ms']})")
        for k, v in (onnx.get("verdict") or {}).items():
            t.add(f"Проверка {k}", v)
        probe8 = _load((Path(folder) if folder else RESULTS_DIR) / "onnx_int8_on_probe_v2.json")
        if probe8.get("human", {}).get("macro_f1") is not None:
            same = not final.get("model_version") or probe8.get("model") == final.get("model_version")
            t.add("probe_v2: macro-F1 int8 (ONNX)" + ("" if same else f" — другая модель {probe8.get('model')}"),
                  _ci(probe8["human"]))
            if final.get("probe_v2_eval", {}).get("macro_f1") is not None:
                t.add("probe_v2: macro-F1 PyTorch (итоговая модель)", _ci(final["probe_v2_eval"]))
        diag = (onnx.get("diagnostics") or {}).get("per_channel")
        if diag:
            t.add("Диагностика LOCAL-4: per-channel, совпадение", f"{diag['batch32_vs_torch']['argmax_agreement'] * 100:.1f} %")
            t.add("Диагностика LOCAL-4: per-channel, 4 потока", f"{diag['isolated_4_threads']['mean_ms']} мс "
                                                               f"(p95 {diag['isolated_4_threads']['p95_ms']})")
        tables.append(t)
    tables += extra_tables(Path(folder) if folder else RESULTS_DIR)
    return tables


def paired_files(folder: Path) -> list[tuple[str, dict]]:
    """Строки таблицы 3 из файлов `analysis paired`: results/paired_<модель>_<режим a>_vs_<режим b>.json."""
    out = []
    for f in sorted(Path(folder).glob("paired_*_vs_*.json")):
        r = _load(f)
        if r.get("set") != "probe_v2" or not r.get("delta"):
            continue
        left, right = f.stem[len("paired_"):].split("_vs_", 1)
        model, _, reg_a = left.partition("_")
        reg = lambda x: REGIME_RU.get(x) or REGIME_RU.get(f"synth_{x}") or x  # noqa: E731 — «template» = synth_template
        title = (f"{MODEL_RU[model]}: {reg(reg_a)} − {reg(right)}" if model in MODEL_RU else f"{r.get('a')} − {r.get('b')}")
        out.append((title, r["delta"]))
    return out


def extra_tables(folder: Path) -> list[Table]:
    """Дополнительные опыты (если файлы есть): перевод транслита, чистка шумных меток llm_v1, нагрузка /classify."""
    out = []
    tr = dict(_load(folder / "translit_to_cyrillic_probe_v2.json"))
    cyr8 = _load(folder / "onnx_int8_on_probe_v2_to_cyrillic.json")
    if cyr8.get("to_cyrillic"):
        final_version = _load(folder / "final_model_meta.json").get("model_version")
        tr["transformer_int8"] = dict(cyr8["to_cyrillic"], other_model=bool(final_version) and cyr8.get("model") != final_version,
                                      model=cyr8.get("model"))
    if tr:
        t = Table("t8_translit_to_cyrillic", "Таблица 8. Перевод транслита в кириллицу перед моделью (probe_v2)",
                  ["Модель", "macro-F1 без / с переводом", "Δ [95% ДИ]", "Транслит: accuracy без / с", "Текстов изменено"],
                  "to_cyrillic — функция R04; меняет только тексты, где латиницы ≥ 50 % (их число — в последней колонке). "
                  "Словарь и логрегрессия обучены как synth_all; трансформер — итоговая модель (ONNX int8).")
        for key, name in (("heuristic_v1", "словарь (v1)"), ("logreg", "логрегрессия"),
                          ("transformer_int8", "трансформер (итоговая, int8)")):
            r = tr.get(key)
            if r:
                d = r["paired_delta_cyr_minus_raw"]
                name = name + (f" — другая модель {r['model']}" if r.get("other_model") else "")
                t.add(name, f"{_f(r['raw']['macro_f1'])} / {_f(r['to_cyrillic']['macro_f1'])}",
                      f"{d['delta']:+.3f} [{d['low']:+.3f}; {d['high']:+.3f}]",
                      f"{_f(r['raw']['translit_accuracy'], 2)} / {_f(r['to_cyrillic']['translit_accuracy'], 2)}",
                      r["texts_changed"])
        out.append(t)
    cl = _load(folder / "llm_label_cleaning_effect.json")
    audit = _load(folder / "LLM_LABEL_AUDIT.json")
    if cl or audit:
        t = Table("t9_llm_label_noise", "Таблица 9. Шум меток LLM-синтетики llm_v1 (без людей)", ["Показатель", "Значение"],
                  "Кандидаты — confident learning (логрегрессия 5-fold): p(своей метки) < 0.2 и другая категория ≥ 0.6.")
        if audit:
            t.add("Кандидатов на неверную метку", f"{audit['candidates']} из {audit['n']} ({audit['share']:.1%})")
            other = (audit.get("by_label") or {}).get("other") or {}
            if other:
                t.add("Из них в «Другом»", f"{other['candidates']} из {other['n']} ({other['share']:.1%})")
        if cl:
            d = cl["paired_delta_clean_minus_original"]
            t.add("Логрегрессия v3 + LLM на probe_v2: исходно / без кандидатов",
                  f"{_f(cl['probe_v2_macro_f1']['original'])} / {_f(cl['probe_v2_macro_f1']['clean'])}")
            t.add("Δ [95% ДИ]", f"{d['delta']:+.3f} [{d['low']:+.3f}; {d['high']:+.3f}] — "
                                f"{'доказано' if d['low'] > 0 or d['high'] < 0 else 'не доказано'}")
        out.append(t)
    loads = [(f, _load(f)) for f in sorted(folder.glob("classify_load*.json"))]
    loads = [(f, r) for f, r in loads if r.get("sequential_by_length")]
    if loads:
        t = Table("t10_classify_load", "Таблица 10. Нагрузка на /classify: ONNX int8, CPU",
                  ["Замер", "Ядер / потоков на запрос", "Текст 40 знаков: mean, мс", "5000 знаков: mean / p95, мс",
                   "Одновременно → запросов в минуту", "p95 при наибольшем числе, мс", "Память, МБ"],
                  "bench.py: путь R04 /classify (обрезка до 5000 знаков и 128 токенов, токенизация, ONNX). Облако — "
                  "модель того же размера со случайными весами: скорость, не качество. Лимит R15 — 60 запросов в минуту "
                  "с адреса.")
        for f, r in loads:
            seq = r["sequential_by_length"]
            short, longest = seq[min(seq, key=int)], seq[max(seq, key=int)]
            conc = r["concurrent_longest"]["by_workers"]
            top = conc[max(conc, key=int)]
            t.add(f.stem.replace("classify_load", "").lstrip("_") or "—",
                  f"{r['cpu'].get('cpu_count')} / {r.get('threads_per_request')}", _f(short["mean_ms"], 1),
                  f"{_f(longest['mean_ms'], 1)} / {_f(longest['p95_ms'], 1)}",
                  "; ".join(f"{w} → {v['requests_per_minute']}" for w, v in sorted(conc.items(), key=lambda kv: int(kv[0]))),
                  _f(top["p95_ms"], 0), _f(r.get("peak_rss_mb"), 0))
        out.append(t)
    return out


def render_tables(tables: list[Table], exp: dict) -> str:
    meta = exp.get("meta") or {}
    out = ["# Таблицы для диплома — классификатор обращений v2 (R03)", "",
           "> Сгенерировано `python -m ml.civic_classifier_v2.analysis tables` из `results/experiments.json` "
           f"(прогон {meta.get('created_at', '—')}, код {meta.get('git_sha', '—')}; {meta.get('env_note', '')}), "
           "`final_model_meta.json`, `onnx_export.json`. Руками не править. CSV — в `results/tables/`.", "",
           "Все числа — синтетика и probe_v2 (тексты агентов). Качество на текстах жителей: "
           f"**{(exp.get('human_eval') or {}).get('status', 'NOT_EVALUATED')}**.", ""]
    for t in tables:
        out += t.markdown()
    return "\n".join(out)


# ---------- разбор ошибок ----------

def confusions(ev: dict, labels: tuple[str, ...], top: int = 10) -> list[tuple[str, str, int, float]]:
    """Самые частые пары (истина → прогноз) без диагонали: (true, pred, n, доля от support истины)."""
    cm = ev["confusion"]["rows_true_cols_pred"]
    pairs = []
    for i, row in enumerate(cm):
        sup = sum(row) or 1
        for j, n in enumerate(row):
            if i != j and n:
                pairs.append((labels[i], labels[j], n, n / sup))
    return sorted(pairs, key=lambda x: (-x[2], x[0], x[1]))[:top]


def magnets(ev: dict, labels: tuple[str, ...]) -> list[tuple[str, int, int, float]]:
    """Категории-«магниты»: предсказаны заметно чаще, чем встречаются (predicted − support > 0), и их precision."""
    out = []
    for lab in labels:
        pc = ev["per_class"][lab]
        if pc["predicted"] > pc["support"]:
            out.append((lab, pc["predicted"], pc["support"], pc["precision"]))
    return sorted(out, key=lambda x: -(x[1] - x[2]))


def read_preds(paths: list[Path]) -> dict[str, dict[str, dict]]:
    """{имя файла: {id: строка}} — только наборы, тексты которых можно показывать (не human)."""
    out = {}
    for p in paths:
        rows = {}
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("set", "probe_v2") in PRIVATE_SETS:
                continue
            rows[str(r["id"])] = r
        out[Path(p).stem] = rows
    return out


def render_errors(exp: dict, preds: dict[str, dict[str, dict]], probe: dict[str, dict]) -> str:
    runs = exp.get("runs") or {}
    labels = tuple(exp.get("labels") or L.labels())
    names = L.names("ru")
    out = ["# Разбор ошибок классификатора v2 на probe_v2 (R03)", "",
           "> Сгенерировано `python -m ml.civic_classifier_v2.analysis errors` из `results/experiments.json`"
           + (" и прогнозов по текстам (" + ", ".join(preds) + ")" if preds else "") + ". Руками не править.", "",
           "probe_v2 — 300 текстов агента R02 вне шаблонов (25 на категорию). Это не тексты жителей: разбор "
           "показывает, где модели путаются за пределами шаблонов обучения.", ""]

    out += ["## 1. Где путаются модели (обучение на v3 + LLM)", ""]
    for m in MODELS:
        ev = _ev(runs, f"synth_all/{m}", "probe_v2")
        if not ev:
            continue
        out += [f"### {MODEL_RU[m]} — macro-F1 {_f(ev['macro_f1'])}, ошибок {round((1 - ev['accuracy']) * ev['n'])} из {ev['n']}",
                "", "| Истина → прогноз | Текстов | Доля категории |", "|---|---|---|"]
        for a, b, n, share in confusions(ev, labels):
            out.append(f"| {names[a]} → {names[b]} | {n} | {share:.0%} |")
        mg = magnets(ev, labels)
        if mg:
            out += ["", "Категории-«магниты» (предсказаны чаще, чем есть): " + "; ".join(
                f"{names[lab]} — {pred} вместо {sup} (precision {_f(prec, 2)})" for lab, pred, sup, prec in mg[:4]) + "."]
        out.append("")

    tr = _ev(runs, "synth_all/transformer", "probe_v2")
    lr = _ev(runs, "synth_all/logreg", "probe_v2")
    if tr and lr:
        out += ["## 2. Что трансформер исправил и что испортил по сравнению с логрегрессией (v3 + LLM)", "",
                "| Категория | F1 логрегрессия | F1 трансформер | Δ | Recall лр → тр | Precision лр → тр |",
                "|---|---|---|---|---|---|"]
        rows = []
        for lab in labels:
            a, b = lr["per_class"][lab], tr["per_class"][lab]
            rows.append((b["f1"] - a["f1"], lab, a, b))
        for d, lab, a, b in sorted(rows, key=lambda x: -x[0]):
            out.append(f"| {names[lab]} | {_f(a['f1'], 2)} | {_f(b['f1'], 2)} | {d:+.2f} | {_f(a['recall'], 2)} → "
                       f"{_f(b['recall'], 2)} | {_f(a['precision'], 2)} → {_f(b['precision'], 2)} |")
        out += ["", "По 25 текстов на категорию: Δ меньше ±0.08 (два текста) — шум.", ""]

    st = _ev(runs, "synth_template/transformer", "synth_test_template")
    if st:
        out += ["## 3. Почему трансформер на одной шаблонной v3 провалился на её же невиданных шаблонах", "",
                f"Macro-F1 на test v3 — {_f(st['macro_f1'])} (логрегрессия {_f((_ev(runs, 'synth_template/logreg', 'synth_test_template') or {}).get('macro_f1'))}). "
                "Категории с нулевым или почти нулевым F1:", ""]
        weak = [(lab, st["per_class"][lab]) for lab in labels if st["per_class"][lab]["f1"] < 0.2]
        for lab, pc in weak:
            row = st["confusion"]["rows_true_cols_pred"][labels.index(lab)]
            goes = sorted(((labels[j], n) for j, n in enumerate(row) if n and labels[j] != lab), key=lambda x: -x[1])[:3]
            out.append(f"- {names[lab]}: F1 {_f(pc['f1'], 2)}, support {pc['support']}, предсказано {pc['predicted']}; "
                       "уходят в " + ", ".join(f"{names[g]} ({n})" for g, n in goes))
        tr_info = (runs.get("synth_template/transformer") or {}).get("train") or {}
        loss = _last_train_loss(RESULTS_DIR / "train_log_experiments.jsonl", "synth_template/transformer")
        all_v3 = (_ev(runs, "synth_all/transformer", "synth_test_template") or {}).get("macro_f1")
        out += ["", f"Train loss в конце обучения {_f(loss, 2)} при val macro-F1 {_f(tr_info.get('best_val_macro_f1'))}: "
                "модель запоминает формулировки шаблонов. Невиданные шаблоны тех же категорий (другие слова) она "
                "относит к соседним темам. С LLM-синтетикой (другие формулировки) test v3 — "
                f"{_f(all_v3)}: разнообразие данных важнее размера модели.", ""]

    if preds and probe:
        out += ["## 4. Примеры ошибок (тексты probe_v2)", ""]
        names_list = list(preds)
        if len(names_list) >= 2:
            a, b = names_list[0], names_list[1]
            ids = [i for i in probe if i in preds[a] and i in preds[b]]
            both = sum(1 for i in ids if preds[a][i]["pred"] != preds[a][i]["true"] and preds[b][i]["pred"] != preds[b][i]["true"])
            only_a = sum(1 for i in ids if preds[a][i]["pred"] != preds[a][i]["true"] and preds[b][i]["pred"] == preds[b][i]["true"])
            only_b = sum(1 for i in ids if preds[a][i]["pred"] == preds[a][i]["true"] and preds[b][i]["pred"] != preds[b][i]["true"])
            out += [f"Из {len(ids)} текстов: ошибаются обе модели — {both}; только `{a}` — {only_a}; только `{b}` — {only_b}.", ""]
        for name, rows in preds.items():
            errs = [(i, r) for i, r in rows.items() if i in probe and r["pred"] != r["true"]]
            by_style = Counter(probe[i].get("style", "") for i, _ in errs)
            by_lang = Counter(probe[i].get("lang", "") for i, _ in errs)
            hard = sum(1 for i, _ in errs if probe[i].get("hard"))
            out += [f"### `{name}` — {len(errs)} ошибок", "",
                    f"Языки: {dict(by_lang.most_common())}; стили: {dict(by_style.most_common())}; трудных случаев: {hard}.", "",
                    "| id | Текст (до 140 знаков) | Истина | Прогноз | Язык / стиль | Правило трудного случая |",
                    "|---|---|---|---|---|---|"]
            for i, r in sorted(errs, key=lambda x: (x[1]["true"], x[0])):
                pr = probe[i]
                text = pr["text"].replace("|", "/").replace("\n", " ")
                text = text if len(text) <= 140 else text[:137] + "…"
                out.append(f"| {i} | {text} | {r['true']} | {r['pred']} | {pr.get('lang', '')} / {pr.get('style', '')} | "
                           f"{pr.get('hard_rule') or ''} |")
            out.append("")
        out += _hard_rules_section(preds, probe)
        out += _suggest_section(preds, probe)
        out += _lang_section(preds, probe)
        out += _calibration_section(preds, probe)
    elif not preds:
        out += ["## 4. Примеры ошибок", "",
                "Нет файлов прогнозов по текстам. Для трансформера их даёт ноутбук: RUN.txt шаг 8б "
                "(`--preds-out`), для словаря и логрегрессии — `experiments.py` (artifacts/experiments/*.jsonl).", ""]
    return "\n".join(out)


def _last_train_loss(log_path: Path, tag_prefix: str) -> float | None:
    """train_loss последней эпохи прогона из лога обучения (если лог сохранён в results/)."""
    if not Path(log_path).exists():
        return None
    last = None
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(r.get("tag", "")).startswith(tag_prefix):
            last = r.get("train_loss")
    return last


SUGGEST_THRESHOLDS = (0.3, 0.5, 0.7, 0.9)


def _suggest_section(preds: dict[str, dict[str, dict]], probe: dict[str, dict]) -> list[str]:
    """Подсказка жителю «Похоже на …» (R04 suggest: категория не other и score ≥ порога модели):
    какая доля текстов получает предвыбор и как часто он верен — по прогнозам со score."""
    rows = []
    for name, pr in preds.items():
        items = [r for i, r in pr.items() if i in probe and r.get("score") is not None]
        if not items:
            continue
        for t in SUGGEST_THRESHOLDS:
            sel = [r for r in items if r["score"] >= t and r["pred"] != "other"]
            prec = sum(r["pred"] == r["true"] for r in sel) / len(sel) if sel else None
            rows.append((name, t, len(sel) / len(items), prec, len(items)))
    if not rows:
        return []
    out = ["## 6. Подсказка «Похоже на …»: доля предвыбора и его точность на probe_v2", "",
           "R04 предвыбирает категорию жителю, если она не «Другое» и score ≥ порога модели (у итоговой — 0.3, "
           "подобран на синтетической validation). Точность — доля верных среди предвыбранных; житель всегда может "
           "сменить категорию. score не калиброван, на людях эти числа будут другими.", "",
           "| Прогнозы | Порог | Доля текстов с предвыбором | Точность предвыбора | n |", "|---|---|---|---|---|"]
    for name, t, cov, prec, n in rows:
        out.append(f"| `{name}` | {t} | {cov:.0%} | {'—' if prec is None else f'{prec:.0%}'} | {n} |")
    return out + [""]


CALIB_BINS = (0.0, 0.5, 0.7, 0.9, 0.97, 1.0)


def _calibration_section(preds: dict[str, dict[str, dict]], probe: dict[str, dict]) -> list[str]:
    """Насколько score (softmax top-1) похож на вероятность верного ответа: по корзинам score — доля верных."""
    from ml.civic_classifier_v2.metrics import ece
    rows = []
    for name, pr in preds.items():
        items = [r for i, r in pr.items() if i in probe and r.get("score") is not None]
        if not items:
            continue
        e = ece([int(r["pred"] == r["true"]) for r in items], [float(r["score"]) for r in items])
        for lo, hi in zip(CALIB_BINS[:-1], CALIB_BINS[1:]):
            b = [r for r in items if lo <= r["score"] < hi or (hi == 1.0 and r["score"] == 1.0)]
            if b:
                sc = sum(r["score"] for r in b) / len(b)
                acc = sum(r["pred"] == r["true"] for r in b) / len(b)
                rows.append((name, f"{lo:.2f}–{hi:.2f}", len(b), sc, acc, e))
    if not rows:
        return []
    out = ["## 8. Калибровка score на probe_v2", "",
           "score — softmax top-1. Если он калиброван, в корзине «0.90–0.97» верны около 93 % ответов. Разница «score − "
           "доля верных» > 0 — модель самоуверенна. ECE — средняя по 10 равным корзинам разница, взвешенная по числу "
           "текстов. Это тексты агента, не жителей: на людях калибровка не проверена.", "",
           "| Прогнозы | score | n | Средний score | Доля верных | score − доля | ECE (10 корзин) |",
           "|---|---|---|---|---|---|---|"]
    for name, rng, n, sc, acc, e in rows:
        out.append(f"| `{name}` | {rng} | {n} | {sc:.2f} | {acc:.0%} | {sc - acc:+.2f} | {_f(e)} |")
    return out + [""]


LANGS = ("ru", "kk", "mixed")


def _lang_section(preds: dict[str, dict[str, dict]], probe: dict[str, dict], weak_n: int = 4,
                  weak_acc: float = 0.6) -> list[str]:
    """Категории × язык: macro-F1 по языку, разрыв kk − ru с 95% ДИ и «верно / всего» по ячейкам."""
    from ml.civic_classifier_v2.metrics import report, unpaired_delta
    labs = L.labels()
    idx = {lab: i for i, lab in enumerate(labs)}
    names_ru = L.names("ru")
    out = ["## 7. Категории и языки на probe_v2", "",
           "Macro-F1 внутри языка и разрыв kk − ru. Тексты на разных языках разные, поэтому ДИ — бутстрэп отдельно "
           "внутри каждого языка (не парный). Ниже — «верно / всего» по категориям: в ячейке {cell_n} текстов, "
           "отдельная ячейка — пример, а не закономерность.", "",
           "| Прогнозы | " + " | ".join(f"{g} (n)" for g in LANGS) + " | kk − ru [95% ДИ] |", "|---|" + "---|" * (len(LANGS) + 1)]
    cells = {}
    for name, pr in preds.items():
        ids = [i for i in probe if i in pr]
        if not ids:
            continue
        by = {g: [i for i in ids if probe[i].get("lang") == g] for g in LANGS}
        row = []
        for g in LANGS:
            y = [idx[pr[i]["true"]] for i in by[g]]
            p = [idx[pr[i]["pred"]] for i in by[g]]
            row.append(f"{_f(report(y, p, labs)['macro_f1'])} ({len(y)})" if y else "—")
        yk, pk = [idx[pr[i]["true"]] for i in by["kk"]], [idx[pr[i]["pred"]] for i in by["kk"]]
        yr, prr = [idx[pr[i]["true"]] for i in by["ru"]], [idx[pr[i]["pred"]] for i in by["ru"]]
        d = unpaired_delta(yk, pk, yr, prr, len(labs))
        gap = "—" if d["delta"] is None else (f"{d['delta']:+.3f} [{d['low']:+.3f}; {d['high']:+.3f}] — "
                                               f"{'доказано' if d['low'] > 0 or d['high'] < 0 else 'не доказано'}")
        out.append(f"| `{name}` | " + " | ".join(row) + f" | {gap} |")
        cells[name] = {(lab, g): (sum(pr[i]["pred"] == pr[i]["true"] for i in by[g] if pr[i]["true"] == lab),
                                  sum(1 for i in by[g] if pr[i]["true"] == lab)) for lab in labs for g in LANGS}
    if not cells:
        return []
    sizes = [b for c in cells.values() for (_, b) in c.values() if b]
    out[2] = out[2].replace("{cell_n}", f"{min(sizes)}–{max(sizes)}" if min(sizes) != max(sizes) else str(min(sizes)))
    out.append("")
    for name, c in cells.items():
        out += [f"### `{name}`: верно / всего по категориям и языкам", "",
                "| Категория | " + " | ".join(LANGS) + " | всего |", "|---|" + "---|" * (len(LANGS) + 1)]
        for lab in labs:
            parts = [c[(lab, g)] for g in LANGS]
            ok, n = sum(a for a, _ in parts), sum(b for _, b in parts)
            out.append(f"| {names_ru[lab]} | " + " | ".join(f"{a} / {b}" if b else "—" for a, b in parts) + f" | {ok} / {n} |")
        weak = sorted(((a / b, lab, g, a, b) for (lab, g), (a, b) in c.items() if b >= weak_n and a / b < weak_acc))
        out += ["", "Слабые ячейки (n ≥ %d, верно < %d %%): " % (weak_n, round(weak_acc * 100)) +
                ("; ".join(f"{names_ru[lab]} / {g} — {a} из {b}" for _, lab, g, a, b in weak) if weak else "нет") + ".", ""]
    return out


def _hard_rules_section(preds: dict[str, dict[str, dict]], probe: dict[str, dict]) -> list[str]:
    """Точность по правилам трудных случаев гайда R02 (поле hard_rule в probe_v2): какие правила модели не усвоили."""
    rules: dict[str, list[str]] = {}
    for i, r in probe.items():
        if r.get("hard_rule"):
            rules.setdefault(r["hard_rule"], []).append(i)
    if not rules:
        return []
    names = list(preds)
    out = ["## 5. Трудные случаи по правилам гайда (LABELING_GUIDE_v2)", "",
           "Доля верных ответов на текстах probe_v2 с данным правилом; n — число таких текстов. Правила с n ≤ 2 "
           "показывают отдельные примеры, а не закономерность.", "",
           "| Правило | n | " + " | ".join(f"`{n}`" for n in names) + " |", "|---|---|" + "---|" * len(names)]
    rows = []
    for rule, ids in rules.items():
        accs = []
        for n in names:
            have = [i for i in ids if i in preds[n]]
            accs.append(sum(preds[n][i]["pred"] == preds[n][i]["true"] for i in have) / len(have) if have else None)
        rows.append((rule, len(ids), accs))
    for rule, n, accs in sorted(rows, key=lambda x: (min(a for a in x[2] if a is not None) if any(
            a is not None for a in x[2]) else 1, -x[1])):
        out.append(f"| {rule} | {n} | " + " | ".join("—" if a is None else f"{a:.0%}" for a in accs) + " |")
    return out + [""]


def paired_from_files(path_a: Path, path_b: Path, set_name: str = "probe_v2") -> dict:
    """Парная Δ macro-F1 (a − b) по двум файлам прогнозов {set,id,true,pred} на общих id набора."""
    from ml.civic_classifier_v2.metrics import paired_delta, report
    labs = L.labels()
    idx = {lab: i for i, lab in enumerate(labs)}

    def load(p):
        rows = (json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip())
        return {str(r["id"]): r for r in rows if r.get("set", set_name) == set_name}

    a, b = load(path_a), load(path_b)
    ids = sorted(set(a) & set(b))
    if not ids:
        raise ValueError(f"нет общих id набора {set_name}")
    y = [idx[a[i]["true"]] for i in ids]
    pa, pb = [idx[a[i]["pred"]] for i in ids], [idx[b[i]["pred"]] for i in ids]
    return {"set": set_name, "n": len(ids), "a": Path(path_a).name, "b": Path(path_b).name,
            "macro_f1_a": report(y, pa, labs)["macro_f1"], "macro_f1_b": report(y, pb, labs)["macro_f1"],
            "delta": paired_delta(y, pa, pb, len(labs))}


def load_probe(path: Path | None) -> dict[str, dict]:
    if not path:
        return {}
    from ml.civic_classifier_v2 import data as D
    rows, _ = D.read_rows(Path(path) if Path(path).is_file() else D.corpus_files(Path(path))[0])
    return {str(r["id"]): r for r in rows if r.get("id")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.analysis", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("tables", "errors"):
        sp = sub.add_parser(name)
        sp.add_argument("--results", default=str(RESULTS_DIR / "experiments.json"))
        sp.add_argument("--final", default=str(RESULTS_DIR / "final_model_meta.json"))
        sp.add_argument("--onnx", default=str(RESULTS_DIR / "onnx_export.json"))
    sub.choices["tables"].add_argument("--out", default=str(RESULTS_DIR / "DIPLOMA_TABLES.md"))
    sub.choices["tables"].add_argument("--csv-dir", default=str(RESULTS_DIR / "tables"))
    sub.choices["errors"].add_argument("--out", default=str(RESULTS_DIR / "ERROR_ANALYSIS.md"))
    sub.choices["errors"].add_argument("--preds", nargs="*", default=[], help="JSONL {set,id,true,pred[,score]}")
    sub.choices["errors"].add_argument("--probe", help="probe_v2.jsonl (тексты для примеров)")
    pr = sub.add_parser("paired", help="парная Δ macro-F1 по двум файлам прогнозов (a − b)")
    pr.add_argument("--a", required=True)
    pr.add_argument("--b", required=True)
    pr.add_argument("--set", default="probe_v2")
    pr.add_argument("--out", help="JSON с результатом")
    args = ap.parse_args(argv)

    if args.cmd == "paired":
        res = paired_from_files(Path(args.a), Path(args.b), args.set)
        d = res["delta"]
        print(f"{res['a']} − {res['b']} на {res['set']} (n={res['n']}): {res['macro_f1_a']} − {res['macro_f1_b']} = "
              f"{d['delta']:+.3f} [{d['low']:+.3f}; {d['high']:+.3f}]")
        if args.out:
            Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0

    exp = _load(Path(args.results))
    if not exp:
        print(f"нет {args.results}", file=sys.stderr)
        return 2
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    if args.cmd == "tables":
        tables = build_tables(exp, _load(Path(args.final)), _load(Path(args.onnx)), Path(args.results).parent)
        Path(args.out).write_text(render_tables(tables, exp) + "\n", encoding="utf-8")
        for t in tables:
            t.write_csv(Path(args.csv_dir))
        print(f"{args.out}: {len(tables)} таблиц; CSV — {args.csv_dir}")
    else:
        preds = read_preds([Path(p) for p in args.preds])
        Path(args.out).write_text(render_errors(exp, preds, load_probe(args.probe)) + "\n", encoding="utf-8")
        print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
