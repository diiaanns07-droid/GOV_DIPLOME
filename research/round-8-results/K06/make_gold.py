"""K06 round 8 stage 2: fixed-seed small city-plan-v2 problems with independent gold outputs.

  python3 make_gold.py [--app-root <city-evidence copy>] [--out fixtures/gold_cases.json]

Produces:
  * named SYNTHETIC edge cases (budget=0, ties, required conflicts, no baseline, no candidates, Pareto duplicates,
    permutations of arrays and of ID names);
  * fixed-seed SYNTHETIC random problems on a synthetic bbox;
  * with --app-root: problems on REAL slice records (Overture records of the BUILD's data.js, provenance recorded)
    with SYNTHETIC control points, candidates and costs (user-style inputs, not municipal data).
Gold = gold_bruteforce.solve (independent code). The oracle is NOT used to make the gold.
"""
import argparse, copy, hashlib, json, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gold_bruteforce as G

SYN_CTX = {"city_id": "synthetic-grid", "bbox": [50.0, 40.0, 50.03, 40.03], "source_snapshot": "synthetic-grid-v1"}


def sc_base(ctx, category="school", **kw):
    sc = {"schema_version": "city-plan-v2", "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"],
          "category": category, "control_points": [], "candidates": [], "budget": 0, "max_selected": 0,
          "coverage_radius_m": 500, "required_ids": [], "excluded_ids": [], "selected_ids": []}
    sc.update(kw)
    return sc


def pt(i, lon, lat, w=1):
    return {"id": f"p{i}", "lon": lon, "lat": lat, "weight": w}


def cd(cid, lon, lat, cost, cat="school"):
    return {"id": cid, "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical", "cost": cost}


def named_cases():
    ctx = dict(SYN_CTX, records=[{"id": "s1", "lon": 50.0, "lat": 40.0, "group": "school"},
                                 {"id": "s2", "lon": 50.03, "lat": 40.03, "group": "school"}])
    pts = [pt(1, 50.01, 40.01, 3), pt(2, 50.02, 40.005, 1), pt(3, 50.025, 40.025, 2)]
    cands = [cd("c1", 50.012, 40.011, 400), cd("c2", 50.021, 40.006, 250), cd("c3", 50.015, 40.02, 300),
             cd("c4", 50.028, 40.012, 150)]
    out = []

    def add(name, ctx_, sc):
        out.append({"case": name, "kind": "synthetic", "context": ctx_, "scenario": sc})

    add("budget_zero", ctx, sc_base(ctx, control_points=pts, candidates=cands, budget=0, max_selected=3))
    add("budget_full_max3", ctx, sc_base(ctx, control_points=pts, candidates=cands, budget=1000, max_selected=3))
    # ties: c1 and c1b identical place and cost -> equal plans, winner by sorted IDs
    add("tie_identical_candidates", ctx, sc_base(ctx, control_points=pts, candidates=cands + [cd("c1b", 50.012, 40.011, 400)],
                                                 budget=600, max_selected=2))
    # tie between a candidate and a source record at the same point (metrics unaffected by the tie rule)
    add("tie_candidate_on_source", ctx, sc_base(ctx, control_points=pts, candidates=[cd("on_s1", 50.0, 40.0, 10)] + cands[:2],
                                                budget=500, max_selected=2))
    add("required_over_budget", ctx, sc_base(ctx, control_points=pts, candidates=cands, budget=300, max_selected=3, required_ids=["c1"]))
    add("required_over_count", ctx, sc_base(ctx, control_points=pts, candidates=cands, budget=1000, max_selected=1, required_ids=["c1", "c2"]))
    add("required_and_excluded_ok", ctx, sc_base(ctx, control_points=pts, candidates=cands, budget=800, max_selected=3,
                                                 required_ids=["c4"], excluded_ids=["c2"]))
    ctx0 = dict(SYN_CTX, records=[])
    add("no_baseline", ctx0, sc_base(ctx0, control_points=pts, candidates=cands, budget=700, max_selected=2))
    add("no_baseline_budget_zero", ctx0, sc_base(ctx0, control_points=pts, candidates=cands, budget=0, max_selected=2))
    add("no_candidates", ctx, sc_base(ctx, control_points=pts, candidates=[], budget=1000, max_selected=5))
    # Pareto duplicates: two different plans with equal (cost, weighted_sum): mirror candidates around a single point
    dctx = dict(SYN_CTX, records=[{"id": "far", "lon": 50.0, "lat": 40.0, "group": "school"}])
    add("pareto_duplicates", dctx, sc_base(dctx, control_points=[pt(1, 50.015, 40.015, 1)],
                                           candidates=[cd("e", 50.016, 40.015, 100), cd("w", 50.014, 40.015, 100),
                                                       cd("n", 50.015, 40.016, 120)], budget=500, max_selected=2))
    # other category in records must be ignored
    mctx = dict(SYN_CTX, records=ctx["records"] + [{"id": "clin", "lon": 50.01, "lat": 40.01, "group": "outpatient_clinic"}])
    add("other_category_ignored", mctx, sc_base(mctx, control_points=pts, candidates=cands, budget=700, max_selected=2))
    return out


