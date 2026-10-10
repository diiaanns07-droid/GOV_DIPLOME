"""R03 v2: таблицы для диплома и разбор ошибок (analysis.py) — без torch, на готовых результатах."""

from __future__ import annotations

import json

import r03_fixtures as F
from r03_markers import needs_sklearn
from ml.civic_classifier_v2 import analysis as A
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import RESULTS_DIR
from ml.civic_classifier_v2.evaluate import evaluate_set


def _fake_exp() -> dict:
    """Маленький experiments.json: 3 модели × режим synth_all на «probe» из фикстуры."""
    labs = L.labels()
    probe = [dict(r, group=r["id"]) for r in F.probe_like()]
    y = [labs.index(r["label"]) for r in probe]
    wrong = [(i + 1) % 12 for i in y]
    preds = {"heuristic": [labs.index("other")] * len(y), "logreg": y[:-4] + wrong[-4:], "transformer": y[:-2] + wrong[-2:]}
    runs = {}
    for m, p in preds.items():
        runs[f"synth_all/{m}"] = {"status": "OK", "eval": {"probe_v2": evaluate_set(probe, p, None, labs, False)},
                                  "train": {"n_train": 10, "n_val": 5, "epochs_run": 3, "best_epoch": 2,
                                            "best_val_macro_f1": 0.5, "seconds": 1.0, "gpu_peak_gb": None}}
    return {"labels": list(labs), "runs": runs, "meta": {"created_at": "t", "git_sha": "x"},
            "human_eval": {"status": "NOT_EVALUATED"},
            "comparisons": [{"set": "probe_v2", "title": "synth_all: трансформер − эвристика",
                             "delta": {"delta": 0.1, "low": 0.02, "high": 0.2, "share_delta_gt_0": 0.99}},
                            {"set": "human", "title": "mix: x", "delta": {"delta": 0, "low": -1, "high": 1,
                                                                         "share_delta_gt_0": 0.5}}]}


def test_tables_structure_and_csv(tmp_path):
    exp = _fake_exp()
    tables = A.build_tables(exp, {}, {}, tmp_path / "нет")              # без файлов results/ репозитория
    slugs = [t.slug for t in tables]
    assert {"t1_probe_v2_macro_f1", "t3_paired_probe_v2", "t4_per_class_probe_v2", "t5_slices_probe_v2"} <= set(slugs)
    t3 = next(t for t in tables if t.slug == "t3_paired_probe_v2")
    assert t3.rows == [["v3 + LLM: трансформер − словарь", "+0.100", "[+0.020; +0.200]", "0.99", "доказано"]]
    t4 = next(t for t in tables if t.slug == "t4_per_class_probe_v2")
    assert len(t4.rows) == 13 and t4.rows[-1][0] == "macro-F1"
    md = A.render_tables(tables, exp)
    assert "Таблица 1" in md and "NOT_EVALUATED" in md
    for t in tables:
        path = t.write_csv(tmp_path)
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")             # BOM: Excel читает кириллицу
        assert all(len(r) == len(t.header) for r in t.rows)


def test_confusions_and_magnets():
    exp = _fake_exp()
    ev = exp["runs"]["synth_all/heuristic"]["eval"]["probe_v2"]
    pairs = A.confusions(ev, L.labels(), top=3)
    assert all(p[1] == "other" and p[0] != "other" for p in pairs)
    mg = A.magnets(ev, L.labels())
    assert mg[0][0] == "other" and mg[0][1] == 24 and mg[0][2] == 2


def test_errors_never_show_human_texts(tmp_path):
    exp = _fake_exp()
    probe_rows = F.probe_like()
    preds = tmp_path / "preds.jsonl"
    rows = [{"set": "probe_v2", "id": r["id"], "true": r["label"], "pred": "other"} for r in probe_rows[:3]]
    rows.append({"set": "human", "id": probe_rows[3]["id"], "true": probe_rows[3]["label"], "pred": "other"})
    preds.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    probe_file = F.write_jsonl(tmp_path / "probe.jsonl", probe_rows)
    md = A.render_errors(exp, A.read_preds([preds]), A.load_probe(probe_file))
    assert probe_rows[0]["text"][:40] in md                              # текст probe — можно
    assert probe_rows[3]["text"][:40] not in md                          # строка human — никогда


