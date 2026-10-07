"""Where do the slice's objects fall relative to the K03 graph area and the OSM districts?

Read-only analysis for choosing a compact pilot. Coordinates are never moved to fit the
graph: an object outside the graph area is reported as such.

  python3 -I data/civic/astana/tools/pilot_check.py data/civic/astana/demo_synthetic.json
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import civic_v1 as cv  # noqa: E402


def _in_bbox(p, b):
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def _district(p, fence):
    for poly in fence["polygons"]:
        if cv._point_in_polygon(p[0], p[1], poly["rings"]):
            return poly["district_id"]
    return None


def analyse(items, ref, fence) -> dict:
    g = ref["graph"]
    rows = []
    for o in items:
        geom = o.get("geometry")
        if geom is None:
            rows.append({"id": o["id"], "geometry": None, "placement": "list_only"})
            continue
        pts = cv._positions(geom)
        in_decl = all(_in_bbox(p, g["declared_bbox"]) for p in pts)
        in_ext = all(_in_bbox(p, g["node_extent"]) for p in pts)
        districts = sorted({_district(p, fence) or "outside_districts" for p in pts})
        rows.append({
            "id": o["id"], "geometry": geom["type"], "precision": o.get("geometry_precision"),
            "evidence_type": o.get("evidence_type"),
            "placement": "inside_graph_bbox" if in_decl else ("inside_graph_node_extent" if in_ext else "outside_graph"),
            "districts": districts,
        })
    counts = {}
    for r in rows:
        counts[r["placement"]] = counts.get(r["placement"], 0) + 1
    by_district = {}
    for r in rows:
        for d in r.get("districts", []):
            by_district[d] = by_district.get(d, 0) + 1
    real = [r for r in rows if r.get("evidence_type") in ("observed", "derived")]
    return {
        "graph": {k: g[k] for k in ("path", "at_commit", "graph_sha256", "declared_bbox", "node_extent", "policy_family")},
        "items": len(rows),
        "real_items": len(real),
        "placement_counts": dict(sorted(counts.items())),
        "by_district": dict(sorted(by_district.items())),
        "rows": rows,
        "pilot_by_confirmed_concentration": (
            "not_possible: no confirmed real objects in this slice" if not real else
            "compare counts of real items inside the graph area vs per district before choosing"),
    }


def main(argv):
    path = argv[1] if len(argv) > 1 else os.path.join(PKG, "objects.json")
    with open(os.path.join(PKG, "pilot_reference.json"), encoding="utf-8") as fh:
        ref = json.load(fh)
    report = analyse(cv.load_items(path), ref, cv.load_geofence(os.path.join(PKG, "geofence.json")))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
