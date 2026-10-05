"""K10 round-5 REVIEW: did coincident coordinates decide the choice of the 2x2 km square?

Two parts:
 1. bound check (stdlib, needs only --app-root): adjust the selected cell's count under variants and compare
    with the ORIGINAL runner-up count from research/round-3-results/K10/selection/<city>_bbox_selection.json.
    Variants only ever lower counts, so "adjusted selected > original runner-up" proves the choice is unchanged.
 2. exact recount (optional --raw-dir, needs shapely): every grid cell recomputed from the round-2 raw places
    (sha256 must equal research/next-round/K10/provenance/raw_extracts.sha256) under the same variants.
Variants (sensitivity only; this review does not delete or merge records):
  V0 all records (rule used in round 3) | V1 one per exact coordinate | V2 one per <=2 m cluster
  V3 drop records in exact groups of size >= 3 | V4 drop every record that shares an exact coordinate
Usage: python3 selection_impact.py --app-root <dir> [--raw-dir <round-2 raw dir>] [--out file]
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
import qa_flags  # noqa: E402

SEL = "research/round-3-results/K10/selection/{city}_bbox_selection.json"
RAW_SHA = "research/next-round/K10/provenance/raw_extracts.sha256"
DISTRICTS = "research/next-round/K10/samples/{city}_districts_overture.geojson"
VARIANTS = ["V0_all", "V1_one_per_exact_coordinate", "V2_one_per_2m_cluster", "V3_drop_exact_groups_ge3", "V4_drop_all_exact_group_members"]


def variant_counts(points):
    """points: list of (lon, lat). Returns count per variant for this set."""
    by = {}
    for p in points:
        by[p] = by.get(p, 0) + 1
    xy = sorted(by)
    parent = list(range(len(xy)))

    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(xy)):
        for j in range(i + 1, len(xy)):
            if qa_flags.hav(xy[i], xy[j]) <= qa_flags.NEAR_M:
                parent[f(i)] = f(j)
    return {"V0_all": len(points), "V1_one_per_exact_coordinate": len(by),
            "V2_one_per_2m_cluster": len({f(i) for i in range(len(xy))}),
            "V3_drop_exact_groups_ge3": sum(n for n in by.values() if n < 3),
            "V4_drop_all_exact_group_members": sum(n for n in by.values() if n == 1)}


def bound_check(app_root):
    data = qa_flags.parse_data_js((Path(app_root) / "web" / "data.js").read_bytes())
    out = {}
    for city in ("shymkent", "astana"):
        sel = json.loads((REPO / SEL.format(city=city)).read_text(encoding="utf-8"))
        pts = [(p["lon"], p["lat"]) for p in data["cities"][city]["places"]]
        adj = variant_counts(pts)
        runner = sel["top5"][1]["social_places"]
        out[city] = {"selected_cell": sel["selected"], "original_runner_up": sel["top5"][1],
                     "selected_cell_count_by_variant": adj,
                     "selection_unchanged_proven_without_raw": {v: adj[v] > runner for v in VARIANTS},
                     "note": "False = not provable from the square alone; see exact recount"}
    return out


def exact_recount(raw_dir):
    import shapely
    from shapely.geometry import box, shape
    sys.path.insert(0, str(REPO / "research/round-3-results/K10/scripts"))
    from k10_rules import social_group
    expected = dict(line.split()[::-1] for line in (REPO / RAW_SHA).read_text().splitlines() if line.strip())
    out = {}
    for city in ("shymkent", "astana"):
        rp = Path(raw_dir) / f"{city}_places.jsonl"
        h = hashlib.sha256(rp.read_bytes()).hexdigest()
        if h != expected.get(rp.name):
            raise SystemExit(f"{rp.name}: sha256 {h} != committed {expected.get(rp.name)}")
        sel = json.loads((REPO / SEL.format(city=city)).read_text(encoding="utf-8"))
        gj = json.loads((REPO / DISTRICTS.format(city=city)).read_text(encoding="utf-8"))
        city_g = shape([f for f in gj["features"] if f["properties"]["unit_kind"] == "city"][0]["geometry"])
        gr = sel["grid"]
        pts, all_xy = [], {}
        for line in rp.read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            g = shapely.from_wkt(p["geometry"])
            all_xy[(g.x, g.y)] = all_xy.get((g.x, g.y), 0) + 1
            if social_group(p.get("taxonomy"), p.get("basic_category")):
                pts.append((g.x, g.y))
        cells = []
        for r in range(gr["rows"]):
            for c in range(gr["cols"]):
                b = (gr["origin_lon"] + c * gr["dlon"], gr["origin_lat"] + r * gr["dlat"],
                     gr["origin_lon"] + (c + 1) * gr["dlon"], gr["origin_lat"] + (r + 1) * gr["dlat"])
                if not city_g.contains(box(*b)):
                    continue
                inside = [p for p in pts if b[0] < p[0] < b[2] and b[1] < p[1] < b[3]]
                cells.append({"row": r, "col": c, **variant_counts(inside)})
        res = {"raw_sha256": h, "cells_fully_inside_city": len(cells), "variants": {}}
        for v in VARIANTS:
            ranked = sorted(cells, key=lambda x: (-x[v], x["row"], x["col"]))
            res["variants"][v] = {"winner": {"row": ranked[0]["row"], "col": ranked[0]["col"], "count": ranked[0][v]},
                                  "runner_up": {"row": ranked[1]["row"], "col": ranked[1]["col"], "count": ranked[1][v]},
                                  "same_as_round3_selection": (ranked[0]["row"], ranked[0]["col"]) == (sel["selected"]["row"], sel["selected"]["col"])}
        soc = {}
        for p in pts:
            soc[p] = soc.get(p, 0) + 1
        top = sorted(soc.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        res["largest_exact_groups_city_bbox"] = [
            {"lon": xy[0], "lat": xy[1], "social_records": n, "records_any_category_at_point": all_xy[xy],
             "inside_selected_square": sel["selected"]["bbox"][0] <= xy[0] <= sel["selected"]["bbox"][2]
             and sel["selected"]["bbox"][1] <= xy[1] <= sel["selected"]["bbox"][3]} for xy, n in top]
        out[city] = res
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--raw-dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = {"tool": "research/round-5-results/K10/tools/selection_impact.py", "variants": VARIANTS,
           "bound_check": bound_check(a.app_root)}
    if a.raw_dir:
        res["exact_recount"] = exact_recount(a.raw_dir)
    txt = json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
