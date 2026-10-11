"""Волна 2 п. 4 «Что делают рядом»: вкладки, отключения, задержки, источники (R06 / объекты / пример), подписка."""
from datetime import datetime, timedelta

import pytest

from r08_helpers import NOW, TZ
from ui.civic_akim import api, nearby

DEVICE = "d-abcdefghijklmnopqrstuvwx"


def obj(i, stage, **kw):
    base = {"id": f"o-{i}", "kind": "roadworks", "title_ru": f"Объект {i}", "title_kk": None, "district": "nura",
            "stage": stage, "planned_end": "2026-10-20", "forecast_end": "2026-10-20",
            "updated_at": (NOW - timedelta(days=2)).isoformat(), "demo": False, "geometry": {"type": "Point"}}
    base.update(kw)
    return base


def outage(i, start, end, **kw):
    x = {"id": f"out-{i}", "type": "outage", "utility": "water", "district": "nura", "title_ru": "Нет воды",
         "title_kk": "Су жоқ", "start": start.isoformat(), "end": end.isoformat(), "zone_ru": "Двор",
         "source": "water", "updated_at": (NOW - timedelta(minutes=5)).isoformat(),
         "why": {"problem_ru": "Течь", "reason_ru": "Днём", "result_ru": "Напор", "inconvenience_ru": "6 часов"}}
    x.update(kw)
    return x


def feed(items=(), objects=(), **kw):
    return nearby.feed(kw.pop("district", "nura"), kw.pop("tab", None), now=NOW,
                       objects=lambda d, t: list(objects), nearby_fn=lambda district=None: list(items), **kw)


def test_example_feed_has_all_tabs_and_banner():
    f = nearby.feed("nura", now=NOW, objects=lambda d, t: [])
    assert f["sources"]["nearby"] in ("example", "r06")
    if f["sources"]["nearby"] == "example":
        assert f["demo"] is True and all(c["demo"] for c in f["items"])
        assert f["tabs"]["outages"] >= 1 and f["tabs"]["now"] >= 1 and f["tabs"]["done"] >= 1 and f["tabs"]["planned"] >= 1
        water = next(c for c in f["items"] if c["id"] == "nb-demo-water-nura")
        assert water["start"].startswith((NOW + timedelta(days=1)).date().isoformat()) and water["start"][11:16] == "10:00"
        assert [b["id"] for b in f["banners"]] == ["nb-demo-water-nura"]  # «Завтра 10–16 нет воды»
        road = next(c for c in f["items"] if c["id"] == "nb-demo-road-nura")
        assert road["delayed"] and road["delay_days"] == 7 and road["why"]["reason_ru"]  # «Зачем перекопали улицу»


@pytest.mark.parametrize("shift_h", [0, 5, 13, 23])
def test_example_is_stable_any_time_of_day(shift_h):
    f = nearby.feed("nura", now=NOW + timedelta(hours=shift_h), objects=lambda d, t: [])
    if f["sources"]["nearby"] == "example":
        assert f["tabs"]["outages"] == 1 and len(f["banners"]) == 1


def test_outage_window_and_banners():
    items = [
        outage(1, NOW - timedelta(hours=1), NOW + timedelta(hours=3)),                    # идёт сейчас
        outage(2, NOW + timedelta(hours=20), NOW + timedelta(hours=26)),                  # завтра — баннер
        outage(3, NOW + timedelta(hours=30), NOW + timedelta(hours=31)),                  # третий — только во вкладке
        outage(4, NOW - timedelta(days=1), NOW - timedelta(hours=2)),                     # закончилось — нет
        outage(5, NOW + timedelta(days=9), NOW + timedelta(days=9, hours=2)),            # через 9 дней — рано
        {**outage(6, NOW, NOW + timedelta(hours=1)), "start": None},                      # без времени — нет
    ]
    f = feed(items)
    ids = [c["id"] for c in f["items"] if c["tab"] == "outages"]
    assert ids == ["out-1", "out-2", "out-3"]
    assert [b["id"] for b in f["banners"]] == ["out-1", "out-2"]  # не больше 2
    assert f["items"][0]["active"] is True and f["items"][0]["updated_min_ago"] == 5


def test_objects_map_to_tabs_and_show_delays():
    objects = [obj(1, "construction", forecast_end="2026-11-02"), obj(2, "design"),
               obj(3, "operating", updated_at=(NOW - timedelta(days=3)).isoformat()),
               obj(4, "operating", updated_at=(NOW - timedelta(days=90)).isoformat()), obj(5, "unknown")]
    f = feed(objects=objects)
    tabs = {c["id"]: c["tab"] for c in f["items"]}
    assert tabs == {"o-1": "now", "o-2": "planned", "o-3": "done"}
    o1 = next(c for c in f["items"] if c["id"] == "o-1")
    assert o1["delayed"] and o1["delay_days"] == 13 and o1["why"] is None and o1["title_kk_missing"]
    assert o1["target"] == {"kind": "object", "id": "o-1"}
    assert [c["id"] for c in feed(objects=objects, tab="now")["items"]] == ["o-1"]


