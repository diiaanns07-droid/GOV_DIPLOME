"""R09 + настоящие соседи: R12 engine.civic_geo (/targets) и R04 ui.civic_ml_api (/classify, /similar).

В ветке R09 этих пакетов нет — тесты пропускаются. В общей сборке R01 (или в интеграционном дереве, RUN.txt п.6)
проверяют стык: цели R12 принимает запись R09, ячейки совпадают, R04 находит жалобу R09 для «Я тоже».
Подсказку категории (suggest) R04 даёт только со словарём/моделью R03 (ml.civic_classifier_v2); без R03 — категория
есть, suggest=false, и форма R09 открывает сетку категорий (R01 INTEGRATION §9: тест падал в дереве R04 без R03).
"""

import importlib.util
import random

import pytest

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service
from ui.civic_feedback.v2 import record as rec

HAS_GEO = importlib.util.find_spec("engine.civic_geo") is not None
HAS_ML = importlib.util.find_spec("ui.civic_ml_api") is not None
HAS_R03 = importlib.util.find_spec("ml.civic_classifier_v2") is not None


@pytest.mark.skipif(not HAS_GEO, reason="нет engine.civic_geo (R12) в этом дереве")
def test_r12_targets_are_accepted_by_complaint_record():
    import engine.civic_geo as geo
    random.seed(14)
    seen_kinds = set()
    for _ in range(300):
        lon, lat = random.uniform(71.36, 71.50), random.uniform(51.08, 51.20)
        for cand in geo.targets(lon, lat, None)["candidates"]:
            target = dict(cand["target"], **({"approximate": True} if cand.get("approximate") else {}))
            parsed = rec.parse_target(target)                    # строгий формат CONTRACT §4, без legacy
            assert parsed["id"] == cand["target"]["id"] and parsed.get("label_ru") and parsed.get("label_kk")
            seen_kinds.add(parsed["kind"])
            if parsed["id"].startswith("cell-"):
                assert cand["approximate"] is True
                assert rec.cell_id(*cand["point"]) == parsed["id"]   # та же сетка, что у R09
    assert seen_kinds == {"object", "segment", "area"}


@pytest.mark.skipif(not HAS_ML, reason="нет ui.civic_ml_api (R04) в этом дереве")
def test_r04_finds_r09_complaint_for_metoo(tmp_path):
    import time
    import ui.civic_ml_api as ml
    store = ComplaintStore(tmp_path / "c.sqlite3")
    ml.connect_store(ComplaintsV2Service(store))
    stop = {"kind": "object", "id": "osm-node-5078375591", "label_ru": "Остановка «Бухар жырау»"}
    point = [71.4277518, 51.0988262]
    record, _ = store.create({"text": "Павильон остановки сломан, нет крыши", "category": "transport",
                              "point": point, "target": stop}, "dev-aaaaaaaaaaaaaaaa")
    store.metoo(record["id"], "dev-bbbbbbbbbbbbbbbb")
    deadline = time.time() + 10
    matches = []
    while time.time() < deadline and not matches:          # R04 считает новую жалобу в фоне по событию
        matches = ml.similar("Аялдаманың павильоны сынған, шатыры жоқ", point=point, days=14)["matches"]
        time.sleep(0.2)
    assert matches and matches[0]["complaint_id"] == record["id"] and matches[0]["people"] == 2
    assert "text" not in matches[0]                          # чужие тексты не уходят жителю
    assert ml.similar("Сломана скамейка во дворе", point=point, days=14)["matches"] == []


@pytest.mark.skipif(not HAS_ML, reason="нет ui.civic_ml_api (R04) в этом дереве")
def test_r04_classify_suggests_only_with_r03():
    import ui.civic_ml_api as ml
    c = ml.classify("Павильон остановки сломан, нет крыши")
    assert c["category"] == "transport" and isinstance(c["suggest"], bool)
    if HAS_R03:
        assert c["suggest"] is True                          # с R03 форма сама выбирает «Остановки и транспорт»
