"""Опыт: помогает ли перевод чат-транслита в кириллицу (to_cyrillic из ml/civic_dedup R04) моделям v2.

R04 переводит латиницу в кириллицу перед словарём и v1 (`classify_chain.py`), но не перед моделью v2. Здесь
проверяем на probe_v2, стоит ли делать то же для v2: та же модель, те же тексты — с переводом и без.

    # словарь v1 и логрегрессия (переобучается на v3 + LLM, как synth_all в experiments.py), облако/CPU, ~2 мин:
    python -m ml.civic_classifier_v2.translit check --synth-v3 DIR --llm-v1 DIR --v1-in-v2 DIR --probe-v2 DIR
    # трансформер (готовая модель) — то же через evaluate:
    python -m ml.civic_classifier_v2.evaluate model --model artifacts/onnx --human probe_v2.jsonl --to-cyrillic

to_cyrillic — код R04 (не копируется в R03): берётся `ml.civic_dedup.normalize`, если он есть в сборке, иначе
из файла `--normalize-file` (например, извлечённого `git show origin/claude/r14-R04:ml/civic_dedup/normalize.py`).
Результат — только числа: results/translit_to_cyrillic_probe_v2.json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import heuristic as H
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2 import metrics as M
from ml.civic_classifier_v2.config import LLM_V1_DIR, PROBE_V2_DIR, RESULTS_DIR, SYNTH_V3_DIR, V1_IN_V2_DIR


def load_to_cyrillic(normalize_file: str | None = None):
    """Функция to_cyrillic R04: из сборки (ml.civic_dedup) или из указанного файла."""
    if normalize_file:
        spec = importlib.util.spec_from_file_location("r04_civic_dedup_normalize", normalize_file)
        if spec is None or spec.loader is None:
            raise ModuleNotFoundError(f"не удалось загрузить {normalize_file}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.to_cyrillic
    try:
        from ml.civic_dedup.normalize import to_cyrillic  # код R04 — есть в сборке R01
    except ImportError as exc:
        raise ModuleNotFoundError("нет ml/civic_dedup (R04): запустите в сборке R01 или укажите --normalize-file") from exc
    return to_cyrillic


def compare(records: list[dict], pred_raw: list[int], pred_cyr: list[int], changed: list[bool]) -> dict:
    """Метрики «без перевода / с переводом» на одних и тех же текстах + парная разница."""
    labs = L.labels()
    idx = {lab: i for i, lab in enumerate(labs)}
    y = [idx[r["label"]] for r in records]
    tl = [i for i, r in enumerate(records) if r.get("style") == "translit"]
    out = {}
    for mode, p in (("raw", pred_raw), ("to_cyrillic", pred_cyr)):
        rep = M.report(y, p, labs)
        sub = M.report([y[i] for i in tl], [p[i] for i in tl], labs) if tl else {}
        out[mode] = {"macro_f1": rep["macro_f1"], "accuracy": rep["accuracy"],
                     "translit_n": len(tl), "translit_accuracy": sub.get("accuracy"),
                     "translit_macro_f1": sub.get("macro_f1")}
    out["paired_delta_cyr_minus_raw"] = M.paired_delta(y, pred_cyr, pred_raw, len(labs))
    out["texts_changed"] = sum(changed)
    out["changed_by_style"] = dict(sorted({s: sum(1 for r, c in zip(records, changed) if c and r.get("style") == s)
                                           for s in {r.get("style") for r in records}}.items()))
    out["changed_by_style"] = {k: v for k, v in out["changed_by_style"].items() if v}
    return out


def _cmd_check(args) -> int:
    from ml.civic_classifier_v2 import logreg

    to_cyr = load_to_cyrillic(args.normalize_file)
    labs = L.labels()
    idx = {lab: i for i, lab in enumerate(labs)}
    v3, _ = D.load_corpus(Path(args.synth_v3), source="synth_v3", evidence="synthetic_template")
    llm, _ = D.load_corpus(Path(args.llm_v1), source="llm_v1", evidence="synthetic_llm")
    probe, _ = D.load_corpus(Path(args.probe_v2), source="probe_v2", evidence="synthetic_agent_written")
    evals = list(probe) + [r for r in v3 + llm if r["split"] == "test"]
    try:
        v1, _ = D.load_corpus(Path(args.v1_in_v2), source="v1_in_v2", evidence="synthetic_template_v1")
        evals += [r for r in v1 if r["split"] == "test"]
    except FileNotFoundError:
        pass
    # Как synth_all в experiments.py: train/val v3 + LLM, из train убраны совпадения с оценочными наборами.
    tr = [r for r in v3 + llm if r["split"] == "train"]
    va = [r for r in v3 + llm if r["split"] == "val"]
    tr, dropped = D.drop_leaks(tr, evals)
    texts = [r["text"] for r in probe]
    cyr = [to_cyr(t) for t in texts]
    changed = [a != b for a, b in zip(texts, cyr)]
    model, sel = logreg.fit(tr, va, args.seed)
    result = {
        "what": "to_cyrillic (R04) перед моделью; probe_v2, обучение как synth_all (v3 + LLM)",
        "not_human": "probe_v2 — тексты агента R02, не жителей",
        "train": {"n_train": len(tr), "n_val": len(va), "dropped_leaks": dropped, "logreg_selection": sel["chosen"]},
        "heuristic_v1": compare(probe, [idx[x] for x in H.predict(texts, "v1")], [idx[x] for x in H.predict(cyr, "v1")],
                                changed),
        "logreg": compare(probe, model.predict(texts), model.predict(cyr), changed),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for k in ("heuristic_v1", "logreg"):
        r = result[k]
        d = r["paired_delta_cyr_minus_raw"]
        print(f"{k}: macro-F1 {r['raw']['macro_f1']} -> {r['to_cyrillic']['macro_f1']} "
              f"(Δ {d['delta']:+.3f} [{d['low']:+.3f}; {d['high']:+.3f}]); транслит accuracy "
              f"{r['raw']['translit_accuracy']} -> {r['to_cyrillic']['translit_accuracy']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.translit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--synth-v3", default=str(SYNTH_V3_DIR))
    c.add_argument("--llm-v1", default=str(LLM_V1_DIR))
    c.add_argument("--v1-in-v2", default=str(V1_IN_V2_DIR))
    c.add_argument("--probe-v2", default=str(PROBE_V2_DIR))
    c.add_argument("--normalize-file", help="файл ml/civic_dedup/normalize.py R04, если его нет в сборке")
    c.add_argument("--seed", type=int, default=20261011)
    c.add_argument("--out", default=str(RESULTS_DIR / "translit_to_cyrillic_probe_v2.json"))
    args = ap.parse_args(argv)
    return _cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
