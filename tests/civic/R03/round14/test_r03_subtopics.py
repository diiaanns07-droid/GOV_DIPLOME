"""R03: уточнения ↔ категории (subtopics.py) — без ML-библиотек (логрегрессия и модель v2 — только в CLI)."""

from __future__ import annotations

import r03_markers  # noqa: F401  (пути к корню репозитория)
from ml.civic_classifier_v2 import heuristic as H
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2 import subtopics as S


def test_stems_cover_every_subtopic():
    S._check_stems()
    subs = S.subtopics()
    assert len(subs) == 39 and {s["category"] for s in subs} == set(L.labels()) - {L.OTHER}   # у «Другое» чипов нет
    assert all(s["ru"] and s["kk"] for s in subs)


def test_matches_and_conjunction():
    assert S.matches("Машины паркуются на тротуаре", "sidewalk_parking")
    assert not S.matches("Снег на тротуаре не убран", "sidewalk_parking")       # «a&b»: нужны обе части
    assert S.matches("Светофор долго горит красный", "traffic_light_timing")


def test_label_check_counts_wrong_by_model():
    res = S.label_check({"всё other": lambda t: ["other"] * len(t), "словарь": lambda t: H.predict(t)})
    assert res["n"] == 78
    assert res["wrong"]["всё other"] == 78
    assert res["wrong"]["словарь"] <= 10                                       # продуктовый словарь после волны 2: 8


def test_corpus_check_home_covered_lost_and_private():
    rows = [
        {"text": "В подъезде пахнет газом", "label": "utilities"},               # чип gas в smell_air -> потерян
        {"text": "Пахнет газом на улице", "label": "smell_air"},                 # свой
        {"text": "Сломана скамейка на остановке", "label": "transport"},         # benches -> рядом (stop_shelter)
    ]
    res = S.corpus_check({"probe_v2": rows, "human": rows})
    gas, benches = res["gas"], res["benches"]
    assert (gas["n"], gas["home"], gas["lost"]) == (2, 1, 1) and gas["lost_to"] == {"utilities": 1}
    assert (benches["n"], benches["covered"], benches["lost"]) == (1, 1, 0)
    assert gas["by_set"]["human"] == {"utilities": 1, "smell_air": 1}           # люди — только в by_set
    md = S.report_md(None, res, {"what": "тест"})
    assert "газом" not in md                                                    # в отчёте нет текстов
