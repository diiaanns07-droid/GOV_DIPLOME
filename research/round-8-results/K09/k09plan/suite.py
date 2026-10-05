"""Seeded генератор сценариев city-plan-v2 для эксперимента (synthetic точки/кандидаты/стоимости).

Исходные записи берутся из закреплённого среза (реальные записи Overture) или пусты (synthetic-условие).
Seed — строка (random.Random на строке детерминирован через sha512, не зависит от PYTHONHASHSEED).
"""
import hashlib, json, random
from . import METRIC_VERSION
from . import data as D


def slice_snapshot(data_sha256, city, category, baseline="real_slice_records"):
    """Реальный срез и synthetic-условие без записей получают разные snapshot (разные исходные записи)."""
    tag = f"{data_sha256}|{city}|{category}" + ("" if baseline == "real_slice_records" else f"|{baseline}")
    return "k09r8-slice:" + hashlib.sha256(tag.encode()).hexdigest()[:32]


def make_context(slice_data, data_sha256, city, category, baseline):
    srcs = D.sources(slice_data, city, category) if baseline == "real_slice_records" else []
    return {"city_id": city, "category": category, "bbox": D.bbox(slice_data, city),
            "source_snapshot": slice_snapshot(data_sha256, city, category, baseline), "sources": srcs,
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


def make_scenario_v2(ctx, n_candidates, n_points, budget_ratio, weights, max_selected, radius_m, seed, config_version,
                     budget_max_selected=None):
    """Дизайн v2 (парный, вложенный): геометрия и стоимости зависят только от (config_version, city, category, seed).

    25 точек и 16 кандидатов генерируются один раз; задача берёт первые n_points / n_candidates (вложенные подмножества).
    Веса — отдельный генератор (seed-строка со схемой весов), первые n_points из 25.
    baseline (real/nobase), budget_ratio, max_selected и радиус на геометрию не влияют → парные сравнения.
    budget = floor(budget_ratio × сумма budget_max_selected самых дорогих кандидатов задачи);
    budget_ratio = 1.0 — бюджет не ограничивает (контроль). budget_max_selected по умолчанию = max_selected.
    """
    base = f"{config_version}|{ctx['city_id']}|{ctx['category']}"
    g = random.Random(f"{base}|geom|{seed}")
    w_, s_, e_, n_ = ctx["bbox"]

    def pt():
        return round(g.uniform(w_, e_), 6), round(g.uniform(s_, n_), 6)

    pts_all = [pt() for _ in range(25)]
    cands_all = []
    for _ in range(16):
        lon, lat = pt()
        cands_all.append((lon, lat, g.randint(100, 1000)))
    wr = random.Random(f"{base}|w|{weights}|{seed}")
    if weights == "uniform":
        wts = [1] * 25
    elif weights == "random_1_100":
        wts = [wr.randint(1, 100) for _ in range(25)]
    else:                                       # one_heavy
        wts = [100] + [1] * 24
    pts = [{"id": f"p{i:02d}", "lon": pts_all[i][0], "lat": pts_all[i][1], "weight": wts[i]} for i in range(n_points)]
    cands = [{"id": f"c{i:02d}", "lon": cands_all[i][0], "lat": cands_all[i][1], "category": ctx["category"],
              "kind": "hypothetical", "cost": cands_all[i][2]} for i in range(n_candidates)]
    k = max_selected if budget_max_selected is None else budget_max_selected
    top = sorted((c["cost"] for c in cands), reverse=True)[:k]
    budget = int(budget_ratio * sum(top))
    return {"schema_version": "city-plan-v2", "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"],
            "category": ctx["category"], "control_points": pts, "candidates": cands, "budget": budget,
            "max_selected": max_selected, "coverage_radius_m": radius_m, "required_ids": [], "excluded_ids": [],
            "selected_ids": []}