def test_ru_title():
    assert A._ru_title("synth_template: логрегрессия − эвристика") == "шаблонная v3: логрегрессия − словарь"
    assert A._ru_title("transformer: LLM-синтетика − шаблонная синтетика").startswith("трансформер:")


def test_real_results_render_if_present(tmp_path):
    """Если в ветке есть результаты LOCAL-4 — команды отрабатывают на них без ошибок."""
    if not (RESULTS_DIR / "experiments.json").exists():
        return
    assert A.main(["tables", "--out", str(tmp_path / "t.md"), "--csv-dir", str(tmp_path / "csv")]) == 0
    assert A.main(["errors", "--out", str(tmp_path / "e.md")]) == 0
    assert "Таблица 1" in (tmp_path / "t.md").read_text(encoding="utf-8")


# ---------- перевод транслита (translit.py) ----------

FAKE_NORMALIZE = '''
def to_cyrillic(text, min_share=0.5):
    letters = [c for c in text.lower() if c.isalpha()]
    latin = [c for c in letters if "a" <= c <= "z"]
    if not letters or len(latin) < min_share * len(letters):
        return text
    return text.lower().replace("yama", "яма").replace("fonar", "фонар")
'''


def test_translit_compare_with_fake_normalize(tmp_path):
    from ml.civic_classifier_v2 import heuristic as H
    from ml.civic_classifier_v2 import translit as T
    f = tmp_path / "normalize.py"
    f.write_text(FAKE_NORMALIZE, encoding="utf-8")
    to_cyr = T.load_to_cyrillic(str(f))
    recs = [{"id": "1", "text": "na doroge yama", "label": "roads", "style": "translit"},
            {"id": "2", "text": "Во дворе не горят фонари", "label": "lighting", "style": "colloquial"},
            {"id": "3", "text": "fonar ne gorit", "label": "lighting", "style": "translit"}]
    labs = L.labels()
    raw = [labs.index(x) for x in H.predict([r["text"] for r in recs], "v1")]
    cyr_texts = [to_cyr(r["text"]) for r in recs]
    cyr = [labs.index(x) for x in H.predict(cyr_texts, "v1")]
    res = T.compare(recs, raw, cyr, [a != r["text"] for a, r in zip(cyr_texts, recs)])
    assert res["texts_changed"] == 2 and res["changed_by_style"] == {"translit": 2}   # кириллицу не трогает
    assert res["raw"]["translit_accuracy"] == 0.0 and res["to_cyrillic"]["translit_accuracy"] == 1.0
    assert res["paired_delta_cyr_minus_raw"]["delta"] > 0


def test_load_to_cyrillic_without_r04_gives_clear_error(monkeypatch):
    import builtins
    import pytest
    from ml.civic_classifier_v2 import translit as T
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("ml.civic_dedup"):
            raise ImportError("нет")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ModuleNotFoundError, match="normalize-file"):
        T.load_to_cyrillic(None)


def test_load_human_keeps_style_for_probe(tmp_path):
    from ml.civic_classifier_v2 import data as D
    recs, _ = D.load_human([F.write_jsonl(tmp_path / "p.jsonl", F.probe_like())])
    assert {r["style"] for r in recs} == {"colloquial"} and any(r["hard"] for r in recs)


# ---------- аудит меток llm_v1 ----------

def test_label_audit_flags_confident_disagreement():
    import numpy as np
    from ml.civic_classifier_v2 import label_audit as LA
    labs = L.labels()
    recs = [{"id": f"x{i}", "text": f"t{i}", "label": "other", "split": "train", "lang": "ru"} for i in range(4)]
    proba = np.full((4, 12), 0.01)
    proba[0, labs.index("noise_safety")] = 0.85                         # уверенно другая тема -> кандидат
    proba[1, labs.index("noise_safety")] = 0.55                         # не уверенно -> нет
    proba[2, labs.index("other")] = 0.9                                 # согласна с меткой -> нет
    proba[3, labs.index("waste")] = 0.7
    proba[3, labs.index("other")] = 0.25                                # p(метки) не низкая -> нет
    v3 = proba.copy()
    res = LA.audit(recs, proba, v3, low=0.2, high=0.6)
    assert res["candidates"] == 1 and res["items"][0]["id"] == "x0"
    assert res["items"][0]["suggested"] == "noise_safety" and res["items"][0]["v3_agrees"] is True
    assert res["by_label"]["other"] == {"candidates": 1, "n": 4, "share": 0.25}


