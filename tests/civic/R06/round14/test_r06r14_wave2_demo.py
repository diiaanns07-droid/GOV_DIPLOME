"""R06 волна 2: демо-идеи жителей — честные места по OSM и путь «идея → проект» на демо-данных.

Места (data/civic/astana/osm-objects, LOCAL-1, real): идеи-объекты — внутри жилого квартала OSM, не ближе 60 м к
площадкам, спортплощадкам, паркам, вне школ и детсадов, ≥ 80 м от демо-проектов и друг от друга; улица в названии —
ближайшая улица с названием по графу OSM (≤ 100 м). Нет данных OSM — эти проверки SKIP, засев проверяется всегда.
"""

import gzip
import json
import math
from pathlib import Path

import pytest

from r06r14_helpers import call, device
from ui.civic_store.demo_r14 import DEMO_IDEAS, DEMO_PROPOSALS, seed_r14_demo
from ui.civic_store.districts import _inside, district_of

REPO = Path(__file__).resolve().parents[4]
RAW = REPO / "data" / "civic" / "astana" / "osm-objects" / "raw"
GRAPH = REPO / "engine" / "civic_scenarios" / "graphs" / "osm-astana-walking-20260506.graph.json"
K = math.cos(math.radians(51.13))
IDEAS = {i["key"]: i for i in DEMO_IDEAS}
YARD_IDEAS = ("square", "sports", "gazebo", "fountain")   # стоят во дворах (свет — на улице, велопарковка — у остановки)


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111320 * K, (a[1] - b[1]) * 110540)


