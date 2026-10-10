"""R06 раунд 14: демо-предложения стоят в правильных местах по реальным данным OSM (CONTRACT §8).

Данные — data/civic/astana/osm-objects/raw (LOCAL-1, real, ODbL), только чтение. Нет папки — SKIP.
Проверки: всё в районе Нура; остановка совпадает с существующей остановкой OSM; сквер/площадка/спортплощадка —
внутри жилого квартала OSM, не ближе 60 м к существующим площадкам/спортплощадкам/паркам, вне школ и детсадов;
освещение — по рёбрам графа (линия не дальше 5 м от формы ребра).
"""

import gzip
import json
import math
from pathlib import Path

import pytest

from ui.civic_store.demo_r14 import DEMO_PROPOSALS
from ui.civic_store.districts import _inside, district_of

REPO = Path(__file__).resolve().parents[4]
RAW = REPO / "data" / "civic" / "astana" / "osm-objects" / "raw"
GRAPH = REPO / "engine" / "civic_scenarios" / "graphs" / "osm-astana-walking-20260506.graph.json"
pytestmark = pytest.mark.skipif(not RAW.is_dir(), reason="нет data/civic/astana/osm-objects (LOCAL-1)")
K = math.cos(math.radians(51.13))


def load(name):
    with gzip.open(RAW / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)["elements"]


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
    out = []
    for e in load(name):
        if e["type"] == "node":
            out.append(("node", [[e["lon"], e["lat"]]]))
        elif e.get("geometry"):
            out.append(("way", [[g["lon"], g["lat"]] for g in e["geometry"]]))
    return out


def clearance(p, name):
    best = float("inf")
    for kind, ring in shapes(name):
        if kind == "node":
            best = min(best, metres(p, ring[0]))
        elif len(ring) > 3 and ring[0] == ring[-1] and _inside(p[0], p[1], ring):
            return 0.0
        else:
            best = min(best, to_segment(p, ring))
    return best


POINTS = {kind: geom for kind, geom, *_ in DEMO_PROPOSALS}


def test_all_demo_proposals_are_in_nura():
    for kind, geometry in POINTS.items():
        assert district_of(geometry) == "nura", kind


def test_stop_is_a_real_osm_bus_stop():
    p = POINTS["stop"]["coordinates"]
    nearest = min(metres(p, (e["lon"], e["lat"])) for e in load("bus_stops") if e["type"] == "node")
    assert nearest < 1.0


@pytest.mark.parametrize("kind", ["square", "playground", "sports"])
def test_new_objects_are_inside_yards_and_away_from_existing(kind):
    p = POINTS[kind]["coordinates"]
    yards = [ring for t, ring in shapes("residential") if t == "way" and len(ring) > 3 and ring[0] == ring[-1]]
    assert any(_inside(p[0], p[1], ring) for ring in yards), "не внутри жилого квартала OSM"
    for name in ("playgrounds", "pitches", "parks", "gardens"):
        assert clearance(p, name) >= 60, (kind, name, clearance(p, name))
    for name in ("schools", "kindergartens"):
        assert clearance(p, name) > 0, (kind, "на территории", name)


def test_demo_points_do_not_collide_with_each_other():
    pts = [POINTS[k]["coordinates"] for k in ("square", "playground", "sports", "stop")]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            assert metres(pts[i], pts[j]) > 80


@pytest.mark.skipif(not GRAPH.is_file(), reason="нет пешеходного графа OSM")
def test_lighting_follows_graph_edges_within_5m():
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    edges = [e["geometry"] for e in graph["edges"] if e.get("osm_way_id") == 1482578141]
    line = POINTS["lighting"]["coordinates"]
    for p in line:
        assert min(to_segment(p, g) for g in edges) <= 5.0


DEMO_PACKAGE = REPO / "ui" / "civic_store" / "demo_package.json"


def test_demo_package_titles_have_no_tech_words_but_stay_synthetic():
    # UX_REVIEW R11 день 3, п. 15: «Демо: … (синтетика)» в названии лишнее — метка «Пример» уже есть.
    pkg = json.loads(DEMO_PACKAGE.read_text(encoding="utf-8"))
    assert pkg["slice"]["demo"] is True
    for item in pkg["items"]:
        assert "Демо" not in item["title"] and "синтетик" not in item["title"].lower(), item["title"]
        assert item["evidence_type"] == "synthetic"


@pytest.mark.skipif(not GRAPH.is_file(), reason="нет пешеходного графа OSM")
def test_demo_package_lines_follow_osm_graph_within_5m():
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    pkg = json.loads(DEMO_PACKAGE.read_text(encoding="utf-8"))
    lines = [i for i in pkg["items"] if i["geometry"] and i["geometry"]["type"] == "LineString"]
    assert lines and all(i["geometry_source"] == "osm-graph" and i["geometry_precision"] == "source" for i in lines)
    edges = [e["geometry"] for e in graph["edges"] if e.get("osm_way_id") == 409391547]
    for item in lines:
        for p in item["geometry"]["coordinates"]:
            assert min(to_segment(p, g) for g in edges) <= 5.0


def test_demo_yard_is_real_osm_residential():
    pkg = json.loads(DEMO_PACKAGE.read_text(encoding="utf-8"))
    yard = next(i for i in pkg["items"] if i["id"] == "demo-r02-yard-landscaping")
    ring = yard["geometry"]["coordinates"][0]
    residential = [r for t, r in shapes("residential") if t == "way" and len(r) > 3]
    best = min(max(min(metres(p, q) for q in r) for p in ring) for r in residential)
    assert yard["geometry_source"] == "osm-area" and best <= 5.0  # каждая вершина ≤ 5 м от контура двора OSM


@pytest.mark.skipif(not GRAPH.is_file(), reason="нет пешеходного графа OSM")
def test_demo_proposal_streets_are_the_nearest_named_streets():
    """Улица в названии и в near_street (ru/kk) — ближайшая улица с названием по графу OSM, не дальше 100 м.
    Ночь 10→11 окт: «Сквер у улицы Ильяса Омарова» стоял в 308 м от Омарова и в 68 м от Айтматова — исправлено."""
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    named = [(e["name"], e["geometry"]["coordinates"] if isinstance(e["geometry"], dict) else e["geometry"])
             for e in graph["edges"] if e.get("name")]
    for kind, geom, title_ru, title_kk, *_rest, street in DEMO_PROPOSALS:
        coords = geom["coordinates"]
        p = coords if geom["type"] == "Point" else coords[len(coords) // 2]
        street_ru, street_kk = street
        assert street_kk and "улица" not in street_kk and street_kk.endswith("көшесі"), street_kk
        own = min(to_segment(p, line) for name, line in named if name == street_ru)
        nearest = min(to_segment(p, line) for _name, line in named)
        assert own <= 100 and own - nearest <= 30, (kind, street_ru, round(own), round(nearest))
        if "улиц" in title_ru:  # «… у улицы X» / «Освещение улицы X» — та же улица, что рядом
            assert street_ru.split(" ", 1)[1] in title_ru, (title_ru, street_ru)
            assert street_kk.replace(" көшесі", "") in title_kk, (title_kk, street_kk)
