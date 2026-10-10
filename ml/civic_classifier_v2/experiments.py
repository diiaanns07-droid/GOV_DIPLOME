"""Эксперимент диплома: режимы обучения × модели, оценка на ОДНОМ наборе текстов людей.

Режимы (на чём обучаем):
  synth_v1       — старый корпус v1 (R08, раунд 12), переразмеченный R02 в 12 категорий (ml/datasets/v1_in_v2/);
  synth_template — шаблонная синтетика v3 (R02, ml/datasets/synth_v3/data/), split по шаблонам;
  synth_llm      — LLM-синтетика llm_v1 (R02, ml/datasets/llm_v1/);
  synth_all      — обе синтетики вместе;
  human          — только тексты людей: стратифицированный k-fold, прогнозы вне фолда;
  mix            — синтетика (обе) + люди из обучающих фолдов, те же фолды.
Модели: heuristic (словарь, не обучается), logreg (метод v1), transformer (v2, xlm-roberta-base).
Плюс без обучения: LLM zero-shot (файл прогнозов от zeroshot.py) и v1 как есть (если пакет v1 доступен).

Оценочные наборы: тексты людей (главный), probe_v2 — независимый тест вне шаблонов (300 текстов, написаны
агентом R02 вручную, ml/datasets/probe_v2/), синтетический test каждого корпуса (справочно).

Протокол честности:
  * тексты людей = оценочный набор; в режимах synth_* они не участвуют ни в обучении, ни в выборе;
  * в human/mix для фолда f: обучение на остальных фолдах, ВНУТРИ них — стратифицированная validation
    (val_ratio) для ранней остановки, порога и гиперпараметров логрегрессии; фолд f только предсказывается;
  * из обучения удаляются тексты, совпадающие с оценочными (после нормализации);
  * probe_v2 — только оценка во всех режимах; в human/mix его предсказывает ансамбль моделей фолдов
    (среднее вероятностей), потому что «одной» модели в k-fold нет;
  * синтетический test — справочно, отдельной таблицей.

Запуск (ноутбук, venv с CUDA; точные команды — research/round-14-results/R03/RUN.txt):
    python -m ml.civic_classifier_v2.experiments --human private/labels_owner.jsonl
    python -m ml.civic_classifier_v2.experiments --human private/labels_owner.jsonl --seeds 3
    python -m ml.civic_classifier_v2.experiments --models heuristic logreg     # без GPU, минуты
Результат: ml/civic_classifier_v2/results/experiments.json + RESULTS.md (в Git), прогнозы и логи —
ml/civic_classifier_v2/artifacts/experiments/ (вне Git).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import heuristic
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import (ARTIFACTS_DIR, LLM_V1_DIR, REPO_ROOT, RESULTS_DIR, SMOKE_OVERRIDES,
                                           PROBE_V2_DIR, SYNTH_V3_DIR, V1_IN_V2_DIR, TrainConfig)
from ml.civic_classifier_v2.evaluate import evaluate_set, write_results
from ml.civic_classifier_v2.metrics import paired_delta

REGIMES = ("synth_v1", "synth_template", "synth_llm", "synth_all", "human", "mix")
# Какие синтетические корпуса входят в режим. synth_all и mix — новые корпуса раунда 14 (v3 + LLM);
# старый v1→v2 идёт отдельным столбцом для сравнения генераторов.
REGIME_SOURCES = {"synth_v1": ["v1_in_v2"], "synth_template": ["synth_v3"], "synth_llm": ["llm_v1"],
                  "synth_all": ["synth_v3", "llm_v1"], "human": [], "mix": ["synth_v3", "llm_v1"]}
TEST_SET_OF = {"synth_v3": "synth_test_template", "llm_v1": "synth_test_llm", "v1_in_v2": "synth_test_v1"}
MODELS = ("heuristic", "logreg", "transformer")
MIN_HUMAN = 200  # prompts/R03.txt: оценка на людях — если размечено ≥ 200 текстов


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ---------- одна модель: обучить на train/val и предсказать наборы ----------

def run_model(name: str, train: list[dict], val: list[dict], eval_sets: dict[str, list[dict]],
              cfg: TrainConfig, labels: tuple[str, ...], log_path: Path, tag: str) -> tuple[dict, dict]:
    """-> ({набор: (pred_idx, proba|None)}, сведения об обучении)."""
    index = {lab: i for i, lab in enumerate(labels)}
    out, info = {}, {"n_train": len(train), "n_val": len(val)}
    t0 = time.time()
    if name == "heuristic":
        for s, recs in eval_sets.items():
            # Базовая модель эксперимента — замороженный словарь v1 (результаты c19b889 воспроизводимы).
            out[s] = ([index[x] for x in heuristic.predict([r["text"] for r in recs], version="v1")], None)
    elif name == "logreg":
        from ml.civic_classifier_v2 import logreg
        model, sel = logreg.fit(train, val, cfg.seed, labels=labels)
        info["selection"] = sel
        for s, recs in eval_sets.items():
            proba = model.predict_proba([r["text"] for r in recs]) if recs else np.zeros((0, len(labels)))
            out[s] = ([int(i) for i in proba.argmax(axis=1)], proba)
    elif name == "transformer":
        from ml.civic_classifier_v2 import transformer as T
        tm = T.fit(train, val, cfg, labels, log_path=log_path, tag=tag)
        info.update({"best_epoch": tm.best_epoch, "best_val_macro_f1": tm.best_val_macro_f1,
                     "epochs_run": len(tm.history), "threshold": tm.threshold.get("chosen"),
                     "gpu_peak_gb": tm.info.get("gpu_peak_gb"), "env": {k: tm.info.get(k) for k in
                                                                       ("torch", "transformers", "cuda", "gpu")}})
        for s, recs in eval_sets.items():
            proba = T.predict_proba(tm, [r["text"] for r in recs])
            out[s] = ([int(i) for i in proba.argmax(axis=1)], proba)
        T.free(tm)
    else:
        raise ValueError(name)
    info["seconds"] = round(time.time() - t0, 1)
    return out, info


# ---------- данные ----------

def load_sources(args, notes: list[str]) -> dict:
    """Загружает всё доступное; отсутствующее помечается NOT_AVAILABLE (а не падает)."""
    src: dict = {}
    for key, path, source, evidence in (("synth_v3", args.synth_v3, "synth_v3", "synthetic_template"),
                                        ("llm_v1", args.llm_v1, "llm_v1", "synthetic_llm"),
                                        ("v1_in_v2", args.v1_in_v2, "v1_in_v2", "synthetic_template_v1")):
        try:
            recs, rep = D.load_corpus(Path(path), source=source, evidence=evidence,
                                      not_complaint=args.not_complaint)
            split_info = D.ensure_splits(recs, args.seed)
            if split_info["assigned"]:
                notes.append(f"{key}: в корпусе нет поля split — назначен {split_info['rule']}")
            src[key] = {"records": recs, "load_report": rep}
        except FileNotFoundError as exc:
            src[key] = {"records": [], "status": "NOT_AVAILABLE", "reason": str(exc)}
    try:
        recs, rep = D.load_corpus(Path(args.probe_v2), source="probe_v2", evidence="synthetic_agent_written",
                                  not_complaint=args.not_complaint)
        for r in recs:
            r["split"] = "test"  # набор только для проверки, что бы ни стояло в файле
        src["probe_v2"] = {"records": recs, "load_report": rep}
    except FileNotFoundError as exc:
        src["probe_v2"] = {"records": [], "status": "NOT_AVAILABLE", "reason": str(exc)}
    humans = [Path(p) for p in (args.human or [])]
    if humans:
        recs, rep = D.load_human(humans, not_complaint=args.not_complaint, drop_unsure=args.drop_unsure)
        src["human"] = {"records": recs, "load_report": rep, "files": [p.name for p in humans]}
    else:
        src["human"] = {"records": [], "status": "NOT_AVAILABLE", "reason": "не передан --human"}
    return src


def load_exclude_ids(path: str | None) -> set[str]:
    """id синтетических текстов, которые не брать в обучение: JSONL/JSON-список или {"candidate_ids": [...]}
    (например, кандидаты на шумную метку из label_audit.py). Оценочные наборы не трогаются."""
    if not path:
        return set()
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if isinstance(data, dict):
        data = data.get("candidate_ids") or data.get("ids") or []
    return {str(x["id"] if isinstance(x, dict) else x) for x in data}


def _split(recs: list[dict], name: str) -> list[dict]:
    return [r for r in recs if r["split"] == name]


# ---------- главный цикл ----------

def run(args) -> dict:
    labels = L.labels()
    index = {lab: i for i, lab in enumerate(labels)}
    notes: list[str] = []
    cfg = TrainConfig(seed=args.seed)
    if args.model_name:
        cfg = cfg.override([f"model_name={json.dumps(args.model_name)}"])
    if args.smoke:
        cfg = cfg.override([f"{k}={json.dumps(v)}" for k, v in SMOKE_OVERRIDES.items()])
    cfg = cfg.override(args.set)
    # Главный прогон — artifacts/experiments/, остальные (smoke, lc_0.5, …) — в подпапке со своим именем,
    # чтобы не перезаписать прогнозы и лог главного.
    out_art = Path(args.artifacts) / "experiments"
    if args.name != "experiments":
        out_art = out_art / args.name
    out_art.mkdir(parents=True, exist_ok=True)
    log_path = out_art / "train_log.jsonl"

    src = load_sources(args, notes)
    exclude_ids = load_exclude_ids(args.exclude_train_ids)
    syn = {k: src[k]["records"] for k in ("synth_v3", "llm_v1", "v1_in_v2")}
    human = src["human"]["records"]
    if args.max_human and len(human) > args.max_human:
        human = human[:args.max_human]

    human_ok = len(human) >= args.min_human
    if human and not human_ok:
        notes.append(f"текстов людей {len(human)} < {args.min_human}: оценка на людях NOT_EVALUATED "
                     f"(порог меняется --min-human, тогда результат помечается как предварительный)")
    if human_ok and args.min_human < MIN_HUMAN:
        notes.append(f"ПРЕДВАРИТЕЛЬНО: порог --min-human {args.min_human} < {MIN_HUMAN}")
    eval_human = human if human_ok else []

    # Оценочные наборы, общие для всех режимов.
    eval_sets_common = {}
    if eval_human:
        eval_sets_common["human"] = eval_human
    probe = src["probe_v2"]["records"]
    if probe:
        eval_sets_common["probe_v2"] = probe
    for key, set_name in TEST_SET_OF.items():
        if syn[key]:
            eval_sets_common[set_name] = _split(syn[key], "test")
    all_eval = [r for recs in eval_sets_common.values() for r in recs]

    results: dict = {
        "format": "birge-clf-v2-experiments", "labels": list(labels), "regimes": [], "runs": {},
        "meta": {"created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "git_sha": git_sha(), "model_name": cfg.model_name, "seed": cfg.seed, "seeds": args.seeds,
                 "mode": "smoke" if args.smoke else "full", "k_folds": args.folds, "val_ratio": args.val_ratio,
                 "human_fraction": args.human_fraction,
                 "exclude_train_ids": (Path(args.exclude_train_ids).name if args.exclude_train_ids else None),
                 "excluded_ids_n": len(exclude_ids), "heuristic_dict": "v1", "heuristic_dict_sha256": heuristic.DICT_V1_SHA256,
                 "env_note": args.env_note, "train_config": cfg.to_dict()},
        "data": {}, "notes": notes,
    }
    for key in ("synth_v3", "llm_v1", "v1_in_v2", "probe_v2", "human"):
        s = src[key]
        results["data"][key] = (D.summary(s["records"]) | {"load_report": s.get("load_report")}
                                if s["records"] else {"status": s.get("status", "EMPTY"), "reason": s.get("reason", "")})
    if eval_human:
        results["human_eval"] = {
            "status": "EVALUATED", "n": len(eval_human), "files": src["human"].get("files"),
            "annotators": "см. файлы разметки", "protocol":
                f"режимы с людьми — стратифицированный {args.folds}-fold, прогнозы вне фолда; "
                f"внутренняя validation {int(args.val_ratio * 100)}% обучающей части фолда"}
    else:
        results["human_eval"] = {"status": "NOT_EVALUATED",
                                 "reason": f"размечено {len(human)} текстов людей (нужно ≥ {args.min_human})"
                                 if human else "файл разметки людей не передан (--human)"}

    # Фолды людей — одни и те же для human и mix (парные сравнения корректны).
    folds = D.stratified_kfold(eval_human, args.folds, args.seed) if eval_human else []

    store: dict[str, dict] = {}  # run_key -> {set: pred list} для парных сравнений
    for regime in args.regimes:
        need_syn = REGIME_SOURCES[regime]
        avail = [k for k in need_syn if syn[k]]
        if regime.startswith("synth") and len(avail) < len(need_syn):
            for m in args.models:
                results["runs"][f"{regime}/{m}"] = {"regime": regime, "model": m, "status": "NOT_RUN",
                                                    "reason": "нет корпуса: " + ", ".join(set(need_syn) - set(avail))}
            results["regimes"].append(regime)
            continue
        if regime in ("human", "mix") and not eval_human:
            for m in args.models:
                results["runs"][f"{regime}/{m}"] = {"regime": regime, "model": m, "status": "NOT_EVALUATED",
                                                    "reason": results["human_eval"]["reason"]}
            results["regimes"].append(regime)
            continue
        if regime == "mix" and not avail:
            notes.append("mix: нет ни одного синтетического корпуса — режим совпал бы с human, пропущен")
            continue
        results["regimes"].append(regime)
        if regime == "mix" and len(avail) < len(need_syn):
            notes.append(f"mix: синтетика только {avail} (нет {sorted(set(need_syn) - set(avail))})")
        syn_train = [r for k in avail for r in _split(syn[k], "train")]
        if exclude_ids:
            before = len(syn_train)
            syn_train = [r for r in syn_train if r["id"] not in exclude_ids]
            if before != len(syn_train):
                notes.append(f"{regime}: из синтетического train исключено по --exclude-train-ids {before - len(syn_train)}")
        syn_val = [r for k in avail for r in _split(syn[k], "val")]
        syn_train, leaked = D.drop_leaks(syn_train, all_eval)
        if leaked:
            notes.append(f"{regime}: из синтетического train убрано {leaked} текстов, совпавших с оценочными")

        for m in args.models:
            key = f"{regime}/{m}"
            seeds = [args.seed + i for i in range(args.seeds if m == "transformer" else 1)]
            seed_runs = []
            entry: dict = {"regime": regime, "model": m, "status": "OK"}
            try:
                for si, seed in enumerate(seeds):
                    cfg_s = cfg.override([f"seed={seed}"])
                    preds: dict[str, tuple[list[int], np.ndarray | None]] = {}
                    train_info: dict = {}
                    if regime.startswith("synth"):
                        sets = {k: v for k, v in eval_sets_common.items() if v}
                        p, info = run_model(m, syn_train, syn_val, sets, cfg_s, labels, log_path, f"{key}/s{seed}")
                        preds.update(p)
                        train_info = info
                    else:
                        # k-fold по людям: каждый текст предсказан моделью, которая его не видела.
                        oof_pred = [0] * len(eval_human)
                        oof_proba = np.zeros((len(eval_human), len(labels)))
                        has_proba = True
                        fold_infos = []
                        # probe_v2: каждый фолд предсказывает весь набор; итог — среднее вероятностей
                        # (или голосование, если вероятностей нет — у словаря все фолды одинаковы).
                        probe_proba = np.zeros((len(probe), len(labels)))
                        probe_votes = np.zeros((len(probe), len(labels)))
                        for f, test_idx in enumerate(folds):
                            test_set = set(test_idx)
                            rest = [eval_human[i] for i in range(len(eval_human)) if i not in test_set]
                            tr_h, va_h = D.stratified_split(rest, args.val_ratio, seed + f)
                            # Кривая обучения: в обучение идёт только доля текстов людей; val и оценка — полные.
                            tr_h = D.stratified_subsample(tr_h, args.human_fraction, seed + f)
                            tr = tr_h + (syn_train if regime == "mix" else [])
                            # validation — только люди (целевая область); синтетика лишь в обучении.
                            fold_eval = {"human": [eval_human[i] for i in test_idx]}
                            if probe:
                                fold_eval["probe_v2"] = probe
                            p, info = run_model(m, tr, va_h, fold_eval, cfg_s, labels, log_path,
                                                f"{key}/s{seed}/fold{f}")
                            pr, pb = p["human"]
                            for j, i in enumerate(test_idx):
                                oof_pred[i] = pr[j]
                                if pb is not None:
                                    oof_proba[i] = pb[j]
                            has_proba = has_proba and pb is not None
                            if probe:
                                ppr, ppb = p["probe_v2"]
                                probe_votes[np.arange(len(probe)), ppr] += 1
                                if ppb is not None:
                                    probe_proba += ppb
                            fold_infos.append(info)
                        preds["human"] = (oof_pred, oof_proba if has_proba else None)
                        if probe:
                            if has_proba:
                                pp = probe_proba / len(folds)
                                preds["probe_v2"] = ([int(i) for i in pp.argmax(axis=1)], pp)
                            else:
                                preds["probe_v2"] = ([int(i) for i in probe_votes.argmax(axis=1)], None)
                        train_info = {"folds": fold_infos, "n_train_mean": round(float(np.mean(
                            [fi["n_train"] for fi in fold_infos])), 1)}
                        if probe:
                            train_info["probe_v2_prediction"] = (f"ансамбль {len(folds)} моделей фолдов "
                                                                 "(среднее вероятностей)")
                    evals = {}
                    for s, (pr, pb) in preds.items():
                        recs = eval_sets_common.get(s) or []
                        evals[s] = evaluate_set(recs, pr, pb, labels, grouped=s.startswith("synth_test"))
                    if si == 0:
                        entry["eval"] = evals
                        entry["train"] = train_info | {"synthetic_sources": avail}
                        store[key] = {s: pr for s, (pr, _) in preds.items()}
                        _save_preds(out_art / f"{key.replace('/', '__')}.jsonl", preds, eval_sets_common, labels)
                    seed_runs.append({"seed": seed, "human_macro_f1": (evals.get("human") or {}).get("macro_f1"),
                                      "probe_v2_macro_f1": (evals.get("probe_v2") or {}).get("macro_f1"),
                                      "synth_test_template_macro_f1":
                                          (evals.get("synth_test_template") or {}).get("macro_f1")})
                if len(seeds) > 1:
                    entry["seed_runs"] = seed_runs
            except Exception as exc:  # один упавший прогон не должен ронять весь эксперимент
                entry = {"regime": regime, "model": m, "status": "FAILED", "reason": f"{type(exc).__name__}: {exc}"}
                notes.append(f"{key}: FAILED — {type(exc).__name__}: {exc}")
                if args.fail_fast:
                    raise
            results["runs"][key] = entry
            # Промежуточное сохранение: если ноутбук уснёт, готовое не потеряется.
            write_results(results, Path(args.results), args.name)

    # Модели без обучения: zero-shot LLM (файл прогнозов) и v1 как есть.
    no_train_sets = {s: eval_sets_common[s] for s in ("human", "probe_v2") if eval_sets_common.get(s)}
    if no_train_sets:
        if args.zeroshot_preds:
            results["runs"]["none/zeroshot_llm"] = _external_preds(Path(args.zeroshot_preds), no_train_sets, labels,
                                                                   store, "none/zeroshot_llm")
        else:
            results["runs"]["none/zeroshot_llm"] = {"status": "NOT_RUN", "reason": "нет --zeroshot-preds "
                                                    "(запуск zeroshot.py только локально с ключом API)"}
        if args.v1:
            results["runs"]["none/v1_shipped"] = _v1_shipped(no_train_sets, labels, store)

    # Модели, которые в этом прогоне не запускались (например, трансформер в облаке без весов), — явно NOT_RUN.
    for regime in results["regimes"]:
        for m in MODELS:
            results["runs"].setdefault(f"{regime}/{m}", {"regime": regime, "model": m, "status": "NOT_RUN",
                                                         "reason": args.not_run_reason})
    results["comparisons"] = _comparisons(store, eval_sets_common, labels, args.regimes)
    best = [(k, v["eval"]["human"]["macro_f1"]) for k, v in results["runs"].items()
            if v.get("status") == "OK" and (v.get("eval") or {}).get("human")]
    results["best_on_human"] = max(best, key=lambda kv: kv[1])[0] if best else None
    best_p = [(k, v["eval"]["probe_v2"]["macro_f1"]) for k, v in results["runs"].items()
              if v.get("status") == "OK" and (v.get("eval") or {}).get("probe_v2")]
    results["best_on_probe"] = max(best_p, key=lambda kv: kv[1])[0] if best_p else None
    write_results(results, Path(args.results), args.name)
    return results


def _save_preds(path: Path, preds: dict, sets: dict, labels) -> None:
    """Прогнозы по id (без текстов) — в artifacts/, для повторных сравнений."""
    with open(path, "w", encoding="utf-8") as fh:
        for s, (pr, pb) in preds.items():
            for r, p, i in zip(sets.get(s) or [], pr, range(len(pr))):
                row = {"set": s, "id": r["id"], "true": r["label"], "pred": labels[p]}
                if pb is not None:
                    row["score"] = round(float(pb[i, p]), 4)
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _external_preds(path: Path, sets: dict[str, list[dict]], labels, store: dict, key: str) -> dict:
    """Прогнозы из файла {id, label} (zeroshot.py / llm_label.py R02) на людях и probe_v2.
    Оценка на пересечении id; покрытие указывается; в парных сравнениях — только при полном покрытии."""
    if not path.exists():
        return {"status": "NOT_RUN", "reason": f"нет файла {path.name}"}
    rows, _ = D.read_rows(path)
    by_id = {}
    for r in rows:
        lab = L.normalize_label(r.get("label") or r.get("pred"))
        by_id[str(r.get("id"))] = lab if lab else L.OTHER  # нераспознанный ответ LLM = other
    index = {lab: i for i, lab in enumerate(labels)}
    entry: dict = {"regime": "none", "status": "OK", "eval": {}, "coverage": {}, "source_file": path.name}
    notes = []
    for set_name, recs_all in sets.items():
        recs = [r for r in recs_all if r["id"] in by_id]
        entry["coverage"][set_name] = f"{len(recs)}/{len(recs_all)}"
        if not recs:
            continue
        pred = [index[by_id[r["id"]]] for r in recs]
        entry["eval"][set_name] = evaluate_set(recs, pred, None, labels, False)
        if len(recs) == len(recs_all):
            store.setdefault(key, {})[set_name] = pred
        else:
            notes.append(f"{set_name}: покрытие {len(recs)}/{len(recs_all)} — в парных сравнениях не участвует")
    if not entry["eval"]:
        return {"status": "NOT_RUN", "reason": "в файле нет id из оценочных наборов", "coverage": entry["coverage"]}
    if notes:
        entry["note"] = "; ".join(notes)
    return entry


def _v1_shipped(sets: dict[str, list[dict]], labels, store: dict) -> dict:
    """v1 (6 категорий) как есть: метка v1 -> v2. Нужен пакет ml/civic_classifier (ветка wizardly-ptolemy @ 14c3384)."""
    try:
        from ml.civic_classifier import classify  # noqa: WPS433 — необязательная зависимость
    except Exception as exc:  # пакета v1 нет в этой сборке
        return {"status": "NOT_RUN", "reason": f"пакет v1 недоступен ({type(exc).__name__})"}
    m = L.v1_to_v2()
    index = {lab: i for i, lab in enumerate(labels)}
    entry = {"regime": "none", "status": "OK", "eval": {},
             "note": "v1 умеет только 6 категорий; snow_ice, waste, utilities, smell_air, noise_safety, parking недостижимы"}
    for set_name, recs in sets.items():
        pred = [index[m.get(classify(r["text"]).get("label"), L.OTHER)] for r in recs]
        store.setdefault("none/v1_shipped", {})[set_name] = pred
        entry["eval"][set_name] = evaluate_set(recs, pred, None, labels, False)
    return entry


def _comparisons(store: dict, sets: dict[str, list[dict]], labels, regimes) -> list[dict]:
    """Парные бутстрэп-сравнения на одном и том же наборе: люди (по текстам) и синтетический test
    (по шаблонам). Главные — на людях; синтетические — справочно."""
    k = len(labels)
    index = {lab: i for i, lab in enumerate(labels)}
    out = []
    for set_name, recs in sets.items():
        if not recs:
            continue
        y = [index[r["label"]] for r in recs]
        groups = [r["group"] for r in recs] if set_name.startswith("synth_test") else None

        def add(a: str, b: str, title: str):
            pa, pb = (store.get(a) or {}).get(set_name), (store.get(b) or {}).get(set_name)
            if pa is not None and pb is not None and len(pa) == len(pb) == len(y):
                out.append({"set": set_name, "a": a, "b": b, "title": title, "n": len(y),
                            "delta": paired_delta(y, pa, pb, k, groups)})

        for r in regimes:
            add(f"{r}/transformer", f"{r}/logreg", f"{r}: трансформер − логрегрессия")
            add(f"{r}/transformer", f"{r}/heuristic", f"{r}: трансформер − эвристика")
            add(f"{r}/logreg", f"{r}/heuristic", f"{r}: логрегрессия − эвристика")
        for m in ("transformer", "logreg"):
            add(f"synth_template/{m}", f"synth_v1/{m}", f"{m}: синтетика v3 − синтетика v1→v2")
            add(f"synth_llm/{m}", f"synth_template/{m}", f"{m}: LLM-синтетика − шаблонная синтетика")
            add(f"mix/{m}", f"synth_all/{m}", f"{m}: смесь − только синтетика (вклад текстов людей)")
            add(f"mix/{m}", f"human/{m}", f"{m}: смесь − только люди (вклад синтетики)")
        add("none/zeroshot_llm", "mix/transformer", "LLM zero-shot − трансформер (смесь)")
        add("none/zeroshot_llm", "synth_all/transformer", "LLM zero-shot − трансформер (только синтетика)")
        add("none/zeroshot_llm", "synth_template/transformer", "LLM zero-shot − трансформер (синтетика v3)")
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.experiments", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synth-v3", default=str(SYNTH_V3_DIR), help="файл или папка шаблонной синтетики v3")
    ap.add_argument("--llm-v1", default=str(LLM_V1_DIR), help="файл или папка LLM-синтетики llm_v1")
    ap.add_argument("--v1-in-v2", default=str(V1_IN_V2_DIR), help="корпус v1, переразмеченный в 12 категорий")
    ap.add_argument("--probe-v2", default=str(PROBE_V2_DIR),
                    help="независимый тест вне шаблонов (R02, 300 текстов) — только оценка")
    ap.add_argument("--human", nargs="*", help="JSONL разметки людей (первым — файл владельца)")
    ap.add_argument("--regimes", nargs="+", default=list(REGIMES), choices=REGIMES)
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=MODELS)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--val-ratio", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=TrainConfig().seed)
    ap.add_argument("--seeds", type=int, default=1, help="повторы трансформера с seed, seed+1, …")
    ap.add_argument("--min-human", type=int, default=MIN_HUMAN)
    ap.add_argument("--max-human", type=int, default=0, help="для отладки: взять первые N текстов людей")
    ap.add_argument("--exclude-train-ids", help="JSON/JSONL с id синтетических текстов, исключаемых из обучения "
                    "(например results/LLM_LABEL_AUDIT.json — опыт «чистка шумных меток»)")
    ap.add_argument("--human-fraction", type=float, default=1.0,
                    help="кривая обучения: доля текстов людей в обучении фолда (0.25, 0.5…); оценка — на всех. "
                         "Запускать с --regimes human mix и своим --name (например lc_050)")
    ap.add_argument("--not-complaint", choices=("drop", "other"), default="drop")
    ap.add_argument("--drop-unsure", action="store_true", help="исключить тексты, где разметчик сомневался")
    ap.add_argument("--model-name", help="трансформер: имя HF или путь (по умолчанию FacebookAI/xlm-roberta-base)")
    ap.add_argument("--set", action="append", help="параметр TrainConfig key=value (можно несколько)")
    ap.add_argument("--zeroshot-preds", help="JSONL {id,label} от zeroshot.py")
    ap.add_argument("--v1", action="store_true", help="добавить строку «v1 как есть» (нужен пакет ml/civic_classifier)")
    ap.add_argument("--smoke", action="store_true", help="быстрая проверка конвейера (не результат)")
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("--results", default=str(RESULTS_DIR))
    ap.add_argument("--name", default="experiments", help="имя файла результатов (experiments -> RESULTS.md)")
    ap.add_argument("--artifacts", default=str(ARTIFACTS_DIR))
    ap.add_argument("--env-note", default="", help="описание среды для отчёта: «RTX 4060 Laptop, Windows 11, …»")
    ap.add_argument("--not-run-reason", default="не запускалась в этом прогоне (--models)",
                    help="пояснение для моделей, не вошедших в --models")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke and args.name == "experiments":
        args.name = "smoke"  # проверка конвейера не перезаписывает настоящие результаты
    res = run(args)
    print(json.dumps({"best_on_human": res.get("best_on_human"), "best_on_probe": res.get("best_on_probe"),
                      "human_eval": res["human_eval"]["status"],
                      "runs": {k: v.get("status") for k, v in res["runs"].items()}}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