def test_load_to_cyrillic_from_git_ref_reads_bytes(monkeypatch):
    """--normalize-ref: код R04 берётся через git show в байтах (без перенаправления оболочки)."""
    import subprocess
    from ml.civic_classifier_v2 import translit as T
    calls = []

    class Done:
        stdout = FAKE_NORMALIZE.encode("utf-8")

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return Done()

    monkeypatch.setattr(subprocess, "run", fake_run)
    f = T.load_to_cyrillic(git_ref="origin/claude/r14-R04")
    assert calls and calls[0][-1] == "origin/claude/r14-R04:ml/civic_dedup/normalize.py"
    assert f("na doroge yama") == "na doroge яма" and f("Яма во дворе") == "Яма во дворе"


def test_paired_from_files(tmp_path):
    rows_a = [{"set": "probe_v2", "id": str(i), "true": "roads", "pred": "roads"} for i in range(10)]
    rows_b = [dict(r, pred="other" if i < 5 else "roads") for i, r in enumerate(rows_a)]
    rows_b.append({"set": "human", "id": "h", "true": "roads", "pred": "other"})   # чужой набор не учитывается
    fa, fb = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    for f, rows in ((fa, rows_a), (fb, rows_b)):
        f.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    res = A.paired_from_files(fa, fb)
    assert res["n"] == 10 and res["macro_f1_a"] == 1.0 and res["delta"]["delta"] > 0


def test_suggest_section_precision():
    probe = {str(i): {"id": str(i)} for i in range(4)}
    preds = {"m": {"0": {"true": "roads", "pred": "roads", "score": 0.95},
                   "1": {"true": "roads", "pred": "waste", "score": 0.8},
                   "2": {"true": "other", "pred": "other", "score": 0.99},     # other не предвыбирается
                   "3": {"true": "roads", "pred": "roads", "score": 0.2}}}
    md = "\n".join(A._suggest_section(preds, probe))
    assert "| `m` | 0.3 | 50% | 50% | 4 |" in md and "| `m` | 0.9 | 25% | 100% | 4 |" in md


def test_load_table_from_bench_files(tmp_path):
    rep = {"cpu": {"cpu_count": 4}, "threads_per_request": 4, "peak_rss_mb": 509.0,
           "sequential_by_length": {"40": {"mean_ms": 10.9, "p95_ms": 14.7}, "5000": {"mean_ms": 34.9, "p95_ms": 43.5}},
           "concurrent_longest": {"length": 5000, "by_workers": {"8": {"requests_per_minute": 2342, "p95_ms": 291.6},
                                                                  "1": {"requests_per_minute": 1653, "p95_ms": 46.4}}}}
    (tmp_path / "classify_load_cloud.json").write_text(json.dumps(rep), encoding="utf-8")
    (tmp_path / "classify_load_broken.json").write_text("{}", encoding="utf-8")       # без замеров — пропускается
    t = next(t for t in A.extra_tables(tmp_path) if t.slug == "t10_classify_load")
    assert t.rows == [["cloud", "4 / 4", "10.9", "34.9 / 43.5", "1 → 1653; 8 → 2342", "292", "509"]]


def test_unpaired_delta_between_language_groups():
    from ml.civic_classifier_v2 import metrics as M
    y = [0, 1, 2, 3] * 10
    d_same = M.unpaired_delta(y, y, y, y, 4)
    assert d_same["delta"] == 0 and d_same["low"] == 0 and d_same["high"] == 0
    bad = [(v + 1) % 4 if i % 2 else v for i, v in enumerate(y)]          # половина ошибок
    d = M.unpaired_delta(y, bad, y, y, 4)
    assert d["delta"] < 0 and d["high"] < 0 and d["share_delta_gt_0"] == 0.0     # хуже — доказано
    assert M.unpaired_delta([], [], y, y, 4)["delta"] is None


