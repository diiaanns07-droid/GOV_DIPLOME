"""R03 v2: протокол эксперимента (нет утечки теста), сквозной прогон на крошечной модели, ONNX, predict."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import fixtures as F
from conftest import needs_ml, needs_onnx, needs_sklearn
from ml.civic_classifier_v2 import experiments as E
from ml.civic_classifier_v2 import labels as L


def _args(data_dir: Path, tmp: Path, *extra: str) -> list[str]:
    # Явные пути: тесты не должны зависеть от того, лежат ли настоящие корпуса R02 в ml/datasets/.
    return ["--synth-v3", str(data_dir / "synth_v3"), "--llm-v1", str(tmp / "no_llm"), "--v1-in-v2", str(tmp / "no_v1"),
            "--human", str(data_dir / "human.jsonl"), "--results", str(tmp / "results"),
            "--artifacts", str(tmp / "art"), *extra]


# ---------- протокол: тест не участвует в обучении и выборе ----------

def test_protocol_no_leak(data_dir, tmp_path, monkeypatch):
    calls = []

    def spy(name, train, val, eval_sets, cfg, labels, log_path, tag):
        calls.append({"tag": tag, "train": {r["id"] for r in train}, "val": {r["id"] for r in val},
                      "train_splits": {r["split"] for r in train if r["source"] != "human"},
                      "eval": {s: [r["id"] for r in recs] for s, recs in eval_sets.items()}})
        return {s: ([0] * len(recs), None) for s, recs in eval_sets.items()}, {"n_train": len(train),
                                                                              "n_val": len(val)}

    monkeypatch.setattr(E, "run_model", spy)
    E.main(_args(data_dir, tmp_path, "--min-human", "50", "--folds", "3", "--models", "heuristic",
                 "--regimes", "synth_template", "synth_llm", "human", "mix"))
    human_ids = {r["id"] for r in F.human_like()}
    synth = {r["id"]: r for r in F.synth_corpus()}
    syn_calls = [c for c in calls if c["tag"].startswith("synth_template")]
    assert len(syn_calls) == 1
    c = syn_calls[0]
    assert not (c["train"] | c["val"]) & human_ids                     # люди не в обучении
    assert all(synth[i]["split"] == "train" for i in c["train"])        # только train-сплит
    assert all(synth[i]["split"] == "val" for i in c["val"])
    assert set(c["eval"]["human"]) == human_ids
    for regime in ("human", "mix"):
        fold_calls = [c for c in calls if c["tag"].startswith(regime + "/")]
        assert len(fold_calls) == 3
        seen = set()
        for c in fold_calls:
            ev = set(c["eval"]["human"])
            assert not ev & (c["train"] | c["val"])                      # фолд не видел свои тексты
            assert c["val"] <= human_ids                                 # validation — только люди
            seen |= ev
            assert c["train_splits"] <= {"train"}                        # синтетический test не в обучении
        assert seen == human_ids                                         # каждый текст предсказан ровно раз
    mix_train = fold_calls[0]["train"]
    assert any(i in synth for i in mix_train)                            # в смеси есть синтетика
    res = json.loads((tmp_path / "results" / "experiments.json").read_text(encoding="utf-8"))
    assert res["runs"]["synth_llm/heuristic"]["status"] == "NOT_RUN"  # llm_v1 нет -> честно NOT_RUN
    assert any("mix: синтетика только" in n for n in res["notes"])


def test_human_fraction_limits_only_training(data_dir, tmp_path, monkeypatch):
    seen = []

    def spy(name, train, val, eval_sets, cfg, labels, log_path, tag):
        seen.append((sum(r["source"] == "human" for r in train), len(val), len(eval_sets["human"])))
        return {s: ([0] * len(r), None) for s, r in eval_sets.items()}, {"n_train": len(train), "n_val": len(val)}

    monkeypatch.setattr(E, "run_model", spy)
    E.main(_args(data_dir, tmp_path, "--min-human", "50", "--folds", "3", "--models", "heuristic",
                 "--regimes", "human", "--human-fraction", "0.5", "--name", "lc"))
    full = []
    monkeypatch.setattr(E, "run_model", lambda name, train, val, sets, *a, **k: (
        full.append(len(train)) or {s: ([0] * len(r), None) for s, r in sets.items()},
        {"n_train": len(train), "n_val": len(val)}))
    E.main(_args(data_dir, tmp_path, "--min-human", "50", "--folds", "3", "--models", "heuristic",
                 "--regimes", "human", "--name", "full"))
    assert all(h < f for (h, _, _), f in zip(seen, full))           # обучающих людей меньше
    assert sum(n for _, _, n in seen) == 60                          # оценка — по всем текстам
    res = json.loads((tmp_path / "results" / "lc.json").read_text(encoding="utf-8"))
    assert res["meta"]["human_fraction"] == 0.5


def test_human_eval_not_evaluated_below_200(data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(E, "run_model", lambda name, train, val, sets, *a, **k: (
        {s: ([0] * len(r), None) for s, r in sets.items()}, {"n_train": len(train), "n_val": len(val)}))
    E.main(_args(data_dir, tmp_path, "--models", "heuristic", "--regimes", "synth_template", "human"))
    res = json.loads((tmp_path / "results" / "experiments.json").read_text(encoding="utf-8"))
    assert res["human_eval"]["status"] == "NOT_EVALUATED"
    assert res["runs"]["human/heuristic"]["status"] == "NOT_EVALUATED"
    assert "human" not in res["runs"]["synth_template/heuristic"]["eval"]
    md = (tmp_path / "results" / "RESULTS.md").read_text(encoding="utf-8")
    assert "NOT_EVALUATED" in md


# ---------- базовая логрегрессия ----------

@needs_sklearn
def test_logreg_learns_and_selects_on_val(data_dir):
    from ml.civic_classifier_v2 import data as D
    from ml.civic_classifier_v2 import logreg
    recs, _ = D.load_corpus(data_dir / "synth_v3", source="synth_v3", evidence="x")
    tr = [r for r in recs if r["split"] == "train"]
    va = [r for r in recs if r["split"] == "val"]
    model, sel = logreg.fit(tr, va, seed=1, grid=logreg.GRID[:4])
    assert len(sel["candidates"]) == 4 and sel["chosen"] in [c["hyper"] for c in sel["candidates"]]
    hum = F.human_like()
    pred = model.predict([r["text"] for r in hum])
    acc = np.mean([L.labels()[p] == r["label"] for p, r in zip(pred, hum)])
    assert acc > 0.5
    assert model.predict_proba(["яма"]).shape == (1, 12)


def test_v1_features_match_v1_definition():
    from ml.civic_classifier_v2.logreg import v1_features, v1_normalize
    assert v1_normalize("Звоните +7 701 123 45 67, Ёлка №12!") == "звоните phone елка 0"
    f = v1_features("яма")
    assert f["c: я"] == 1 and f["c:яма "] == 1 and f["w:яма"] == 1


# ---------- сквозной прогон на крошечной модели ----------

@needs_ml
@needs_sklearn
def test_experiments_end_to_end_smoke(data_dir, tiny_model, tmp_path):
    E.main(_args(data_dir, tmp_path, "--smoke", "--min-human", "50", "--folds", "2",
                 "--model-name", str(tiny_model), "--regimes", "synth_template", "human", "mix", "--fail-fast"))
    res = json.loads((tmp_path / "results" / "smoke.json").read_text(encoding="utf-8"))
    assert res["meta"]["mode"] == "smoke"
    for regime in ("synth_template", "human", "mix"):
        for m in ("heuristic", "logreg", "transformer"):
            run = res["runs"][f"{regime}/{m}"]
            assert run["status"] == "OK", run
            ev = run["eval"]["human"]
            assert ev["n"] == 60 and ev["ci"]["macro_f1"]["low"] is not None
            assert len(ev["confusion"]["rows_true_cols_pred"]) == 12
    assert res["runs"]["synth_template/transformer"]["eval"]["synth_test_template"]["ci"]["unit"].startswith("groups")
    assert res["comparisons"] and res["best_on_human"]
    md = (tmp_path / "results" / "smoke.md").read_text(encoding="utf-8")
    assert "ПРОВЕРКА КОНВЕЙЕРА" in md and "| v2: трансформер |" in md
    # Приватность: тексты людей не попадают ни в results/, ни в файлы прогнозов.
    blobs = [p.read_text(encoding="utf-8") for p in (tmp_path / "results").iterdir()]
    preds = list((tmp_path / "art" / "experiments" / "smoke").glob("*__*.jsonl"))
    assert preds                                                    # прогнозы smoke — в своей подпапке
    blobs += [p.read_text(encoding="utf-8") for p in preds]
    for r in F.human_like():
        assert all(r["text"] not in b for b in blobs)


# ---------- итоговая модель, ONNX int8, predict ----------

@pytest.fixture(scope="module")
def exported(data_dir, tiny_model, tmp_path_factory):
    from ml.civic_classifier_v2 import export_onnx, train
    if not (pytest.importorskip("onnx") and pytest.importorskip("onnxruntime")):
        pytest.skip("нет onnx")
    out = tmp_path_factory.mktemp("final")
    # Режим human: val из тех же шаблонов, что и train, — крошечная модель успевает чему-то научиться.
    # (В фикстуре синтетики val — невиданные казахские шаблоны: там крошечная модель не обобщает,
    # и ранняя остановка честно возвращает веса 1-й эпохи.)
    rc = train.main(["--smoke", "--regime", "human", "--human", str(data_dir / "human.jsonl"), "--min-human", "50",
                     "--synth-v3", str(out / "none"), "--llm-v1", str(out / "none"),
                     "--model-name", str(tiny_model), "--out", str(out / "final"),
                     "--set", "epochs=30", "--set", "patience=30", "--set", "lr=0.003"])
    assert rc == 0
    rc = export_onnx.main(["--model", str(out / "final"), "--out", str(out / "onnx"), "--texts",
                           str(data_dir / "human.jsonl"), "--n", "60", "--results", str(out / "onnx_export.json"),
                           "--min-int8-agreement", "0.0"])
    report = json.loads((out / "onnx_export.json").read_text(encoding="utf-8"))
    return out, rc, report


@needs_ml
@needs_onnx
def test_onnx_export_matches_pytorch(exported):
    out, rc, rep = exported
    assert rc == 0
    assert rep["verdict"]["fp32_matches_torch"] == "PASS"
    assert rep["check"]["onnx_fp32_vs_torch"]["argmax_agreement"] == 1.0
    assert rep["check"]["onnx_int8_vs_torch"]["max_abs_diff_prob"] < 0.2
    assert rep["latency_cpu"]["int8_all_threads"]["n"] == 60
    assert not (out / "onnx" / "model.onnx").exists() and (out / "onnx" / "model.int8.onnx").exists()
    assert not (out / "onnx" / "model.onnx.data").exists()
    assert rep["check"]["onnx_fp32_vs_torch_batch1"]["argmax_agreement"] == 1.0
    assert (out / "onnx" / "tokenizer.json").exists() and (out / "onnx" / "birge_meta.json").exists()


@needs_ml
@needs_onnx
def test_predict_contract_and_policy(exported):
    from ml.civic_classifier_v2.predict import Classifier
    out, _, _ = exported
    clf = Classifier.load(out / "onnx")
    assert clf.backend == "onnx:model.int8.onnx"
    res = clf.classify("Не горят фонари во дворе уже неделю")
    assert set(res) == {"category", "score", "needs_review", "model_version", "top3"}  # CONTRACT §7
    assert res["category"] in L.labels() and 0 <= res["score"] <= 1
    assert len(res["top3"]) == 3 and res["top3"][0]["category"] == res["category"]
    assert res["top3"][0]["score"] >= res["top3"][1]["score"] >= res["top3"][2]["score"]
    # рецепт не проверен на людях (нет --experiments) -> подсказка всегда требует проверки
    assert clf.always_review and res["needs_review"] is True
    empty = clf.classify("  !!! ")
    assert empty["category"] == "other" and empty["needs_review"] and empty["top3"] == []
    with pytest.raises(TypeError):
        clf.classify(None)
    long = clf.classify("яма " * 3000)                                   # обрезка, без падения
    assert long["category"] in L.labels()
    torch_clf = Classifier.load(out / "final", backend="torch")
    texts = [r["text"] for r in F.human_like()[:20]]
    assert (torch_clf.predict_proba(texts).argmax(1) == Classifier.load(
        out / "onnx").predict_proba(texts).argmax(1)).mean() >= 0.8


@needs_ml
@needs_onnx
def test_learned_model_beats_chance_on_synthetic_val(exported):
    from ml.civic_classifier_v2.transformer import META_NAME
    out, _, _ = exported
    meta = json.loads((out / "final" / META_NAME).read_text(encoding="utf-8"))
    assert meta["best_val_macro_f1"] > 0.2          # цикл обучения действительно учится (случайно ≈ 0.08)
    assert meta["review_policy"] == "threshold" and meta["training_data"] == "real_human_labeled"
    assert meta["human_eval"]["status"] == "NOT_EVALUATED"
    assert meta["history"] and meta["best_epoch"] >= 1 and 0.3 <= meta["threshold"] <= 1.0


def test_review_policy_from_meta(tmp_path):
    from ml.civic_classifier_v2.predict import Classifier
    base = {"labels": list(L.labels()), "model_version": "x", "threshold": 0.5}
    synth = Classifier(tmp_path, dict(base, review_policy="always", human_eval={"status": "EVALUATED"}), None, "-")
    assert synth.always_review                       # без людей в обучении — всегда проверка
    unchecked = Classifier(tmp_path, dict(base, review_policy="threshold"), None, "-")
    assert unchecked.always_review                   # люди в обучении, но рецепт не оценён
    trusted = Classifier(tmp_path, dict(base, review_policy="threshold", human_eval={"status": "EVALUATED"}),
                         None, "-")
    assert not trusted.always_review


def test_predict_unavailable_and_label_mismatch(tmp_path):
    from ml.civic_classifier_v2.predict import Classifier, ModelUnavailable
    with pytest.raises(ModelUnavailable):
        Classifier.load(tmp_path)
    meta = {"labels": ["a", "b"], "model_version": "x"}
    with pytest.raises(ModelUnavailable):
        Classifier(tmp_path, meta, None, "none")


def test_class_weights():
    pytest.importorskip("torch")
    from ml.civic_classifier_v2.transformer import class_weights
    w = class_weights([0, 0, 0, 1], 3, "sqrt_inv")
    assert w[2] == 0 and w[1] > w[0] and abs((w[0] + w[1]) / 2 - 1) < 1e-3
    assert class_weights([0, 1], 3, "none") == [1.0, 1.0, 0.0]


def test_env_dir_overrides_default(tmp_path, monkeypatch):
    from ml.civic_classifier_v2 import predict as P
    monkeypatch.setenv(P.ENV_DIR, str(tmp_path / "custom"))
    with pytest.raises(P.ModelUnavailable) as exc:
        P.Classifier.load()
    assert "custom" in str(exc.value)


@needs_ml
def test_small_data_trains_min_steps_before_early_stop(tiny_model):
    """Только люди (~200 текстов = единицы шагов на эпоху): ранняя остановка не должна сработать на разгоне."""
    from ml.civic_classifier_v2 import data as D
    from ml.civic_classifier_v2 import transformer as T
    from ml.civic_classifier_v2.config import TrainConfig
    recs = [dict(r, group=r["id"], split=None, source="human") for r in F.human_like(48)]
    tr, va = D.stratified_split(recs, 0.25, 1)
    cfg = TrainConfig(model_name=str(tiny_model), fp16=False, max_length=32, batch_size=8, grad_accum=1,
                      epochs=2, patience=1, min_train_steps=20, max_epochs=6, lr=1e-3)
    tm = T.fit(tr, va, cfg, L.labels())
    spe = tm.info["steps_per_epoch"]
    assert tm.info["epochs_planned"] == min(6, -(-20 // spe)) > 2       # эпох прибавилось
    ran_steps = tm.history[-1]["steps"]
    assert ran_steps >= min(20, spe * 6)                                  # остановка не раньше min_train_steps
    assert 1 <= tm.best_epoch <= len(tm.history)
