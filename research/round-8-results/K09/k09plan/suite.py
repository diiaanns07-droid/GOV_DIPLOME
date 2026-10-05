"""Seeded генератор сценариев city-plan-v2 для эксперимента (synthetic точки/кандидаты/стоимости).

Исходные записи берутся из закреплённого среза (реальные записи Overture) или пусты (synthetic-условие).
Seed — строка (random.Random на строке детерминирован через sha512, не зависит от PYTHONHASHSEED).
"""
import hashlib, json, random
from . import METRIC_VERSION
from . import data as D


def slice_snapshot(data_sha256, city, category):
    return "k09r8-slice:" + hashlib.sha256(f"{data_sha256}|{city}|{category}".encode()).hexdigest()[:32]


def make_context(slice_data, data_sha256, city, category, baseline):
    srcs = D.sources(slice_data, city, category) if baseline == "real_slice_records" else []
    return {"city_id": city, "category": category, "bbox": D.bbox(slice_data, city),
            "source_snapshot": slice_snapshot(data_sha256, city, category), "sources": srcs,
            "baseline": baseline, "metric_version": METRIC_VERSION}


def make_scenario(ctx, n_candidates, n_points, budget_ratio, weights, max_selected, radius_m, seed, config_version):
    rng = random.Random(f"{config_version}|{ctx['city_id']}|{ctx['category']}|{ctx['baseline']}|{n_candidates}|{n_points}|"
                        f"{budget_ratio}|{weights}|{max_selected}|{radius_m}|{seed}")
    w, s, e, n = ctx["bbox"]

    def pt():
        return round(rng.uniform(w, e), 6), round(rng.uniform(s, n), 6)

    pts = []
    for i in range(n_points):
        lon, lat = pt()
        if weights == "uniform":
            wt = 1
        elif weights == "random_1_100":
            wt = rng.randint(1, 100)
        else:                                   # one_heavy
            wt = 100 if i == 0 else 1
        pts.append({"id": f"p{i:02d}", "lon": lon, "lat": lat, "weight": wt})
    cands = []
    for i in range(n_candidates):
        lon, lat = pt()
        cands.append({"id": f"c{i:02d}", "lon": lon, "lat": lat, "category": ctx["category"], "kind": "hypothetical",
                      "cost": rng.randint(100, 1000)})
    budget = int(budget_ratio * sum(c["cost"] for c in cands))
    return {"schema_version": "city-plan-v2", "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"],
            "category": ctx["category"], "control_points": pts, "candidates": cands, "budget": budget,
            "max_selected": max_selected, "coverage_radius_m": radius_m, "required_ids": [], "excluded_ids": [],
            "selected_ids": []}
