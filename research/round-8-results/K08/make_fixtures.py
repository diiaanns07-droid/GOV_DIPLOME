"""K08 R8: детерминированные фикстуры city-plan-v2 на реальных срезах c a5b5e2d.

Контрольные точки и кандидаты — сетка внутри bbox (ввод «пользователя»), стоимости/веса/бюджет — synthetic demo.
Записи срезов (Overture) не меняются. Usage: python make_fixtures.py --app-root APP --out DIR
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import planlib as P

def grid(bb, nx, ny, pad=0.12):
    out = []
    for j in range(ny):
        for i in range(nx):
            fx = pad + (1 - 2 * pad) * (i / (nx - 1) if nx > 1 else 0.5)
            fy = pad + (1 - 2 * pad) * (j / (ny - 1) if ny > 1 else 0.5)
            out.append((round(bb[0] + (bb[2] - bb[0]) * fx, 6), round(bb[1] + (bb[3] - bb[1]) * fy, 6)))
    return out

SPECS = [
    # name, city, category, points grid, candidate grid, costs, budget, max_selected, radius, required, excluded, selected
    ("shymkent_school_demo", "shymkent", "school", (3, 3), (3, 2), [120, 90, 150, 60, 200, 80], 300, 3, 400, [], ["c6"], ["c1"]),
    ("astana_clinic_demo", "astana", "outpatient_clinic", (4, 2), (4, 2), [50, 70, 40, 90, 60, 30, 80, 100], 150, 2, 300, ["c3"], [], ["c3", "c8"]),
    ("astana_clinic_infeasible", "astana", "outpatient_clinic", (2, 2), (2, 2), [500, 600, 700, 800], 900, 3, 300, ["c1", "c2"], [], []),
]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app-root", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(); ctx = P.Context(a.app_root); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    man = {"fixtures_schema": "k08-r8-fixtures/v1", "app_root_note": "реальные срезы data.js сборки; см. snapshot",
           "synthetic": ["control_points.weight", "candidates.cost", "candidates (места)", "budget", "max_selected", "coverage_radius_m",
                         "required_ids/excluded_ids/selected_ids"],
           "observed_secondary": ["записи Overture в срезе (web/data.js)"], "fixtures": []}
    for name, city, cat, pg, cg, costs, budget, ms, rad, req, exc, sel in SPECS:
        bb = ctx.city(city)["bbox"]
        pts = [{"id": f"p{k+1}", "lon": x, "lat": y, "weight": 1 + (k * 7) % 10} for k, (x, y) in enumerate(grid(bb, *pg))]
        cands = [{"id": f"c{k+1}", "lon": x, "lat": y, "category": cat, "kind": "hypothetical", "cost": costs[k]}
                 for k, (x, y) in enumerate(grid(bb, *cg, pad=0.2))]
        sc = {"schema_version": P.SCHEMA, "city_id": city, "source_snapshot": P.source_snapshot(ctx, city), "category": cat,
              "control_points": pts, "candidates": cands, "budget": budget, "max_selected": ms, "coverage_radius_m": rad,
              "required_ids": req, "excluded_ids": exc, "selected_ids": sel}
        P.validate_plan_scenario(sc, ctx)
        (out / f"{name}.json").write_text(json.dumps(sc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        man["fixtures"].append({"file": f"{name}.json", "city_id": city, "category": cat, "source_snapshot": sc["source_snapshot"],
                                "kind": "synthetic demo inputs over real slice"})
    (out / "fixtures_manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(len(man["fixtures"]), "fixtures")

if __name__ == "__main__":
    main()
