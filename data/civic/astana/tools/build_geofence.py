"""Build data/civic/astana/geofence.json from the saved OSM district polygons.

Input (read-only, not modified): data/astana_districts.geojson - OSM administrative
relations saved in the repository (ODbL, see its own metadata). The geofence is a
sanity check for coordinates (wrong city, swapped lon/lat), not a legal boundary.
Deterministic: same input bytes -> same output bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(PKG, "..", "..", ".."))
DEFAULT_INPUT = os.path.join(REPO, "data", "astana_districts.geojson")
DEFAULT_OUTPUT = os.path.join(PKG, "geofence.json")
MARGIN_DEG = 0.05  # ~5.5 km north-south, ~3.5 km east-west at 51N


def build(input_path: str = DEFAULT_INPUT) -> dict:
    raw = open(input_path, "rb").read()
    data = json.loads(raw)
    polygons = []
    xs, ys = [], []
    for feat in data["features"]:
        geom = feat["geometry"]
        parts = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for rings in parts:
            polygons.append({
                "district_id": feat["properties"].get("id"),
                "name": feat["properties"].get("name"),
                "osm_relation": feat["properties"].get("osm_id"),
                "rings": rings,
            })
            for ring in rings:
                for lon, lat in ring:
                    xs.append(lon)
                    ys.append(lat)
    city_bbox = [min(xs), min(ys), max(xs), max(ys)]
    outer = [round(city_bbox[0] - MARGIN_DEG, 6), round(city_bbox[1] - MARGIN_DEG, 6),
             round(city_bbox[2] + MARGIN_DEG, 6), round(city_bbox[3] + MARGIN_DEG, 6)]
    meta = data.get("metadata", {})
    polygons.sort(key=lambda p: (str(p["district_id"]), len(p["rings"][0])))
    return {
        "schema": "r05-geofence-v1",
        "city": "astana",
        "purpose": "Coordinate sanity check (wrong city / swapped lon-lat). Not an official boundary.",
        "input": {
            "path": os.path.relpath(input_path, REPO).replace(os.sep, "/"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "source": meta.get("source"),
            "attribution": meta.get("attribution"),
            "license_url": meta.get("license_url"),
            "retrieved_at": meta.get("retrieved_at"),
            "osm_base_timestamp": meta.get("osm_base_timestamp"),
            "note": meta.get("note"),
        },
        "license": "ODbL-1.0 (derived from OpenStreetMap; attribution required)",
        "city_bbox": city_bbox,
        "margin_deg": MARGIN_DEG,
        "outer_bbox": outer,
        "polygons": polygons,
    }


def main(argv: list[str]) -> int:
    out = argv[1] if len(argv) > 1 else DEFAULT_OUTPUT
    fence = build()
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(fence, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        fh.write("\n")
    print(f"wrote {out}: {len(fence['polygons'])} polygons, outer_bbox={fence['outer_bbox']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
