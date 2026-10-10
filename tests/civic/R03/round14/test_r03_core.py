"""R03 v2: категории, загрузка данных, разбиения, эвристика, метрики (без torch)."""

from __future__ import annotations

import json

import numpy as np
import pytest

import fixtures as F
from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import heuristic as H
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2 import metrics as M


# ---------- категории ----------

def test_labels_come_from_categories_file():
    raw = json.loads(L.CATEGORIES_PATH.read_text(encoding="utf-8"))
    assert L.labels() == tuple(c["id"] for c in raw["categories"])
    assert len(L.labels()) == 12 and L.labels()[-1] == "other"


@pytest.mark.parametrize("raw,expected", [
    ("roads", "roads"), ("transport_stops", "transport"), ("landscaping", "yards"), ("not_complaint", None),
    ("", None), ("skip", None), (None, None), ("какая-то", None), (" lighting ", "lighting"),
])
def test_normalize_label(raw, expected):
    assert L.normalize_label(raw) == expected


def test_not_complaint_dropped_by_default_or_mapped_on_request():
    # LABELING_GUIDE_v2 п. 5: «Не жалоба» не входит в 12 категорий и исключается из обучения и оценки.
    assert L.normalize_label("not_complaint") is None
    assert L.normalize_label("not_complaint", not_complaint="other") == "other"


# ---------- данные ----------

def test_load_corpus_skips_pairs_file_and_keeps_splits(data_dir):
    recs, rep = D.load_corpus(data_dir / "synth_v3", source="synth_v3", evidence="synthetic_template")
    assert rep["files"] == 1 and rep["records"] == len(F.synth_corpus())
    assert {r["split"] for r in recs} == {"train", "val", "test"}
    assert all(r["label"] in L.labels() for r in recs)
    # группа = шаблон: split по шаблонам, один шаблон не попадает в два сплита
    by_group = {}
    for r in recs:
        by_group.setdefault(r["group"], set()).add(r["split"])
    assert all(len(s) == 1 for s in by_group.values())


def test_load_corpus_without_split_assigns_group_split(tmp_path):
    rows = [{k: v for k, v in r.items() if k != "split"} for r in F.synth_corpus()]
    F.write_jsonl(tmp_path / "c.jsonl", rows)
    recs, _ = D.load_corpus(tmp_path / "c.jsonl", source="s", evidence="e")
    info = D.ensure_splits(recs, seed=1)
    assert info["assigned"] == len(recs)
    by_group = {}
    for r in recs:
        by_group.setdefault(r["group"], set()).add(r["split"])
    assert all(len(s) == 1 for s in by_group.values())
    recs2, _ = D.load_corpus(tmp_path / "c.jsonl", source="s", evidence="e")
    D.ensure_splits(recs2, seed=1)
    assert [r["split"] for r in recs] == [r["split"] for r in recs2]  # детерминированно


def test_missing_corpus_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        D.load_corpus(tmp_path / "nope", source="s", evidence="e")
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError):
        D.load_corpus(tmp_path / "empty", source="s", evidence="e")


def test_load_human_labeling_export(tmp_path):
    rows = F.human_like(20)
    rows[0]["label"] = "not_complaint"
    rows[1]["label"] = "skip"
    rows[2] = dict(rows[3])                       # повтор id с той же меткой
    rows[4]["text"] = rows[5]["text"]              # повтор текста с другим id
    path = F.write_jsonl(tmp_path / "h.jsonl", rows)
    path.write_text(path.read_text(encoding="utf-8") + "это не json\n\n", encoding="utf-8")
    recs, rep = D.load_human([path])
    assert rep["bad_lines"] == 1 and rep["not_complaint"] == 1
    assert rep["skipped_or_unknown_label"] == 2          # skip + not_complaint (исключён по гайду)
    assert rep["duplicate_id"] == 1 and rep["duplicate_text"] == 1
    assert all(r["id"] != rows[0]["id"] for r in recs) and recs[0]["source"] == "human"
    assert len(recs) == 20 - 1 - 1 - 1 - 1
    as_other, _ = D.load_human([path], not_complaint="other")
    assert len(as_other) == len(recs) + 1 and as_other[0]["label"] == "other"
    no_unsure, _ = D.load_human([path], drop_unsure=True)
    assert all(not r["unsure"] for r in no_unsure) and len(no_unsure) < len(recs)


def test_first_file_wins_on_conflict(tmp_path):
    a = F.human_like(5)
    b = [dict(r, label="other") for r in a]
    pa, pb = F.write_jsonl(tmp_path / "a.jsonl", a), F.write_jsonl(tmp_path / "b.jsonl", b)
    recs, rep = D.load_human([pa, pb])
    assert [r["label"] for r in recs] == [r["label"] for r in a]
    assert rep["duplicate_id_label_conflict"] == sum(r["label"] != "other" for r in a)


