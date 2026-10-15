"""R06 раунд 15, задача 5: seed_world — своя часть демо-мира R02 (CONTRACT §11): работы, идеи, демо-проекты из идей.

Фикстура — часть настоящего world_v1.json R02 (времена относительные: модуль материализует их сам, как требует SCHEMA §4).
Полный мир — test_full_world_if_present (если файл мира есть в сборке).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from r06r14_helpers import call, context
from ui.civic_store import seed_world
from ui.civic_store import v2 as v2mod
from ui.civic_store import world as world_mod
from ui.civic_store.demo_r14 import seed_r14_demo

HERE = Path(__file__).parent
PART = json.loads((HERE / "fixtures" / "world_r06_part.json").read_text(encoding="utf-8"))
ASTANA = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 11, 9, 0, tzinfo=ASTANA)     # те же сутки, что часы тестов (11 окт 04:00 UTC)


@pytest.fixture(autouse=True)
def world_mode(monkeypatch):
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")


@pytest.fixture
def fake_r12(monkeypatch):
    """Граф улиц R12 — подмена: у освещения линия по «ребру» рядом, у площадки — улица рядом."""
    from engine.civic_geo import api as geo_api

    def snap(lon, lat, kind=None):
        return {"edge_id": "osm-w555-0", "street_ru": "улица Сарыкум", "street_kk": "Сарыкум көшесі",
                "near_street_ru": None, "near_street_kk": None}
    monkeypatch.setattr(geo_api, "street_snap", snap)
    monkeypatch.setattr(world_mod.works_v2, "edges_lookup", lambda ids: {
        "osm-w555-0": ([(71.4180, 51.1979), (71.4185, 51.1981)], "улица Сарыкум", "Сарыкум көшесі", "a", "b")})


def test_seed_world_part(stack, fake_r12):
    svc, v2 = stack
    report = seed_world(svc.db.path, PART, NOW, service=svc)
    assert report["inserted"] == 9 and report["skipped"] == 0 and report["invalid"] == 0, report
    assert report["projects"] == 2 and report["notes"] == []
    # повтор — ничего не дублирует
    again = seed_world(svc.db.path, PART, NOW, service=svc)
    assert again["inserted"] == 0 and again["skipped"] == 9 and again["projects"] == 2
    # работы — для календаря R12 (§5.6), сцена 8: асфальт в мае, сети в июле на той же улице
    works = {r["id"]: r for r in v2.nearby.works_v2(include_outages=True)["items"]}
    surface, dig = works["w-w15-002"], works["w-w15-003"]
    assert surface["kind"] == "surface" and dig["kind"] == "dig" and surface["source"] == "demo"
    assert surface["starts_on"][5:] == "05-04" and dig["starts_on"][5:] == "07-06" and surface["starts_on"][:4] == "2027"
    assert surface["street_ru"] == "улица Баян Сулу" and set(dig["segments"]) <= set(surface["segments"]) | set(dig["segments"])
    assert surface["geometry"]["type"] == "MultiLineString" and surface["link"] == "#works/w-w15-002"
    closure = works["w-w15-008"]
    assert closure["kind"] == "closure" and closure["type"] == "work"
    outage = works["w-w15-040"]
    assert outage["type"] == "outage" and outage["service"] == "water" and outage["kind"] is None
    # то же для «Рядом» R08 (формат раунда 14): тексты обоих языков, «Пример»
    nearby = {i["id"]: i for i in v2.nearby.items("nura")}
    assert nearby["w-w15-040"]["title_kk"] and nearby["w-w15-040"]["why"]["problem_ru"] and nearby["w-w15-040"]["demo"]
    # идеи: голоса, статусы, «сделайте вместе», проекты из идей
    ideas = {i["id"]: i for i in v2.ideas.list({"status": ["review,voting,project,rejected"]}, None, staff=True)["items"]}
    assert ideas["idea-w15-01"]["votes"] == 34 and ideas["idea-w15-01"]["initiative"]["id"] == "i-w15-10"
    assert ideas["idea-w15-01"]["self_doable"] is True and ideas["idea-w15-01"]["topic"] == "greening"
    assert ideas["idea-w15-10"]["status"] == "review" and ideas["idea-w15-10"]["votes"] == 0
    assert ideas["idea-w15-08"]["status"] == "rejected" and ideas["idea-w15-08"]["reason_ru"]
    playground, lighting = ideas["idea-w15-06"], ideas["idea-w15-07"]
    assert playground["status"] == "project" and playground["project"]["kind"] == "playground"
    assert lighting["status"] == "project" and lighting["project"]["kind"] == "lighting"
    projects = {p["id"]: p for p in v2.proposals.list({}, None)["items"]}
    light = projects[lighting["project"]["id"]]
    assert light["geometry"]["type"] == "LineString" and light["demo"] is True
    assert light["idea"]["id"] == "idea-w15-07" and light["title_ru"] == "Освещение улицы Сарыкум"
    # в публичном списке — без идеи «на проверке»
    public = [i["id"] for i in call(v2, "GET", "/ideas")["body"]["data"]["items"]]
    assert "idea-w15-10" not in public and "idea-w15-01" in public


def test_reset_returns_demo_records_to_world_state(stack, fake_r12):
    svc, v2 = stack
    seed_world(svc.db.path, PART, NOW, service=svc)
    with svc.db.write() as conn:   # «репетиция» поменяла демо-записи
        conn.execute("UPDATE civic_ideas SET status = 'rejected' WHERE id = 'idea-w15-01'")
        conn.execute("DELETE FROM civic_idea_votes WHERE idea_id = 'idea-w15-01'")
        conn.execute("UPDATE civic_nearby_items SET removed = 1 WHERE id = 'w-w15-002'")
    kept = seed_world(svc.db.path, PART, NOW, service=svc)
    assert kept["reset"] == 0 and kept["skipped"] == 9           # без reset — не трогаем
    report = seed_world(svc.db.path, PART, NOW + timedelta(days=1), reset=True, service=svc)
    assert report["reset"] == 9 and report["inserted"] == 0 and report["projects"] == 2
    idea = v2.ideas.get("idea-w15-01", staff=True)["item"]
    assert idea["status"] == "voting" and idea["votes"] == 34
    assert "w-w15-002" in {r["id"] for r in v2.nearby.works_v2()["items"]}


def test_real_records_are_never_reset(stack, staff, fake_r12):
    svc, v2 = stack
    why = {"problem": "п", "reason": "п", "result": "р", "inconvenience": "н"}
    made = staff.call("POST", "/works", {"type": "work", "status": "planned", "district": "nura", "lang": "ru",
                                         "title": "Настоящая работа", "planned_end": "2026-11-20", "why": why})
    assert made["status"] == 201
    real_id = made["body"]["data"]["item"]["id"]
    clash = {"works": [dict(PART["works"][0], id=real_id)], "ideas": []}
    report = seed_world(svc.db.path, clash, NOW, reset=True, service=svc)
    assert report["skipped"] == 1 and report["reset"] == 0
    assert v2.nearby.get_staff(real_id)["item"]["texts"]["title_ru"] == "Настоящая работа"


def test_final4_demo_is_retired_only_in_world_mode(stack, monkeypatch, fake_r12):
    svc, v2 = stack
    monkeypatch.setenv("CIVIC_DEMO_WORLD", "0")
    seed_r14_demo(svc)                                           # база FINAL-4: 6 демо-идей и 8 записей «Рядом»
    assert any(i["id"].startswith("nb-demo") for i in v2.nearby.items(None))
    monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")
    report = seed_world(svc.db.path, PART, NOW, service=svc)
    assert report["retired"] == 14
    assert not any(i["id"].startswith("nb-demo") for i in v2.nearby.items(None))
    public = call(v2, "GET", "/ideas")["body"]["data"]["items"]
    assert all(i["id"].startswith("idea-w15") for i in public)
    assert len(v2.proposals.list({}, None)["items"]) == 7        # 5 проектов FINAL-4 (шаг 5) + 2 из мира
    # в режиме мира seed_r14_demo сам не добавляет идеи и «Рядом» FINAL-4
    again = seed_r14_demo(svc)
    assert again["ideas"][0]["action"] == "skipped" and again["nearby"][0]["action"] == "skipped"


def test_lighting_project_without_street_graph_stays_checking(stack, monkeypatch):
    svc, v2 = stack
    from engine.civic_geo import api as geo_api

    def no_graph(*a, **k):
        raise RuntimeError("нет графа")
    monkeypatch.setattr(geo_api, "street_snap", no_graph)
    part = {"works": [], "ideas": [i for i in PART["ideas"] if i["id"] == "idea-w15-07"]}
    report = seed_world(svc.db.path, part, NOW, service=svc)
    assert report["inserted"] == 1 and report["projects"] == 0 and "освещение без линии" in report["notes"][0]
    assert v2.ideas.get("idea-w15-07", staff=True)["item"]["status"] == "checking"


@pytest.mark.parametrize("bad", [
    {"id": "w bad id", "type": "work"},
    {"id": "w-x1", "type": "work", "district": "mars", "service": "water", "title_ru": "x", "ends_on": "2026-10-20"},
    {"id": "w-x2", "type": "work", "district": "nura", "service": "Водоканал АО", "title_ru": "x", "ends_on": "2026-10-20"},
    {"id": "w-x3", "type": "work", "district": "nura", "service": "water", "title_ru": "x", "starts_on": "2026-10-25",
     "ends_on": "2026-10-20"},
    {"id": "w-x4", "type": "outage", "district": "nura", "service": "water", "title_ru": "x", "utility": "internet",
     "starts_at": "2026-10-12T10:00:00+05:00", "ends_at": "2026-10-12T12:00:00+05:00"},
])
def test_invalid_world_records_are_counted_not_stored(stack, bad):
    svc, v2 = stack
    report = seed_world(svc.db.path, {"works": [bad], "ideas": []}, NOW, service=svc)
    assert report["invalid"] == 1 and report["inserted"] == 0


def test_empty_or_foreign_world(stack):
    svc, v2 = stack
    assert seed_world(svc.db.path, {}, NOW, service=svc)["source"] == "empty"
    assert seed_world(svc.db.path, None, NOW, service=svc)["inserted"] == 0


def test_materialize_fallback_matches_schema_rules():
    now = datetime(2026, 10, 15, 17, 0, tzinfo=ASTANA)
    got = world_mod._walk({"a": {"day": -12}, "b": {"in_hours": 20}, "c": {"season": {"month": 5, "day": 4}},
                           "d": {"day_at": {"day": 2, "hour": 18, "minute": 30}},
                           "e": {"next_weekday": {"weekday": 5, "hour": 10, "minute": 0}}, "f": "как есть"}, now)
    assert got == {"a": "2026-10-03", "b": "2026-10-16T13:00:00+05:00", "c": "2027-05-04",
                   "d": "2026-10-17T18:30:00+05:00", "e": "2026-10-17T10:00:00+05:00", "f": "как есть"}


def test_full_world_if_present(stack):
    path = Path(os.environ.get("CIVIC_DEMO_WORLD_PATH") or
                Path(__file__).resolve().parents[4] / "data" / "civic" / "astana" / "demo-world" / "world_v1.json")
    if not path.exists():
        pytest.skip(f"мира R02 нет в этой сборке: {path}")
    svc, v2 = stack
    world = json.loads(path.read_text(encoding="utf-8"))
    report = seed_world(svc.db.path, world, NOW, service=svc)
    assert report["invalid"] == 0 and report["inserted"] == len(world["works"]) + len(world["ideas"])
    assert report["projects"] >= 1
