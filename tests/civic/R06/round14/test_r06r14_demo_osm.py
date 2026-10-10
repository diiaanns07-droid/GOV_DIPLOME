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
