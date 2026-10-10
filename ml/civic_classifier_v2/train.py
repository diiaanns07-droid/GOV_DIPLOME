"""Обучение ИТОГОВОЙ модели v2 (одна команда) -> artifacts/final/ (веса, токенизатор, birge_meta.json).

Эксперимент со сравнением режимов — experiments.py; здесь обучается одна модель для продукта
по выбранному режиму (по умолчанию: mix, если есть разметка людей, иначе synth_all/synth_template).

    python -m ml.civic_classifier_v2.train --human private/labels_owner.jsonl
    python -m ml.civic_classifier_v2.train --regime synth_template            # без людей
    python -m ml.civic_classifier_v2.train --regime mix --human private/labels_owner.jsonl \
        --experiments ml/civic_classifier_v2/results/experiments.json --set batch_size=8 --set grad_accum=4

Данные:
  synth_*  : train = train-split синтетики, val = val-split синтетики; тексты людей (если даны) —
             только ОЦЕНКА итоговой модели (в обучении не участвуют) -> human_eval в birge_meta.json;
  human/mix: люди делятся стратифицированно на train / val (val_ratio); val — только люди.
             Оценку на людях для этого рецепта даёт k-fold из experiments.json (--experiments),
             потому что все тексты людей уже в обучении.
Тест-сплит синтетики в обучение не входит никогда.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import (ARTIFACTS_DIR, LLM_V1_DIR, PROBE_V2_DIR, SMOKE_OVERRIDES, SYNTH_V3_DIR,
                                           TrainConfig)

REGIMES = ("synth_template", "synth_llm", "synth_all", "human", "mix")
TRAINING_DATA = {
    "synth_template": "synthetic_template_v3",
    "synth_llm": "synthetic_llm_v1",
    "synth_all": "synthetic_template_v3+synthetic_llm_v1",
    "human": "real_human_labeled",
    "mix": "synthetic+real_human_labeled",
}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", Path(name).name.lower()).strip("-")[:40] or "model"


def assemble(regime: str, synth: dict[str, list[dict]], human: list[dict], val_ratio: float, seed: int,
             notes: list[str]) -> tuple[list[dict], list[dict]]:
    """(train, val) для режима. Ошибка, если нужных данных нет."""
    want = {"synth_template": ["synth_v3"], "synth_llm": ["llm_v1"], "synth_all": ["synth_v3", "llm_v1"],
            "human": [], "mix": ["synth_v3", "llm_v1"]}[regime]
    avail = [k for k in want if synth.get(k)]
    if regime.startswith("synth") and len(avail) < len(want):
        raise SystemExit(f"режим {regime}: нет корпуса {sorted(set(want) - set(avail))} — см. ml/datasets/ (R02)")
    syn_tr = [r for k in avail for r in synth[k] if r["split"] == "train"]
    syn_va = [r for k in avail for r in synth[k] if r["split"] == "val"]
    if regime.startswith("synth"):
        if human:
            syn_tr, leaked = D.drop_leaks(syn_tr, human)
            if leaked:
                notes.append(f"из синтетического train убрано {leaked} текстов, совпавших с текстами людей")
        return syn_tr, syn_va
    if not human:
        raise SystemExit(f"режим {regime}: нужен --human (файл разметки людей)")
    h_tr, h_va = D.stratified_split(human, val_ratio, seed)
    if regime == "mix":
        if not avail:
            raise SystemExit("режим mix: нет ни одного синтетического корпуса")
        syn_tr, leaked = D.drop_leaks(syn_tr, human)
        if leaked:
            notes.append(f"из синтетического train убрано {leaked} текстов, совпавших с текстами людей")
        return h_tr + syn_tr, h_va
    return h_tr, h_va


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.train", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regime", choices=REGIMES)
    ap.add_argument("--synth-v3", default=str(SYNTH_V3_DIR))
    ap.add_argument("--llm-v1", default=str(LLM_V1_DIR))
    ap.add_argument("--human", nargs="*")
    ap.add_argument("--probe-v2", default=str(PROBE_V2_DIR), help="независимый тест вне шаблонов — только оценка")
    ap.add_argument("--not-complaint", choices=("drop", "other"), default="drop")
    ap.add_argument("--val-ratio", type=float, default=0.15)
    ap.add_argument("--min-human", type=int, default=200)
    ap.add_argument("--model-name", help="имя HF или путь (по умолчанию FacebookAI/xlm-roberta-base)")
    ap.add_argument("--set", action="append", help="параметр TrainConfig key=value")
    ap.add_argument("--experiments", help="results/experiments.json — взять k-fold оценку рецепта на людях")
    ap.add_argument("--out", default=str(ARTIFACTS_DIR / "final"))
    ap.add_argument("--smoke", action="store_true", help="быстрая проверка конвейера (не результат)")
    args = ap.parse_args(argv)

    from ml.civic_classifier_v2 import transformer as T
    from ml.civic_classifier_v2.evaluate import evaluate_set

    cfg = TrainConfig()
    if args.model_name:
        cfg = cfg.override([f"model_name={json.dumps(args.model_name)}"])
    if args.smoke:
        cfg = cfg.override([f"{k}={json.dumps(v)}" for k, v in SMOKE_OVERRIDES.items()])
    cfg = cfg.override(args.set)
    labels = L.labels()
    notes: list[str] = []

    synth = {}
    for key, path, evidence in (("synth_v3", args.synth_v3, "synthetic_template"),
                                ("llm_v1", args.llm_v1, "synthetic_llm")):
        try:
            recs, _ = D.load_corpus(Path(path), source=key, evidence=evidence, not_complaint=args.not_complaint)
            D.ensure_splits(recs, cfg.seed)
            synth[key] = recs
        except FileNotFoundError:
            synth[key] = []
    human = []
    if args.human:
        human, rep = D.load_human([Path(p) for p in args.human], not_complaint=args.not_complaint)
        print(f"люди: {len(human)} текстов; {rep}", file=sys.stderr)

    regime = args.regime or ("mix" if len(human) >= args.min_human and (synth["synth_v3"] or synth["llm_v1"])
                             else "human" if len(human) >= args.min_human
                             else "synth_all" if synth["synth_v3"] and synth["llm_v1"] else "synth_template")
    train, val = assemble(regime, synth, human, args.val_ratio, cfg.seed, notes)
    probe = []
    try:
        probe, _ = D.load_corpus(Path(args.probe_v2), source="probe_v2", evidence="synthetic_agent_written",
                                 not_complaint=args.not_complaint)
        train, leaked = D.drop_leaks(train, probe)
        if leaked:
            notes.append(f"из train убрано {leaked} текстов, совпавших с probe_v2")
    except FileNotFoundError:
        pass
    print(f"режим {regime}: train {len(train)}, val {len(val)}; модель {cfg.model_name}", file=sys.stderr)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tm = T.fit(train, val, cfg, labels, log_path=out / "train_log.jsonl", tag=f"final/{regime}")
    data_sha = T.data_fingerprint(train)
    version = f"civic-clf-v2-{slug(cfg.model_name)}-{regime}-d{data_sha[:8]}-s{cfg.seed}"

    # Оценка на людях для паспорта модели.
    human_eval: dict = {"status": "NOT_EVALUATED", "reason": "нет разметки людей"}
    if regime.startswith("synth") and len(human) >= args.min_human:
        proba = T.predict_proba(tm, [r["text"] for r in human])
        ev = evaluate_set(human, [int(i) for i in proba.argmax(axis=1)], proba, labels, grouped=False)
        human_eval = {"status": "EVALUATED", "n": ev["n"], "macro_f1": ev["macro_f1"], "accuracy": ev["accuracy"],
                      "ci": ev["ci"], "protocol": "тексты людей в обучении не участвовали"}
    elif regime in ("human", "mix"):
        human_eval = {"status": "NOT_EVALUATED", "reason": "все тексты людей в обучении; нужна k-fold оценка "
                      "рецепта из experiments.json (--experiments)"}
        if args.experiments and Path(args.experiments).exists():
            exp = json.loads(Path(args.experiments).read_text(encoding="utf-8"))
            run = (exp.get("runs") or {}).get(f"{regime}/transformer") or {}
            ev = (run.get("eval") or {}).get("human")
            if run.get("status") == "OK" and ev:
                human_eval = {"status": "EVALUATED", "n": ev["n"], "macro_f1": ev["macro_f1"],
                              "accuracy": ev["accuracy"], "ci": ev["ci"],
                              "protocol": f"оценка рецепта: {exp['meta'].get('k_folds')}-fold out-of-fold, "
                                          f"experiments.json @ {exp['meta'].get('git_sha')}"}
    elif human:
        human_eval = {"status": "NOT_EVALUATED", "reason": f"текстов людей {len(human)} < {args.min_human}"}

    # probe_v2 (R02, вне шаблонов) — только оценка итоговой модели, в обучение не входит.
    probe_eval: dict = {"status": "NOT_AVAILABLE"}
    if probe:
        proba = T.predict_proba(tm, [r["text"] for r in probe])
        ev = evaluate_set(probe, [int(i) for i in proba.argmax(axis=1)], proba, labels, grouped=False)
        probe_eval = {"status": "EVALUATED", "n": ev["n"], "macro_f1": ev["macro_f1"], "accuracy": ev["accuracy"],
                      "ci": ev["ci"], "slices": ev.get("slices"),
                      "note": "synthetic_agent_written (R02), вне шаблонов; не качество на людях"}

    meta = {"model_version": version, "regime": regime, "training_data": TRAINING_DATA[regime],
            "data_sha256": data_sha, "n_train": len(train), "n_val": len(val),
            "train_by_source": D.summary(train)["by_source"], "human_eval": human_eval, "probe_v2_eval": probe_eval,
            # Без текстов людей в обучении подсказка всегда требует проверки (как у v1).
            "review_policy": "threshold" if regime in ("human", "mix") else "always",
            "smoke": bool(args.smoke), "notes": notes}
    T.save(tm, out, meta)
    print(json.dumps({"saved": str(out), "model_version": version, "best_epoch": tm.best_epoch,
                      "best_val_macro_f1": tm.best_val_macro_f1, "threshold": tm.threshold.get("chosen"),
                      "human_eval": human_eval.get("status"), "probe_v2_macro_f1": probe_eval.get("macro_f1"),
                      "gpu_peak_gb": tm.info.get("gpu_peak_gb")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
