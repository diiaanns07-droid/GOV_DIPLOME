"""K10-E03: road/path network profile per district from Overture transportation/segment.

For each city: segments clipped to district polygons -> geodesic km by class,
attribute completeness (names, road_surface), and connectivity of the road
graph inside the city polygon (union-find over shared connector ids):
share of length in the largest connected component.

Usage: python network_by_district.py <raw_dir> > result.json
"""
import json
import sys
from collections import Counter, defaultdict

import shapely
from pyproj import Geod
from shapely.strtree import STRtree

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from check_districts import load  # noqa: E402

GEOD = Geod(ellps="WGS84")
WALK_CLASSES = {"footway", "pedestrian", "path", "steps", "living_street", "residential", "service",
                "track", "cycleway", "bridleway", "unclassified", "tertiary", "secondary", "primary"}


def km(g):
    return GEOD.geometry_length(g) / 1000.0


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def run(raw_dir, city):
    region, districts, extra = load(raw_dir, city)
    city_g = shapely.from_wkt(region[0]["geometry"])
    units = districts + extra
    ugeoms = [shapely.from_wkt(u["geometry"]) for u in units]
    tree = STRtree(ugeoms)
    subtype_count = Counter()
    by_unit = defaultdict(lambda: {"km_by_class": Counter(), "segments": 0, "named": 0, "with_surface": 0})
    dsu = DSU()
    seg_len = {}
    seg_conn = {}
    n_in_city = 0
    for line in open(f"{raw_dir}/{city}_segment.jsonl", encoding="utf-8"):
        s = json.loads(line)
        subtype_count[s.get("subtype")] += 1
        if s.get("subtype") != "road":
            continue
        g = shapely.from_wkt(s["geometry"])
        if not city_g.intersects(g):
            continue
        n_in_city += 1
        cls = s.get("class") or "(none)"
        inside = g.intersection(city_g)
        seg_len[s["id"]] = km(inside)
        conns = [c["connector_id"] for c in (s.get("connectors") or [])]
        seg_conn[s["id"]] = conns
        for a, b in zip(conns, conns[1:]):
            dsu.union(a, b)
        for i in tree.query(g):
            part = g.intersection(ugeoms[i])
            if part.is_empty:
                continue
            u = by_unit[units[i]["names"]["primary"]]
            u["km_by_class"][cls] += km(part)
            u["segments"] += 1
            u["named"] += 1 if (s.get("names") or {}).get("primary") else 0
            u["with_surface"] += 1 if s.get("road_surface") else 0
    comp_len = Counter()
    for sid, conns in seg_conn.items():
        if conns:
            comp_len[dsu.find(conns[0])] += seg_len[sid]
    total = sum(seg_len.values())
    lcc = max(comp_len.values()) if comp_len else 0.0
    units_out = {}
    for name, u in sorted(by_unit.items()):
        kc = {k: round(v, 2) for k, v in sorted(u["km_by_class"].items(), key=lambda x: -x[1])}
        units_out[name] = {
            "road_km_total": round(sum(u["km_by_class"].values()), 2),
            "walkable_class_km": round(sum(v for k, v in u["km_by_class"].items() if k in WALK_CLASSES), 2),
            "km_by_class": kc,
            "segment_pieces": u["segments"],
            "share_named": round(u["named"] / u["segments"], 3) if u["segments"] else None,
            "share_with_road_surface": round(u["with_surface"] / u["segments"], 3) if u["segments"] else None,
        }
    return {
        "city": city,
        "segments_in_bbox_by_subtype": dict(subtype_count),
        "road_segments_intersecting_city": n_in_city,
        "road_km_inside_city": round(total, 2),
        "connected_components": len(comp_len),
        "largest_component_share_of_km": round(lcc / total, 4) if total else None,
        "districts": units_out,
    }


if __name__ == "__main__":
    raw = sys.argv[1]
    print(json.dumps({"experiment_id": "K10-E03",
                      "note": "Overture/OSM road network; lengths geodesic WGS84 km; 'walkable_class_km' is a K10 "
                              "class list, not a pedestrian-access verification.",
                      "walk_classes": sorted(WALK_CLASSES),
                      "results": [run(raw, "shymkent"), run(raw, "astana")]},
                     ensure_ascii=False, indent=1))