def test_r06_source_replaces_example_and_district_filter():
    items = [outage(1, NOW, NOW + timedelta(hours=1)), outage(2, NOW, NOW + timedelta(hours=1), district="esil")]
    f = feed(items)
    assert f["sources"]["nearby"] == "r06" and [c["id"] for c in f["items"]] == ["out-1"] and f["demo"] is False


def test_why_without_text_is_dropped():
    item = outage(1, NOW, NOW + timedelta(hours=1), why={"problem_ru": "", "reason_ru": None})
    assert feed([item])["items"][0]["why"] is None


@pytest.mark.parametrize("district,tab,field", [("mars", None, "district"), ("nura", "all", "tab")])
def test_bad_params(district, tab, field):
    with pytest.raises(nearby.NearbyError) as exc:
        nearby.feed(district, tab, now=NOW)
    assert exc.value.field == field


def test_subscribe_list_unsubscribe_and_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(nearby, "SUBS_PATH", tmp_path / "subs.json")
    items = [outage(1, NOW, NOW + timedelta(hours=2), updated_at=(NOW - timedelta(minutes=5)).isoformat()),
             outage(2, NOW, NOW + timedelta(hours=2), updated_at=(NOW - timedelta(days=3)).isoformat())]
    nearby.subscribe(DEVICE, "district", "nura", now=NOW - timedelta(days=1))
    assert nearby.subscriptions(DEVICE) == [{"scope": "district", "id": "nura", "since": (NOW - timedelta(days=1)).isoformat()}]
    ups = nearby.updates_for(DEVICE, now=NOW, objects=lambda d, t: [], nearby_fn=lambda district=None: items)
    assert [u["id"] for u in ups] == ["out-1"]  # out-2 обновлено до подписки
    nearby.subscribe(DEVICE, "district", "nura", on=False)
    assert nearby.subscriptions(DEVICE) == []


@pytest.mark.parametrize("device,scope,sid,field", [
    ("short", "district", "nura", "device_id"), (DEVICE, "planet", "nura", "scope"),
    (DEVICE, "district", "mars", "id"), (DEVICE, "item", "../x", "id"), (None, "district", "nura", "device_id")])
def test_subscribe_validation(tmp_path, device, scope, sid, field):
    with pytest.raises(nearby.NearbyError) as exc:
        nearby.subscribe(device, scope, sid, path=tmp_path / "s.json")
    assert exc.value.field == field and not (tmp_path / "s.json").exists()


def test_subscription_limit(tmp_path):
    path = tmp_path / "s.json"
    for i in range(nearby.MAX_SUBS_PER_DEVICE):
        nearby.subscribe(DEVICE, "item", f"w-{i}", path=path)
    with pytest.raises(nearby.NearbyError) as exc:
        nearby.subscribe(DEVICE, "item", "w-extra", path=path)
    assert exc.value.status == 429


def test_api_routes(tmp_path, monkeypatch):
    monkeypatch.setattr(nearby, "SUBS_PATH", tmp_path / "subs.json")
    code, body = api.handle_get("/api/civic/v2/nearby", {"district": ["nura"], "tab": ["outages"]})
    assert code == 200 and all(c["tab"] == "outages" for c in body["items"]) and set(body["tabs"]) == set(nearby.TABS)
    assert api.handle_get("/api/civic/v2/nearby", {"district": "mars"})[0] == 400
    code, body = api.handle_post("/api/civic/v2/nearby/subscriptions", {"device_id": DEVICE, "scope": "district", "id": "nura"})
    assert code == 200 and body["items"][0]["id"] == "nura"
    assert api.handle_get("/api/civic/v2/nearby/subscriptions", {"device_id": DEVICE})[1]["items"][0]["scope"] == "district"
    assert api.handle_get("/api/civic/v2/nearby/updates", {"device_id": DEVICE})[0] == 200
    assert api.handle_post("/api/civic/v2/nearby/subscriptions", {"device_id": "x"})[0] == 400
    code, body = api.handle_post("/api/civic/v2/nearby/subscriptions", {"device_id": DEVICE, "scope": "district", "id": "nura", "on": False})
    assert code == 200 and body["items"] == []


def test_example_texts_are_bilingual_and_generic():
    import json
    raw = json.loads(nearby.FIXTURE.read_text("utf-8"))
    from ui.civic_akim import routing
    for x in raw["items"]:
        assert x["title_ru"] and x["title_kk"]
        for k in ("problem", "reason", "result", "inconvenience"):
            assert x["why"][f"{k}_ru"] and x["why"][f"{k}_kk"], (x["id"], k)
        if x["type"] == "outage":
            assert x["source"] in routing.SERVICES and x["zone_ru"] and x["zone_kk"] and "when" in x
    assert raw["_meta"]["synthetic"] is True
