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

def build_tables(exp: dict, final: dict, onnx: dict) -> list[Table]:
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
        diag = (onnx.get("diagnostics") or {}).get("per_channel")
        if diag:
            t.add("Диагностика LOCAL-4: per-channel, совпадение", f"{diag['batch32_vs_torch']['argmax_agreement'] * 100:.1f} %")
            t.add("Диагностика LOCAL-4: per-channel, 4 потока", f"{diag['isolated_4_threads']['mean_ms']} мс "
                                                               f"(p95 {diag['isolated_4_threads']['p95_ms']})")
        tables.append(t)
    return tables


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
        out += ["", "Train loss падает до 0.03 при val 0.756: модель запоминает формулировки шаблонов. Невиданные "
                "шаблоны тех же категорий (другие слова) она относит к соседним темам. Добавление LLM-синтетики "
                "(другие формулировки) поднимает test v3 до 0.779 — разнообразие данных важнее размера модели.", ""]

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
    elif not preds:
        out += ["## 4. Примеры ошибок", "",
                "Нет файлов прогнозов по текстам. Для трансформера их даёт ноутбук: RUN.txt шаг 8б "
                "(`--preds-out`), для словаря и логрегрессии — `experiments.py` (artifacts/experiments/*.jsonl).", ""]
    return "\n".join(out)


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
    args = ap.parse_args(argv)

    exp = _load(Path(args.results))
    if not exp:
        print(f"нет {args.results}", file=sys.stderr)
        return 2
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    if args.cmd == "tables":
        tables = build_tables(exp, _load(Path(args.final)), _load(Path(args.onnx)))
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
