"""K11 round 8: deterministic fixtures for city-plan-v2 orchestration tests.

    python fixtures/make_fixtures.py --app-root <copy of prototypes/city-evidence @ a5b5e2d> --app-sha <SHA>

synthetic/  explicit SYNTHETIC contexts (city_id "synthetic"); NOT city statistics.
real/       source records copied (id, lon, lat, group) from the app's web/data.js for one city/category,
            with data.js sha256 and app SHA in provenance; control points, candidates, costs and budget are
            SYNTHETIC user inputs (conditional units, not tenge), clearly labelled.
Then: python oracle/plan_oracle.py --write-expected fixtures/synthetic ; ... fixtures/real
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
SCHEMA = "city-plan-v2"


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n").encode("utf-8"))


def scenario(city, snap, category, points, cands, budget, max_sel, radius, req=(), exc=(), sel=()):
    return {"schema_version": SCHEMA, "city_id": city, "source_snapshot": snap, "category": category,
            "control_points": points, "candidates": cands, "budget": budget, "max_selected": max_sel,
            "coverage_radius_m": radius, "required_ids": list(req), "excluded_ids": list(exc), "selected_ids": list(sel)}


def cand(cid, lon, lat, cost, category="school"):
    return {"id": cid, "lon": round(lon, 6), "lat": round(lat, 6), "category": category, "kind": "hypothetical", "cost": cost}


def pt(pid, lon, lat, w=1):
    return {"id": pid, "lon": round(lon, 6), "lat": round(lat, 6), "weight": w}


def synthetic(out: Path):
    bbox = [0.0, 0.0, 0.02, 0.02]
    ctx = lambda recs: {"city_id": "synthetic", "bbox": bbox, "source_snapshot": "synthetic:k11-r8", "records": recs,
                        "kind": "SYNTHETIC — not a city"}
    prov = {"kind": "synthetic", "generator": "fixtures/make_fixtures.py", "note": "explicit synthetic geometry; not city statistics"}
    src = [{"id": "src-центр", "lon": 0.01, "lat": 0.01, "group": "school"}]
    corners = [pt(f"p{i}", x, y) for i, (x, y) in enumerate([(0.005, 0.005), (0.015, 0.005), (0.005, 0.015), (0.015, 0.015)])]
    ties = [cand(c, x, y, 100) for c, (x, y) in zip(["b", "a", "d", "c"], [(0.004, 0.006), (0.006, 0.004), (0.014, 0.016), (0.016, 0.014)])]
    cases = {
        "syn_ties.json": (src, scenario("synthetic", "synthetic:k11-r8", "school", corners, ties, 300, 2, 600)),
        "syn_empty_baseline.json": ([], scenario("synthetic", "synthetic:k11-r8", "school",
            [pt(f"q{i}", 0.002 + 0.004 * i, 0.01, w=i + 1) for i in range(5)],
            [cand(f"c{i}", 0.003 + 0.005 * i, 0.012, 10 * (i + 1)) for i in range(4)], 60, 2, 400)),
        "syn_infeasible_budget.json": (src, scenario("synthetic", "synthetic:k11-r8", "school", corners, ties, 50, 2, 600, req=["a"])),
        "syn_infeasible_count.json": (src, scenario("synthetic", "synthetic:k11-r8", "school", corners, ties, 1000, 2, 600,
                                                    req=["a", "b", "c"])),
        "syn_equal_pareto.json": (src, scenario("synthetic", "synthetic:k11-r8", "school", corners,
            [cand(c, x, y, 50) for c, (x, y) in zip(["e1", "e2", "e3", "e4"], [(0.005, 0.006), (0.006, 0.005), (0.015, 0.016), (0.016, 0.015)])],
            1000, 3, 300)),
        "syn_required_excluded.json": (src, scenario("synthetic", "synthetic:k11-r8", "school", corners, ties, 400, 3, 600,
                                                     req=["d"], exc=["a"], sel=["d", "b"])),
        "syn_unicode_ids.json": (src, scenario("synthetic", "synthetic:k11-r8", "school",
            [pt(i, 0.003 + 0.002 * k, 0.004 + 0.002 * k, k + 1) for k, i in enumerate(["нүкте-1", "Ә-2", "z-3", "-4", "😀-5"])],
            [cand(i, 0.004 + 0.003 * k, 0.012 - 0.001 * k, 100) for k, i in enumerate(["мектеп-ә", "мектеп-а", "Z", "", "😀", "école"])],
            300, 3, 500)),
    }
    rnd = random.Random(20261005)
    pts = [pt(f"P{i:02d}", rnd.uniform(0.001, 0.019), rnd.uniform(0.001, 0.019), rnd.randint(1, 100)) for i in range(25)]
    cs = [cand(f"C{j:02d}", rnd.uniform(0.001, 0.019), rnd.uniform(0.001, 0.019), rnd.randint(1, 400000)) for j in range(16)]
    srcs = [{"id": f"S{k}", "lon": rnd.uniform(0.0, 0.02), "lat": rnd.uniform(0.0, 0.02), "group": "school"} for k in range(3)]
    cases["syn_bench_16x25.json"] = (srcs, scenario("synthetic", "synthetic:k11-r8", "school", pts, cs, 1000000, 5, 800))
    rows = []
    for name, (recs, sc) in cases.items():
        write(out / name, {"provenance": prov, "context": ctx(recs), "scenario": sc})
        rows.append({"file": name, "kind": "synthetic"})
    return rows


def real(out: Path, app_root: Path, app_sha: str):
    data_js = app_root / "web" / "data.js"
    raw = data_js.read_bytes()
    text = raw.decode("utf-8")
    data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    dsha = hashlib.sha256(raw).hexdigest()
    rows = []
    for city, category, n_c, n_p, seed in (("shymkent", "school", 16, 25, 11), ("astana", "outpatient_clinic", 8, 12, 12),
                                            ("astana", "school", 16, 25, 13)):
        c = data["cities"][city]
        bb = c["bbox"]
        recs = [{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "group": p["group"]} for p in c["places"] if p["group"] == category]
        rnd = random.Random(seed)
        u = lambda a, b: rnd.uniform(a + (b - a) * 0.02, b - (b - a) * 0.02)
        pts = [pt(f"нүкте-{i:02d}", u(bb[0], bb[2]), u(bb[1], bb[3]), rnd.randint(1, 100)) for i in range(n_p)]
        cs = [cand(f"жоба-{j:02d}", u(bb[0], bb[2]), u(bb[1], bb[3]), rnd.randint(1000, 500000), category) for j in range(n_c)]
        snap = f"k11-r8:{city}:{category}:data.js-sha256:{dsha}"
        sc = scenario(city, snap, category, pts, cs, 900000, 5, 300)
        name = f"real_{city}_{category}_{n_c}x{n_p}.json"
        prov = {"kind": "real_slice_with_synthetic_inputs", "app_branch": "claude/beautiful-clarke-sbzomj", "app_sha": app_sha,
                "data_js_sha256": dsha, "records": f"web/data.js cities.{city}.places with group={category} ({len(recs)} records; id, lon, lat, group)",
                "release": c.get("release"), "synthetic": "control points, candidates, weights, costs (conditional units) and budget"}
        write(out / name, {"provenance": prov, "context": {"city_id": city, "bbox": bb, "source_snapshot": snap, "records": recs},
                           "scenario": sc})
        rows.append({"file": name, "kind": "real_slice", "city": city, "category": category, "records": len(recs)})
    return rows, dsha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--app-sha", required=True)
    a = ap.parse_args()
    syn = synthetic(HERE / "synthetic")
    rea, dsha = real(HERE / "real", Path(a.app_root), a.app_sha)
    write(HERE / "MANIFEST.json", {"generator": "fixtures/make_fixtures.py", "app_sha": a.app_sha, "data_js_sha256": dsha,
                                   "synthetic": syn, "real": rea})
    print(f"{len(syn)} synthetic + {len(rea)} real-slice fixtures")


if __name__ == "__main__":
    main()
