"""Stage 3: timing of the oracle's exact search on SYNTHETIC problems at moderate and maximum spec size.
  python3 benchmark.py [--json out/benchmark.json] [--export-problems out/bench_problems.json]
moderate: 10 candidates, 10 points, max_selected 3;  max: 16 candidates, 25 points, max_selected 5, budget 1e6;
max_all_feasible: the same size where all 6885 subsets of size <= 5 fit the budget.
The exported problems ({name: {context, scenario}}) can be fed to another implementation and checked with
compare_candidate.py. Timings are for this Python oracle only, not for the browser.
"""
import argparse, json, os, platform, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_oracle as O

CTX = {"city_id": "synthetic-grid", "bbox": [50.0, 40.0, 50.03, 40.03], "source_snapshot": "synthetic-grid-v1"}


def problem(rng, n_c, n_p, max_sel, budget):
    u = lambda: (rng.uniform(50.0, 50.03), rng.uniform(40.0, 40.03))
    recs = [dict(zip(("lon", "lat"), u()), id=f"s{i}", group="school") for i in range(4)]
    pts = [dict(zip(("lon", "lat"), u()), id=f"p{i:02d}", weight=rng.randint(1, 100)) for i in range(n_p)]
    cands = [dict(zip(("lon", "lat"), u()), id=f"c{i:02d}", category="school", kind="hypothetical",
                  cost=rng.randint(1, 1000) * 1000) for i in range(n_c)]
    sc = {"schema_version": "city-plan-v2", "city_id": CTX["city_id"], "source_snapshot": CTX["source_snapshot"],
          "category": "school", "control_points": pts, "candidates": cands, "budget": budget, "max_selected": max_sel,
          "coverage_radius_m": 500, "required_ids": [], "excluded_ids": [], "selected_ids": []}
    return dict(CTX, records=recs), sc


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json"); ap.add_argument("--export-problems")
    ap.add_argument("--repeat", type=int, default=3)
    a = ap.parse_args()
    rng = random.Random(16_25_5)
    probs = {"moderate_10c_10p_k3": problem(rng, 10, 10, 3, 1_500_000 // 2),
             "max_16c_25p_k5": problem(rng, 16, 25, 5, 1_000_000)}
    # worst case for the search: every subset of size <= 5 is within budget (costs 1..1000)
    ctx, sc = problem(rng, 16, 25, 5, 1_000_000)
    for c in sc["candidates"]:
        c["cost"] //= 1000
    probs["max_16c_25p_k5_all_feasible"] = (ctx, sc)
    out = {"python": platform.python_version(), "machine": platform.machine(), "results": {}}
    for name, (ctx, sc) in probs.items():
        times = []
        for _ in range(a.repeat):
            t = time.perf_counter(); r = O.optimize(ctx, sc); times.append(time.perf_counter() - t)
        out["results"][name] = {"seconds_min": round(min(times), 4), "seconds_max": round(max(times), 4),
                                "evaluated": r["evaluated"], "feasible_count": r["feasible_count"], "status": r["status"],
                                "winners": {n: v["selected_ids"] for n, v in r["objectives"].items()},
                                "pareto_points": len(r["pareto"]), "problem_digest": r["problem_digest"]}
    print(json.dumps(out, indent=1))
    if a.json:
        os.makedirs(os.path.dirname(a.json) or ".", exist_ok=True)
        json.dump(out, open(a.json, "w"), indent=1)
    if a.export_problems:
        json.dump({n: {"context": c, "scenario": s} for n, (c, s) in probs.items()}, open(a.export_problems, "w"), indent=1)


if __name__ == "__main__":
    main()