def test_lang_section_counts_and_weak_cells():
    probe = {f"r{i}": {"id": f"r{i}", "lang": "ru"} for i in range(8)}
    probe.update({f"k{i}": {"id": f"k{i}", "lang": "kk"} for i in range(8)})
    rows = {i: {"true": "roads", "pred": "roads"} for i in probe}
    for i in ("k0", "k1", "k2", "k3", "k4"):
        rows[i] = {"true": "roads", "pred": "other"}                     # kk: 3 из 8 верно -> слабая ячейка
    md = "\n".join(A._lang_section({"m": rows}, probe))
    assert "| Дороги | 8 / 8 | 3 / 8 | — | 11 / 16 |" in md
    assert "Дороги / kk — 3 из 8" in md and "в ячейке 8 текстов" in md
    row = next(line for line in md.splitlines() if line.startswith("| `m` |"))
    assert row.startswith("| `m` | 1.000 (8) | 0.545 (8) | — | -0.455 [") and row.endswith("— доказано |")


def test_calibration_section_bins_and_ece():
    probe = {str(i): {"id": str(i)} for i in range(10)}
    rows = {str(i): {"true": "roads", "pred": "roads" if i < 5 else "waste", "score": 0.99} for i in range(10)}
    rows["9"] = {"true": "roads", "pred": "roads", "score": 1.0}                 # 1.0 попадает в последнюю корзину
    md = "\n".join(A._calibration_section({"m": rows}, probe))
    assert "| `m` | 0.97–1.00 | 10 | 0.99 | 60% | +0.39 | 0.391 |" in md       # самоуверенна: 0.99 против 60 %
    assert A._calibration_section({"h": {"0": {"true": "roads", "pred": "roads"}}}, {"0": {}}) == []   # без score


def test_morning_files_reach_tables(tmp_path):
    """Файлы утреннего шага (int8 на probe, перевод транслита, парная Δ) попадают в таблицы 3, 7 и 8."""
    ci = {"macro_f1": {"low": 0.75, "high": 0.86}}
    final = {"model_version": "M", "probe_v2_eval": {"macro_f1": 0.828, "ci": ci}}
    (tmp_path / "final_model_meta.json").write_text(json.dumps(final), encoding="utf-8")
    (tmp_path / "onnx_int8_on_probe_v2.json").write_text(json.dumps(
        {"model": "M", "human": {"macro_f1": 0.82, "ci": ci}}), encoding="utf-8")
    cmp_ = {"raw": {"macro_f1": 0.8, "translit_accuracy": 0.5}, "to_cyrillic": {"macro_f1": 0.81, "translit_accuracy": 0.7},
            "paired_delta_cyr_minus_raw": {"delta": 0.01, "low": -0.01, "high": 0.03}, "texts_changed": 24}
    (tmp_path / "onnx_int8_on_probe_v2_to_cyrillic.json").write_text(json.dumps(
        {"model": "other", "to_cyrillic": cmp_}), encoding="utf-8")
    (tmp_path / "paired_transformer_synth_all_vs_template.json").write_text(json.dumps(
        {"set": "probe_v2", "delta": {"delta": 0.127, "low": 0.07, "high": 0.18, "share_delta_gt_0": 1.0}}), encoding="utf-8")
    onnx = {"check": {}, "latency_cpu": {}, "verdict": {}}
    tables = {t.slug: t for t in A.build_tables(_fake_exp(), final, onnx, tmp_path)}
    assert ["трансформер: v3 + LLM − шаблонная v3", "+0.127", "[+0.070; +0.180]", "1.0", "доказано"] in tables["t3_paired_probe_v2"].rows
    t7 = {r[0]: r[1] for r in tables["t7_onnx"].rows}
    assert t7["probe_v2: macro-F1 int8 (ONNX)"] == "0.820 [0.750–0.860]"
    assert t7["probe_v2: macro-F1 PyTorch (итоговая модель)"] == "0.828 [0.750–0.860]"
    t8 = tables["t8_translit_to_cyrillic"].rows
    assert len(t8) == 1 and t8[0][0] == "трансформер (итоговая, int8) — другая модель other"   # чужая модель помечена