def permuted(case, rng, rename):
    c = copy.deepcopy(case)
    sc = c["scenario"]
    for k in ("control_points", "candidates", "required_ids", "excluded_ids"):
        rng.shuffle(sc[k])
    rng.shuffle(c["context"]["records"])
    if rename:
        # rename candidate IDs preserving their lexicographic order (so ID tie-breaks map 1:1)
        old = sorted(x["id"] for x in sc["candidates"])
        new = {o: f"z{i:02d}_{o}" for i, o in enumerate(old)}
        for x in sc["candidates"]:
            x["id"] = new[x["id"]]
        for k in ("required_ids", "excluded_ids"):
            sc[k] = [new[x] for x in sc[k]]
        c["id_map"] = new
    c["case"] += "__perm" + ("_renamed" if rename else "")
    c["permutation_of"] = case["case"]
    return c


def random_cases(rng, n, ctx, records, prefix, kind, category):
    out = []
    bb = ctx["bbox"]
    for i in range(n):
        u = lambda: (rng.uniform(bb[0], bb[2]), rng.uniform(bb[1], bb[3]))
        # varied weights, several points and candidates so that the three objectives often disagree
        pts = [dict(zip(("lon", "lat"), u()), id=f"p{j}", weight=rng.choice([1, 1, 2, 5, 20, 100])) for j in range(rng.randint(1, 10))]
        cands = [cd(f"k{j}", *u(), rng.choice([100, 150, 200, 250, 300, 400]), category) for j in range(rng.randint(0, 9))]
        budget = rng.choice([0, 200, 400, 500, 700, 1000])
        req = [cands[0]["id"]] if cands and rng.random() < 0.25 else []
        exc = [cands[-1]["id"]] if len(cands) > 1 and rng.random() < 0.25 else []
        sc = sc_base(ctx, category, control_points=pts, candidates=cands, budget=budget, max_selected=rng.choice([0, 1, 1, 2, 2, 3]),
                     coverage_radius_m=rng.choice([100, 200, 300, 600]), required_ids=req, excluded_ids=exc)
        out.append({"case": f"{prefix}_{i:02d}", "kind": kind, "context": dict(ctx, records=records), "scenario": sc})
    return out


def real_contexts(app_root):
    txt = open(os.path.join(app_root, "web", "data.js"), "rb").read()
    D = json.loads(re.search(rb"window\.CITY_EVIDENCE\s*=\s*(\{.*\})\s*;\s*$", txt, re.S).group(1))
    man = os.path.join(app_root, "_extract_manifest.json")
    commit = json.load(open(man))["commit"] if os.path.exists(man) else None
    prov = {"build_commit": commit, "file": "prototypes/city-evidence/web/data.js", "sha256": hashlib.sha256(txt).hexdigest()}
    for city in D["city_order"]:
        c = D["cities"][city]
        recs = [{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "group": p["group"]} for p in c["places"]]
        snap = "k06-r8:" + hashlib.sha256(json.dumps(sorted([r["id"], r["lon"], r["lat"], r["group"]] for r in recs)).encode()).hexdigest()[:16]
        yield city, {"city_id": city, "bbox": c["bbox"], "source_snapshot": snap}, recs, prov


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app-root")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "gold_cases.json"))
    a = ap.parse_args()
    rng = random.Random(8_2026_10_05)
    cases = named_cases()
    cases += [permuted(c, rng, rename) for c in list(cases) for rename in (False, True)]
    syn_recs = [{"id": f"s{i}", "lon": rng.uniform(50.0, 50.03), "lat": rng.uniform(40.0, 40.03), "group": g}
                for i, g in enumerate(["school"] * 3 + ["outpatient_clinic"] * 2)]
    cases += random_cases(rng, 24, SYN_CTX, syn_recs, "syn_random", "synthetic", "school")
    # rejection-sample 12 SYNTHETIC problems where the gold winners of the three objectives differ
    # (selection uses only the independent gold solver, so it does not bias the oracle comparison)
    div, tries = [], 0
    while len(div) < 12 and tries < 5000:
        tries += 1
        c = random_cases(rng, 1, SYN_CTX, syn_recs, "syn_divergent", "synthetic", "school")[0]
        g = G.solve(c["context"]["records"], c["scenario"])
        if g["status"] == "optimal" and len({tuple(v["selected_ids"]) for v in g["objectives"].values()}) > 1:
            c["case"] = f"syn_divergent_{len(div):02d}"
            div.append(c)
    cases += div
    provenance = None
    if a.app_root:
        for city, ctx, recs, provenance in real_contexts(a.app_root):
            for cat in ("school", "outpatient_clinic"):
                cases += random_cases(rng, 6, ctx, recs, f"real_{city}_{cat}", "real_records_synthetic_inputs", cat)
    for c in cases:
        c["gold"] = G.solve(c["context"]["records"], c["scenario"])
    doc = {"schema": "k06-plan-gold-v1", "metric_version": "haversine-mm-v1",
           "spec": "research/round-8/CORE_SPEC.txt @ codex/research-import-2026-10-05 c3f6c00",
           "gold_solver": "gold_bruteforce.py (independent of plan_oracle.py)", "seed": 8_2026_10_05,
           "real_records_provenance": provenance,
           "note": "costs/budgets/points/candidates are synthetic user-style inputs; distances are straight-line mm",
           "cases": cases}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print(len(cases), "cases ->", a.out)


if __name__ == "__main__":
    main()
