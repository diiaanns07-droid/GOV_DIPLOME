"""R07 раунд 15+ (П3, сцена 0): «Показать на карте» у задачи «ИИ-разбора» R04 ведёт на цель, жалоб по которой
за период нет. /heat/target отвечает 404, как раньше, но с place — подписью и точкой места, чтобы карта подлетела
к нему и честно сказала «жалоб нет». Чужой или кривой id — 404 без place, кэш разбора целей не растёт.

Запуск: python -m pytest tests/civic/R07/test_r07_place.py -q
"""
from datetime import datetime, timedelta, timezone

import pytest

from ui.civic_heat import HeatService
from ui.civic_heat import api, demo_seed, geo
from ui.civic_heat.targets import TargetResolver

TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=TZ)
TARGETS = demo_seed.load_targets()
SEG_ID = next(k for k, v in TARGETS.items() if v["kind"] == "segment")
YARD_ID = next(k for k, v in TARGETS.items() if v["kind"] == "area" and k.startswith("yard-"))
URL = "/api/civic/v2/heat/target"


def svc(records=()):
    return HeatService(source=lambda since: list(records), resolver=TargetResolver(graph_path=None, use_r12=False),
                       clock=lambda: NOW)


def old_complaint(tid, kind, age_days):
    at = (NOW - timedelta(days=age_days)).isoformat()
    return {"id": "c-old", "created_at": at, "text": "текст", "lang": "ru", "category": "roads",
            "point": geo.anchor_of(TARGETS[tid]["geometry"]), "target": {"kind": kind, "id": tid}, "district": "nura",
            "status": "new", "status_history": [{"at": at, "status": "new"}], "metoo": 0, "demo": True}


@pytest.mark.parametrize("kind,tid", [("segment", SEG_ID), ("area", YARD_ID)])
def test_known_place_without_complaints_gets_label_and_anchor(kind, tid):
    st, body = api.handle_get(URL, {"kind": [kind], "id": [tid]}, service=svc())
    assert st == 404 and body["error"] == "not_found"      # как раньше: карточки нет — жалоб нет
    place = body["place"]
    assert place["kind"] == kind and place["id"] == tid
    assert place["label_ru"] and place["label_kk"]
    want = geo.anchor_of(TARGETS[tid]["geometry"])
    assert place["anchor"] == pytest.approx(want, abs=1e-5)
    assert place["geometry"]["type"] == TARGETS[tid]["geometry"]["type"]   # контур места на карте


def test_complaints_outside_period_still_give_place():
    s = svc([old_complaint(SEG_ID, "segment", 40)])
    st, body = api.handle_get(URL, {"kind": ["segment"], "id": [SEG_ID], "days": ["30"]}, service=s)
    assert st == 404 and body["place"]["id"] == SEG_ID
    st, body = api.handle_get(URL, {"kind": ["segment"], "id": [SEG_ID], "days": ["90"]}, service=s)
    assert st == 200 and body["item"]["count"] == 1        # с жалобой в периоде — обычная карточка


@pytest.mark.parametrize("kind,tid", [
    ("segment", "nope"),                                   # нет такой цели
    ("object", "osm-node-1"),                              # вид id правильный, но места нет
    ("district", "nura"),                                  # район — не место для перелёта
    ("point", SEG_ID),
    ("segment", SEG_ID + "'; drop table x"),               # мусор в id
    ("area", "../../etc/passwd"),
    ("area", "yard-" + "9" * 40),
])
def test_unknown_or_bad_target_has_no_place(kind, tid):
    st, body = api.handle_get(URL, {"kind": [kind], "id": [tid]}, service=svc())
    assert st == 404 and "place" not in body


def test_place_does_not_grow_resolver_cache():
    s = svc()
    before = len(s.resolver._cache)
    for i in range(50):
        s.place("object", f"osm-node-{10_000_000 + i}")    # чужие id снаружи
    assert s.place("segment", SEG_ID)
    assert len(s.resolver._cache) == before