# ---------- объём синтетики (synth_curve.py) ----------

def test_synth_curve_subsample_is_stratified_and_deterministic():
    from collections import Counter
    from ml.civic_classifier_v2 import synth_curve as SC
    rows = F.synth_corpus()
    full = Counter(r["label"] for r in rows)
    half = SC.subsample(rows, 0.5, 1)
    assert Counter(r["label"] for r in half) == {lab: round(0.5 * n) for lab, n in full.items()}
    assert [r["id"] for r in half] == [r["id"] for r in SC.subsample(rows, 0.5, 1)]
    assert [r["id"] for r in half] != [r["id"] for r in SC.subsample(rows, 0.5, 2)]
    assert SC.subsample(rows, 1.0, 1) == rows and SC.subsample(rows, 0.0, 1) == []


@needs_sklearn
def test_synth_curve_run_small():
    from ml.civic_classifier_v2 import synth_curve as SC
    rows = F.synth_corpus()
    tr = [r for r in rows if r["split"] == "train"]
    va = [r for r in rows if r["split"] == "val"]
    v3, llm = tr[::2], tr[1::2]
    res = SC.run(v3, llm, va, F.probe_like(), seeds=[1, 2], grid=[{"C": 4.0, "class_weight": None, "keyword_scale": 1.0}],
                 log=lambda *a: None)
    a = res["llm_share"]
    assert [a[k]["n_train"] for k in ("0.0", "0.25", "0.5", "1.0")] == sorted(a[k]["n_train"] for k in a)
    assert a["0.5"]["seeds"] == 2 and a["0.0"]["seeds"] == 1 and res["total_share"]["1.0"] == a["1.0"]
    assert [p["title"] for p in res["paired"]] == ["v3 + 100 % LLM − одна v3", "v3 + 100 % LLM − v3 + 50 % LLM",
                                                   "всё v3 + LLM − половина v3 + LLM"]
    json.dumps(res)                                                       # без служебных прогнозов, сериализуется


def test_synth_curve_table_and_paired_rows(tmp_path):
    ci = {"low": 0.70, "high": 0.80}
    pt = lambda n, m, lo, hi, s: {"n_train": n, "seeds": s, "macro_f1_mean": m, "macro_f1_min": lo, "macro_f1_max": hi,  # noqa: E731
                                  "ci_first_seed": ci}
    curve = {"subsample_seeds": [1, 2, 3], "hyperparameters": "validation",
             "llm_share": {"0.0": pt(2654, 0.751, 0.751, 0.751, 1), "0.25": pt(3349, 0.79, 0.785, 0.796, 3),
                           "1.0": pt(5435, 0.797, 0.797, 0.797, 1)},
             "total_share": {"0.5": pt(2716, 0.778, 0.77, 0.78, 3), "1.0": pt(5435, 0.797, 0.797, 0.797, 1)},
             "paired": [{"title": "v3 + 100 % LLM − одна v3", "delta": {"delta": 0.046, "low": 0.007, "high": 0.087,
                                                                        "share_delta_gt_0": 0.99}},
                        {"title": "v3 + 100 % LLM − v3 + 50 % LLM", "delta": {"delta": 0.0, "low": -0.022, "high": 0.021,
                                                                              "share_delta_gt_0": 0.5}}]}
    (tmp_path / "synth_curve_probe_v2.json").write_text(json.dumps(curve), encoding="utf-8")
    tables = {t.slug: t for t in A.build_tables(_fake_exp(), {}, {}, tmp_path)}
    rows = tables["t11_synth_curve"].rows
    assert [r[0] for r in rows] == ["v3 + 0 % LLM", "v3 + 25 % LLM", "v3 + 100 % LLM", "50 % от v3 + LLM"]
    assert rows[1] == ["v3 + 25 % LLM", "3349", "0.790", "0.785–0.796", "0.700–0.800"] and rows[0][3] == "—"
    t3 = [r[0] for r in tables["t3_paired_probe_v2"].rows]
    assert "логрегрессия, доля синтетики: v3 + 100 % LLM − v3 + 50 % LLM" in t3
    assert not any("одна v3" in r for r in t3)                            # дубль Δ из experiments не добавляется
