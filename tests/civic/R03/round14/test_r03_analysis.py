"""R03 v2: таблицы для диплома и разбор ошибок (analysis.py) — без torch, на готовых результатах."""

from __future__ import annotations

import json

import r03_fixtures as F
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
    tables = A.build_tables(exp, {}, {})
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
