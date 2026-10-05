"""K10-E02: first-function prototype - social POI counts per district, both cities.

Point-in-polygon assignment of Overture places to Overture district polygons
(same release), grouped into a few social categories, at two confidence
thresholds. QC: points outside any district, exact duplicates (same normalised
name within ~50 m). Counts describe Overture coverage, NOT official supply.

Usage: python places_by_district.py <raw_dir> > result.json
"""
import json
import re
import sys
from collections import Counter, defaultdict

import shapely
from shapely.strtree import STRtree

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from check_districts import load  # noqa: E402

THRESHOLDS = (0.0, 0.5)


def group(r):
    h = (r.get("taxonomy") or {}).get("hierarchy") or []
    bc = r.get("basic_category")
    if h[:3] == ["education", "place_of_learning", "school"]:
        return "preschool" if "preschool" in h else "school"
    if h[:3] == ["education", "place_of_learning", "college_university"]:
        return "college_university"
    if h[:2] == ["health_care", "hospital"]:
        return "hospital"
    if "outpatient_care_facility" in h or "primary_care_or_general_clinic" in h:
        return "outpatient_clinic"
    if bc == "pharmacy_and_drug_store":
        return "pharmacy"
    if bc == "government_office":
        return "government_office"
    return None


def norm(name):
    return re.sub(r"[^\w]+", " ", (name or "").lower()).strip()


def run(raw_dir, city):
    region, districts, extra = load(raw_dir, city)
    city_g = shapely.from_wkt(region[0]["geometry"])
    units = districts + extra
    geoms = [shapely.from_wkt(u["geometry"]) for u in units]
    tree = STRtree(geoms)
    places = [json.loads(l) for l in open(f"{raw_dir}/{city}_places.jsonl", encoding="utf-8")]
    counts = {t: defaultdict(Counter) for t in THRESHOLDS}
    outside_city = 0
    outside_districts = 0
    in_city = 0
    seen = Counter()
    dup = 0
    for p in places:
        pt = shapely.from_wkt(p["geometry"])
        if not city_g.contains(pt):
            outside_city += 1
            continue
        in_city += 1
        hits = [i for i in tree.query(pt) if geoms[i].contains(pt)]
        unit = units[hits[0]]["names"]["primary"] if hits else "(вне районов)"
        if not hits:
            outside_districts += 1
        g = group(p)
        key = (norm((p.get("names") or {}).get("primary")), round(pt.x, 3), round(pt.y, 3))
        seen[key] += 1
        if seen[key] > 1:
            dup += 1
        if g is None:
            continue
        for t in THRESHOLDS:
            if (p.get("confidence") or 0) >= t:
                counts[t][unit][g] += 1
    return {
        "city": city,
        "places_in_bbox": len(places),
        "places_inside_city_polygon": in_city,
        "places_outside_city_polygon": outside_city,
        "places_in_city_but_outside_districts": outside_districts,
        "same_name_same_~100m_cell_repeats": dup,
        "counts_by_threshold": {f"confidence>={t}": {u: dict(c) for u, c in sorted(v.items())}
                                for t, v in counts.items()},
    }


if __name__ == "__main__":
    raw = sys.argv[1]
    print(json.dumps({"experiment_id": "K10-E02",
                      "note": "Counts of Overture POIs, not official registries; completeness unknown.",
                      "results": [run(raw, "shymkent"), run(raw, "astana")]},
                     ensure_ascii=False, indent=1))