def test_csv_human(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("id;text;label\n1;Яма на дороге;roads\n2;Темно во дворе;lighting\n", encoding="utf-8")
    recs, _ = D.load_human([p])
    assert [(r["id"], r["label"]) for r in recs] == [("1", "roads"), ("2", "lighting")]


def test_stratified_kfold_partitions_and_stratifies():
    recs, _ = D.load_human([])
    recs = [dict(id=str(i), text=f"t{i}", label=L.labels()[i % 12], group=str(i)) for i in range(240)]
    folds = D.stratified_kfold(recs, 5, seed=3)
    flat = sorted(i for f in folds for i in f)
    assert flat == list(range(240))
    for f in folds:
        counts = np.bincount([L.labels().index(recs[i]["label"]) for i in f], minlength=12)
        assert counts.min() >= 3 and counts.max() <= 5
    assert folds == D.stratified_kfold(recs, 5, seed=3)


def test_stratified_split_keeps_singletons_in_train():
    recs = [dict(id=str(i), label="roads") for i in range(10)] + [dict(id="x", label="parking")]
    tr, va = D.stratified_split(recs, 0.2, seed=1)
    assert any(r["id"] == "x" for r in tr) and not any(r["id"] == "x" for r in va)
    assert len(va) == 2 and len(tr) == 9


def test_drop_leaks_by_normalized_text():
    train = [{"text": "Яма на дороге!"}, {"text": "Темно во дворе"}]
    kept, n = D.drop_leaks(train, [{"text": "яма  на ДОРОГЕ"}])
    assert n == 1 and kept == [{"text": "Темно во дворе"}]


def test_guess_lang():
    assert D.guess_lang("Аулада шам жанбайды, қараңғы") == "kk"
    # Известное ограничение (как у v1): казахский без специфических букв выглядит как ru.
    # Поэтому язык для срезов берётся из записи (форма/разметка), а guess_lang — только запасной.
    assert D.guess_lang("Аулада шам жанбайды") == "ru"
    assert D.guess_lang("Во дворе темно") == "ru"
    assert D.guess_lang("vo dvore temno") == "latin"
    assert D.guess_lang("123") == "unknown"


# ---------- эвристика ----------

@pytest.mark.parametrize("text,label", [
    ("Снег на тротуаре не убран", "snow_ice"),        # правило R02: снег на тротуаре -> snow_ice
    ("Яма во дворе", "roads"),                         # яма во дворе -> roads
    ("Нет света на остановке", "lighting"),            # нет света на остановке -> lighting
    ("Аулада шам жанбайды", "lighting"),
    ("Қоқыс шығарылмайды", "waste"),
    ("Нет горячей воды", "utilities"),
    ("Машины паркуются на тротуаре", "parking"),
    ("Спасибо за ремонт", "other"),
    ("абракадабра", "other"),
])
def test_heuristic_rules(text, label):
    assert H.heuristic_label(text)[0] == label


def test_heuristic_dog_stem_does_not_fire_on_verbs():
    # раньше «ит » ловило «горит »: проверяем, что окончание глагола не считается собакой
    assert H.keyword_hits("фонарь не горит ночью")["noise_safety"] == 0


# ---------- метрики ----------

def test_report_known_values():
    labs = L.labels()
    r = M.report([0, 0, 1, 1], [0, 1, 1, 1], labs)
    assert r["accuracy"] == 0.75
    # roads: P=1 R=0.5 F1=0.667; snow_ice: P=0.667 R=1 F1=0.8 -> macro 0.7333
    assert r["macro_f1"] == pytest.approx(0.7333, abs=1e-4)
    assert r["classes_in_set"] == 2
    assert r["confusion"]["rows_true_cols_pred"][0][:2] == [1, 1]


def test_empty_report_and_bootstrap():
    assert M.report([], [], L.labels())["macro_f1"] is None
    assert M.bootstrap([], [], 12)["macro_f1"]["low"] is None


def test_bootstrap_deterministic_and_contains_point():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 12, 300)
    p = np.where(rng.random(300) < 0.7, y, rng.integers(0, 12, 300))
    a = M.bootstrap(y, p, 12, n_boot=300)
    b = M.bootstrap(y, p, 12, n_boot=300)
    assert a == b
    point = M.report(y.tolist(), p.tolist(), L.labels())["macro_f1"]
    assert a["macro_f1"]["low"] <= point <= a["macro_f1"]["high"]
    g = M.bootstrap(y, p, 12, groups=[i // 10 for i in range(300)], n_boot=300)
    assert g["unit"].startswith("groups (n=30)")


def test_paired_delta_identical_is_zero():
    y = [0, 1, 2, 3, 4] * 10
    d = M.paired_delta(y, y, y, 12, n_boot=100)
    assert d["delta"] == 0 and d["low"] == 0 and d["high"] == 0


def test_choose_threshold_prefers_lowest_meeting_target():
    scores = [0.95, 0.9, 0.8, 0.6, 0.4, 0.35]
    correct = [True, True, True, False, False, True]
    res = M.choose_threshold(scores, correct, [False] * 6, 0.9)
    assert res["chosen"] == 0.65 and res["target_met"]


def test_ece_bounds():
    assert M.ece([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(0.15, abs=1e-6)
    assert M.ece([], []) is None
