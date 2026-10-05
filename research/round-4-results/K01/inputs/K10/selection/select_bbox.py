"""K10 round 3: choose one small study square per city from data (rule fixed in advance).

Rule (set before looking at the result):
  * grid of CELL_KM x CELL_KM squares, origin = SW corner of the city polygon bbox,
    degree steps from the city polygon centroid latitude;
  * keep only squares lying fully inside the city polygon (committed round-2 sample);
  * score = number of Overture places inside the square that match the K10 social rule
    (any confidence), from the round-2 raw places extract;
  * pick max score; ties -> smallest (row, col).

Inputs:
  <districts.geojson>  research/next-round/K10/samples/<city>_districts_overture.geojson (committed)
  <places.jsonl>       round-2 raw extract (sha256 in research/next-round/K10/provenance/raw_extracts.sha256),
                       re-creatable with research/next-round/K10/scripts/overture_extract.py
Usage: python select_bbox.py <city> <districts.geojson> <places.jsonl>
"""
import hashlib
import json
import math
import sys

import shapely
from shapely.geometry import box, shape

sys.path.insert(0, __file__.rsplit("/", 2)[0] + "/scripts")
from k10_rules import CELL_KM, social_group  # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(city, districts_path, places_path):
    gj = json.load(open(districts_path, encoding="utf-8"))
    city_feat = [f for f in gj["features"] if f["properties"]["unit_kind"] == "city"]
    assert len(city_feat) == 1
    city_g = shape(city_feat[0]["geometry"])
    lat0 = city_g.centroid.y
    dlat = CELL_KM / 111.32
    dlon = CELL_KM / (111.32 * math.cos(math.radians(lat0)))
    minx, miny, maxx, maxy = city_g.bounds
    ncol = int(math.ceil((maxx - minx) / dlon))
    nrow = int(math.ceil((maxy - miny) / dlat))
    pts = []
    for line in open(places_path, encoding="utf-8"):
        p = json.loads(line)
        if social_group(p.get("taxonomy"), p.get("basic_category")) is None:
            continue
        pts.append(shapely.from_wkt(p["geometry"]))
    cells = []
    for r in range(nrow):
        for c in range(ncol):
            b = (minx + c * dlon, miny + r * dlat, minx + (c + 1) * dlon, miny + (r + 1) * dlat)
            cell = box(*b)
            if not city_g.contains(cell):
                continue
            n = sum(1 for pt in pts if cell.contains(pt))
            cells.append({"row": r, "col": c, "bbox": [round(v, 6) for v in b], "social_places": n})
    cells.sort(key=lambda x: (-x["social_places"], x["row"], x["col"]))
    return {
        "city": city,
        "rule": "max social places in CELL_KM square fully inside city polygon; tie -> min(row,col)",
        "cell_km": CELL_KM,
        "grid": {"origin_lon": round(minx, 6), "origin_lat": round(miny, 6),
                 "dlon": round(dlon, 7), "dlat": round(dlat, 7), "rows": nrow, "cols": ncol,
                 "lat_for_dlon": round(lat0, 5)},
        "inputs": {"districts_geojson": districts_path, "districts_sha256": sha256(districts_path),
                   "places_jsonl": places_path.rsplit("/", 1)[-1], "places_sha256": sha256(places_path)},
        "social_places_in_input": len(pts),
        "cells_fully_inside_city": len(cells),
        "cells_with_zero": sum(1 for c in cells if c["social_places"] == 0),
        "selected": cells[0],
        "top5": cells[:5],
    }


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4]), ensure_ascii=False, indent=1))
