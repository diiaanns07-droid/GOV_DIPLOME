"""Оценка классификатора v2 на текстах живых людей (LOCAL-14; R03 раунд 15 и глава 4 диплома).

    python -m ml.civic_classifier_v2.eval_human --human private/labels_owner.jsonl \\
        --model ml/civic_classifier_v2/artifacts/onnx --out ml/civic_classifier_v2/results

Системы (каждая — только если доступна, иначе NOT_RUN с причиной):
  heuristic   — продуктовый словарь (запасной путь R04 без файла модели), всегда;
  logreg      — логрегрессия на синтетике v3 (+ LLM-синтетика llm_v1, если файл есть), нужен scikit-learn;
  transformer — сохранённая модель (--model: ONNX или PyTorch-папка, на ноутбуке).
Для каждой: accuracy, macro-F1 с 95 % ДИ (бутстрэп), срезы по языку текста (ru / kk / вперемешку / транслит:
n, macro-F1, ДИ), по категориям (precision, recall, F1, support), матрица ошибок (счётчики), и сравнение с синтетикой:
та же система на probe_v2 (300 текстов вне шаблонов) — разрыв «люди − синтетика» с ДИ (несвязанный бутстрэп).

Приватность: тексты людей никуда не пишутся и не печатаются — в результатах только числа, метки и счётчики. Файл людей
должен лежать вне Git (папка private/ в .gitignore); если он под контролем Git — отказ (код 3).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import heuristic
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import LLM_V1_DIR, PROBE_V2_DIR, REPO_ROOT, RESULTS_DIR, SYNTH_V3_DIR
from ml.civic_classifier_v2.metrics import bootstrap, report, unpaired_delta

MIN_HUMAN = 200          # меньше — ДИ слишком широкие для выводов (пишем предупреждение, но считаем)
MIN_SLICE = 10           # срез языка меньше 10 текстов — без ДИ
LANG_TITLES = {"ru": "русский", "kk": "казахский", "mixed": "вперемешку", "latin": "транслит", "unknown": "не определён"}
SEED = 20261015


def tracked_by_git(path: Path) -> bool:
    """Файл под контролем Git? Тогда это не «приватная» разметка — оценку не запускаем."""
    try:
        res = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], cwd=REPO_ROOT, capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0


# ---------------------------------------------------------------- системы

def system_heuristic(labels):
    index = {lab: i for i, lab in enumerate(labels)}

    def predict(texts: list[str]) -> list[int]:
        return [index[x] for x in heuristic.predict(texts, version="product")]
    return predict, {"name": "heuristic", "title": "Продуктовый словарь (без модели)", "status": "ok"}


def system_logreg(labels, seed: int = SEED):
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return None, {"name": "logreg", "status": "NOT_RUN", "reason": "нет scikit-learn (pip install scikit-learn)"}
    from ml.civic_classifier_v2 import logreg
    train, val, used = [], [], []
    for path, source, evidence in ((SYNTH_V3_DIR, "synth_v3", "synthetic_template"),
                                   (LLM_V1_DIR, "llm_v1", "synthetic_llm")):
        try:
            recs, _rep = D.load_corpus(Path(path), source=source, evidence=evidence)
        except FileNotFoundError:
            continue
        D.ensure_splits(recs, seed)
        train += [r for r in recs if r.get("split") == "train"]
        val += [r for r in recs if r.get("split") == "val"]
        used.append(source)
    if not train:
        return None, {"name": "logreg", "status": "NOT_RUN", "reason": "нет синтетических корпусов для обучения"}
    model, sel = logreg.fit(train, val, seed, labels=labels)

    def predict(texts: list[str]) -> list[int]:
        return [int(i) for i in model.predict_proba(texts).argmax(axis=1)]
    return predict, {"name": "logreg", "title": "Логрегрессия на синтетике (" + " + ".join(used) + ")", "status": "ok",
                     "train": {"n_train": len(train), "n_val": len(val), "sources": used, "chosen": sel.get("chosen")}}


def system_transformer(model_dir: str | None):
    if not model_dir:
        return None, {"name": "transformer", "status": "NOT_RUN", "reason": "не указан --model (веса — на ноутбуке)"}
    from ml.civic_classifier_v2.predict import Classifier
    try:
        clf = Classifier.load(Path(model_dir))
    except Exception as exc:  # noqa: BLE001 — нет onnxruntime/torch или папки
        return None, {"name": "transformer", "status": "NOT_RUN", "reason": f"модель не загрузилась: {type(exc).__name__}"}

    def predict(texts: list[str]) -> list[int]:
        return [int(i) for i in clf.predict_proba(texts).argmax(axis=1)]
    return predict, {"name": "transformer", "title": "Трансформер v2 (" + str(clf.model_version) + ", " + str(clf.backend) + ")",
                     "status": "ok", "labels": list(clf.labels)}


# ---------------------------------------------------------------- метрики

def evaluate(records: list[dict], pred: list[int], labels: tuple[str, ...]) -> dict:
    index = {lab: i for i, lab in enumerate(labels)}
    y = [index[r["label"]] for r in records]
    rep = report(y, pred, labels)
    rep["ci"] = bootstrap(y, pred, len(labels))
    slices = {}
    for lang in sorted({r["lang"] for r in records}):
        idx = [i for i, r in enumerate(records) if r["lang"] == lang]
        sub = report([y[i] for i in idx], [pred[i] for i in idx], labels)
        row = {"title": LANG_TITLES.get(lang, lang), "n": len(idx), "accuracy": sub["accuracy"], "macro_f1": sub["macro_f1"]}
        if len(idx) >= MIN_SLICE:
            row["ci"] = bootstrap([y[i] for i in idx], [pred[i] for i in idx], len(labels))["macro_f1"]
        slices[lang] = row
    rep["by_lang"] = slices
    return rep


def compare_with_synthetic(human: list[dict], pred_h: list[int], probe: list[dict], pred_p: list[int], labels) -> dict:
    index = {lab: i for i, lab in enumerate(labels)}
    y_h = [index[r["label"]] for r in human]
    y_p = [index[r["label"]] for r in probe]
    probe_rep = report(y_p, pred_p, labels)
    return {"probe_v2": {"n": probe_rep["n"], "macro_f1": probe_rep["macro_f1"],
                         "ci": bootstrap(y_p, pred_p, len(labels))["macro_f1"]},
            "human_minus_probe": unpaired_delta(y_h, pred_h, y_p, pred_p, len(labels))}


# ---------------------------------------------------------------- отчёт (без текстов)

def _f(v) -> str:
    return "—" if v is None else f"{v:.3f}".replace(".", ",")


def _ci(ci) -> str:
    if not isinstance(ci, dict) or ci.get("low") is None:
        return ""
    return f" [{_f(ci['low'])}; {_f(ci['high'])}]"


def render(result: dict) -> str:
    lines = ["# Классификатор v2 на текстах людей (LOCAL-14)", "",
             f"Прогон: {result['run_at']}, код {result['git_sha']}. Файлов разметки: {result['files']}, текстов после "
             f"очистки: **{result['n']}** (ru {result['by_lang_n'].get('ru', 0)}, kk {result['by_lang_n'].get('kk', 0)}, "
             f"вперемешку {result['by_lang_n'].get('mixed', 0)}, транслит {result['by_lang_n'].get('latin', 0)}). "
             "Тексты людей в этот файл не попадают — только числа.", ""]
    if result["n"] < MIN_HUMAN:
        lines += [f"**Внимание:** текстов меньше {MIN_HUMAN} — интервалы широкие, выводы предварительные.", ""]
    lines += ["| Система | macro-F1 [95 % ДИ] | accuracy | ru | kk | вперемешку | транслит | probe_v2 (синтетика) | люди − синтетика |",
              "|---|---|---|---|---|---|---|---|---|"]
    for s in result["systems"]:
        if s["status"] != "ok":
            lines.append(f"| {s.get('title') or s['name']} | NOT_RUN: {s['reason']} | | | | | | | |")
            continue
        h = s["human"]
        by = h["by_lang"]
        cells = [f"{_f(by[k]['macro_f1'])} (n={by[k]['n']})" if k in by else "—" for k in ("ru", "kk", "mixed", "latin")]
        cmp_ = s["vs_synthetic"]
        delta = cmp_["human_minus_probe"]
        lines.append(f"| {s['title']} | {_f(h['macro_f1'])}{_ci(h['ci']['macro_f1'])} | {_f(h['accuracy'])} | "
                     + " | ".join(cells) + f" | {_f(cmp_['probe_v2']['macro_f1'])} | "
                     f"{_f(delta.get('delta'))}{_ci({'low': delta.get('low'), 'high': delta.get('high')})} |")
    lines += ["", "Матрицы ошибок и метрики по категориям — `human_eval.json` (поля systems[].human.confusion и per_class).",
              "Разрыв «люди − синтетика» отрицательный — модель на живых текстах хуже, чем на синтетике вне шаблонов.", ""]
    return "\n".join(lines)


def run(human_paths: list[Path], model_dir: str | None, use_logreg: bool, out_dir: Path) -> dict:
    labels = L.labels()
    human, load_rep = D.load_human(human_paths)
    probe, _ = D.load_human([PROBE_V2_DIR / "probe_v2.jsonl"])
    texts_h, texts_p = [r["text"] for r in human], [r["text"] for r in probe]
    factories = [lambda: system_heuristic(labels)]
    if use_logreg:
        factories.append(lambda: system_logreg(labels))
    factories.append(lambda: system_transformer(model_dir))
    systems = []
    for make in factories:
        predict, info = make()
        if predict is None:
            systems.append(info)
            continue
        sys_labels = tuple(info.get("labels") or labels)
        pred_h, pred_p = predict(texts_h), predict(texts_p)
        info["human"] = evaluate(human, pred_h, sys_labels)
        info["vs_synthetic"] = compare_with_synthetic(human, pred_h, probe, pred_p, sys_labels)
        systems.append(info)
    by_lang_n = {}
    for r in human:
        by_lang_n[r["lang"]] = by_lang_n.get(r["lang"], 0) + 1
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = "unknown"
    result = {"format": "birge-clf-v2-human-eval", "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "git_sha": sha, "files": len(human_paths), "n": len(human), "by_lang_n": by_lang_n,
              "load_report": load_rep, "min_human": MIN_HUMAN, "labels": list(labels), "systems": systems,
              "note": "Тексты людей не сохраняются: только числа, метки, счётчики."}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "human_eval.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "RESULTS_HUMAN.md").write_text(render(result), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.eval_human", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--human", nargs="+", required=True, help="разметка людей (JSONL/CSV из web/labeling), вне Git")
    ap.add_argument("--model", help="папка модели: ONNX или PyTorch (artifacts/…)")
    ap.add_argument("--no-logreg", action="store_true", help="не обучать логрегрессию на синтетике")
    ap.add_argument("--out", default=str(RESULTS_DIR))
    args = ap.parse_args(argv)
    paths = [Path(p) for p in args.human]
    for p in paths:
        if not p.exists():
            print(f"NOT_RUN: файла разметки нет: {p}")
            return 2
        if tracked_by_git(p):
            print(f"Отказ: {p} под контролем Git — тексты людей не должны попадать в репозиторий (положите в private/).")
            return 3
    result = run(paths, args.model, not args.no_logreg, Path(args.out))
    for s in result["systems"]:
        if s["status"] == "ok":
            print(f"{s['name']}: macro-F1 {s['human']['macro_f1']} (n={s['human']['n']}), "
                  f"probe_v2 {s['vs_synthetic']['probe_v2']['macro_f1']}")
        else:
            print(f"{s['name']}: NOT_RUN — {s['reason']}")
    print(f"Записано: {Path(args.out) / 'human_eval.json'}, {Path(args.out) / 'RESULTS_HUMAN.md'} (без текстов людей)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