def to_segment(p, line):
    best = float("inf")
    for a, b in zip(line, line[1:]):
        ax, ay = (a[0] - p[0]) * 111320 * K, (a[1] - p[1]) * 110540
        bx, by = (b[0] - p[0]) * 111320 * K, (b[1] - p[1]) * 110540
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        t = 0 if length == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def shapes(name):
    with gzip.open(RAW / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
        elements = json.load(fh)["elements"]
    out = []
    for e in elements:
        if e["type"] == "node":
            out.append(("node", [[e["lon"], e["lat"]]], e))
        elif e.get("geometry"):
            out.append(("way", [[g["lon"], g["lat"]] for g in e["geometry"]], e))
    return out


def clearance(p, name):
    best = float("inf")
    for kind, ring, _ in shapes(name):
        if kind == "node":
            best = min(best, metres(p, ring[0]))
        elif len(ring) > 3 and ring[0] == ring[-1] and _inside(p[0], p[1], ring):
            return 0.0
        else:
            best = min(best, to_segment(p, ring))
    return best


def point(key):
    return IDEAS[key]["geometry"]["coordinates"]


def test_all_demo_ideas_are_in_nura_and_bilingual():
    for idea in DEMO_IDEAS:
        assert district_of(idea["geometry"]) == "nura", idea["key"]
        texts = idea["texts"]
        for field in ("title", "description"):
            assert texts[field + "_ru"] and texts[field + "_kk"], (idea["key"], field)
        assert "Демо" not in texts["title_ru"] and len(texts["title_ru"]) <= 60 and len(texts["title_kk"]) <= 60
        if idea["status"] == "rejected":
            assert texts["reason_kk"] and texts["can_improve_kk"] and idea["reason"] == texts["reason_ru"]


@pytest.mark.skipif(not RAW.is_dir(), reason="нет data/civic/astana/osm-objects (LOCAL-1)")
@pytest.mark.parametrize("key", YARD_IDEAS)
def test_yard_ideas_are_inside_residential_and_away_from_existing(key):
    p = point(key)
    yards = [ring for t, ring, _ in shapes("residential") if t == "way" and len(ring) > 3 and ring[0] == ring[-1]]
    assert any(_inside(p[0], p[1], ring) for ring in yards), "не внутри жилого квартала OSM"
    for name in ("playgrounds", "pitches", "parks", "gardens"):
        assert clearance(p, name) >= 60, (key, name, clearance(p, name))
    for name in ("schools", "kindergartens"):
        assert clearance(p, name) > 0, (key, "на территории", name)


@pytest.mark.skipif(not RAW.is_dir(), reason="нет data/civic/astana/osm-objects (LOCAL-1)")
def test_bike_idea_stands_at_a_real_osm_stop_with_that_name():
    stops = [(e["lon"], e["lat"], e.get("tags", {}).get("name")) for _, _, e in shapes("bus_stops") if e["type"] == "node"]
    lon, lat, name = min(stops, key=lambda s: metres(point("bikes"), s[:2]))
    assert metres(point("bikes"), (lon, lat)) < 1.0 and name in IDEAS["bikes"]["texts"]["title_ru"]


def test_ideas_do_not_collide_with_demo_projects_or_each_other():
    projects = []
    for kind, geom, *_ in DEMO_PROPOSALS:
        c = geom["coordinates"]
        projects.append(c if geom["type"] == "Point" else c[len(c) // 2])
    yard = [point(k) for k in YARD_IDEAS]
    for p in yard:
        assert min(metres(p, q) for q in projects) >= 80, p
    for i in range(len(yard)):
        for j in range(i + 1, len(yard)):
            assert metres(yard[i], yard[j]) >= 80


@pytest.mark.skipif(not GRAPH.is_file(), reason="нет пешеходного графа OSM")
def test_streets_in_idea_titles_are_the_nearest_named_streets():
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    named = [(e["name"], e["geometry"]["coordinates"] if isinstance(e["geometry"], dict) else e["geometry"])
             for e in graph["edges"] if e.get("name")]
    for key, street in (("square", "улица Сыганак"), ("sports", "улица Ильяса Омарова"),
                        ("lighting", "улица Ильяса Омарова")):
        p = point(key)
        own = min(to_segment(p, line) for name, line in named if name == street)
        nearest = min(to_segment(p, line) for _n, line in named)
        assert own <= 100 and own - nearest <= 30, (key, round(own), round(nearest))
        assert street.split(" ", 1)[1].split()[-1] in IDEAS[key]["texts"]["title_ru"]


def test_seed_makes_the_whole_idea_path_once(stack, staff):
    svc, v2 = stack
    report = seed_r14_demo(svc)
    assert [x["key"] for x in report["ideas"]] == [i["key"] for i in DEMO_IDEAS]
    assert seed_r14_demo(svc)["ideas"] == [{"action": "kept"}]                     # повтор ничего не дублирует
    public = call(v2, "GET", "/ideas")["body"]["data"]
    by_title = {i["title_ru"]: i for i in public["items"]}
    assert public["counts"] == {"voting": 3, "checking": 0, "project": 1, "rejected": 1}
    square = by_title["Сквер у улицы Сыганак"]
    assert square["votes"] == 47 and square["demo"] is True and square["object"]["kind"] == "square"
    assert square["title_kk"] == "Сығанақ көшесі маңындағы гүлзар" and square["check"] is None
    light = by_title["Свет на улице Ильяса Омарова"]
    assert light["status"] == "project" and light["project"]["kind"] == "lighting" and light["votes"] == 52
    project = next(p for p in call(v2, "GET", "/proposals")["body"]["data"]["items"] if p["id"] == light["project"]["id"])
    assert project["idea"] == {"id": light["id"], "votes": 52} and project["title_ru"] == "Освещение улицы Ильяса Омарова"
    fountain = by_title["Фонтан во дворе"]
    assert fountain["reason_kk"].startswith("Учаскеде") and fountain["check"]["networks"] == "no"
    review = staff.call("GET", "/staff/ideas", query="status=review")["body"]["data"]["items"]
    assert [i["title_ru"] for i in review] == ["Велопарковка у остановки «Ильяса Омарова»"]
    # Демо-поддержки — случайные устройства: житель не может «снять» чужой демо-голос (R15 S20).
    supported = call(v2, "POST", f"/ideas/{square['id']}/support", {"device_id": device(1), "on": False})
    assert supported["body"]["data"]["changed"] is False and supported["body"]["data"]["item"]["votes"] == 47
