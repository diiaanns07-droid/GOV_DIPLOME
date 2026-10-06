"""K06 round 9 stage 2: small exhaustive city-resilience-v1 cases with independent gold (resilience_gold.solve).
  python3 make_resilience_cases.py [--app-root <city-evidence copy>] [--out fixtures/resilience_gold.json]
SYNTHETIC named cases + fixed-seed SYNTHETIC random cases; with --app-root also REAL source records of both cities
(data.js of that BUILD, provenance recorded) with SYNTHETIC points/candidates/costs and user-chosen exclusions.
must_reject: envelopes that the spec forbids (expected error code from the K06 reference, informational)."""
import argparse, copy, hashlib, json, os, random, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import resilience_gold as RG

LON = 10.0
MER = {"city_id": "synthetic-meridian", "bbox": [9.99, -0.01, 10.01, 0.05], "source_snapshot": "synthetic-v1"}


def plan(ctx, pts, cands, **kw):
    p = {"schema_version": "city-plan-v2", "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"],
         "category": "school", "control_points": pts, "candidates": cands, "budget": 10, "max_selected": 1,
         "coverage_radius_m": 300, "required_ids": [], "excluded_ids": [], "selected_ids": []}
    p.update(kw)
    return p


def P(i, lat, w=1, lon=LON):
    return {"id": i, "lon": lon, "lat": lat, "weight": w}


def C(i, lat, cost=1, lon=LON, cat="school"):
    return {"id": i, "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical", "cost": cost}


def S(i, lat, lon=LON, g="school"):
    return {"id": i, "lon": lon, "lat": lat, "group": g}


def env(p, cases):
    return {"schema_version": "city-resilience-v1", "plan": p, "cases": cases}


def case(i, ids, label=None):
    return {"id": i, "label": label or f"без {', '.join(ids)}", "disabled_source_ids": ids}


def named():
    recs = [S("S1", 0.010), S("S2", 0.030)]
    ctx = dict(MER, records=recs)
    pts = [P("P1", 0.010), P("P2", 0.030), P("P3", 0.0125, 5)]
    cands = [C("A", 0.011), C("B", 0.029)]
    out = []
    add = lambda n, c, e: out.append({"case": n, "kind": "synthetic", "context": c, "envelope": e})
    # hand example (see test): nominal A, robust B, price > 0
    add("nominal_vs_robust_differ", ctx, env(plan(ctx, pts, cands), [case("x2", ["S2"])]))
    add("price_zero_plans_differ", ctx, env(plan(ctx, pts[:2], cands), [case("x2", ["S2"])]))
    add("all_sources_excluded", ctx, env(plan(ctx, pts, cands, max_selected=2), [case("none", ["S1", "S2"])]))
    add("all_sources_excluded_budget0", ctx, env(plan(ctx, pts, cands, budget=0), [case("none", ["S1", "S2"])]))
    add("no_candidates", ctx, env(plan(ctx, pts, []), [case("x1", ["S1"])]))
    add("equal_worst_cases", ctx, env(plan(ctx, pts, cands), [case("x2a", ["S2"]), case("x2b", ["S2"], "дубль x2")]))
    add("symmetric_worst_tie", dict(MER, records=[S("S1", 0.000), S("S2", 0.040)]),
        env(plan(dict(MER), [P("P1", 0.020)], [C("M", 0.020, 5)], budget=0), [case("a", ["S1"]), case("b", ["S2"])]))
    add("required_infeasible", ctx, env(plan(ctx, pts, [C("A", 0.011, 20), C("B", 0.029)], required_ids=["A"]), [case("x2", ["S2"])]))
    add("required_kept", ctx, env(plan(ctx, pts, cands, required_ids=["A"], max_selected=2), [case("x1", ["S1"])]))
    add("unknown_in_case_only", dict(MER, records=[S("S1", 0.010)]), env(plan(dict(MER), pts, cands, budget=0), [case("x1", ["S1"])]))
    add("cost_tiebreak", ctx, env(plan(ctx, [P("P2", 0.030)], [C("B", 0.029, 3), C("B2", 0.029, 2)]), [case("x2", ["S2"])]))
    add("id_tiebreak", ctx, env(plan(ctx, [P("P2", 0.030)], [C("Bz", 0.029, 2), C("Ba", 0.029, 2)]), [case("x2", ["S2"])]))
    for c in out:
        c["context"]["records"] = c["context"].get("records", recs)
        c["envelope"]["plan"]["city_id"] = c["context"]["city_id"]
    return out


def must_reject():
    ctx = dict(MER, records=[S("S1", 0.010), S("S2", 0.030)])
    good = env(plan(ctx, [P("P1", 0.010)], [C("A", 0.011)]), [case("x", ["S1"])])
    def m(fn):
        e = copy.deepcopy(good); fn(e); return e
    thirteen = m(lambda e: e["plan"].update(candidates=[C(f"k{i:02d}", 0.011) for i in range(13)]))
    return [
        ("candidate_id_as_source", m(lambda e: e["cases"][0].update(disabled_source_ids=["A"])), "candidate_not_source"),
        ("unknown_source", m(lambda e: e["cases"][0].update(disabled_source_ids=["S9"])), "unknown_source"),
        ("base_reserved", m(lambda e: e["cases"][0].update(id="base")), "reserved_id"),
        ("empty_label", m(lambda e: e["cases"][0].update(label="")), "bad_label"),
        ("control_char_label", m(lambda e: e["cases"][0].update(label="a\u0007b")), "bad_label"),
        ("label_121", m(lambda e: e["cases"][0].update(label="я" * 121)), "bad_label"),
        ("disabled_empty", m(lambda e: e["cases"][0].update(disabled_source_ids=[])), "bad_disabled"),
        ("disabled_duplicate", m(lambda e: e["cases"][0].update(disabled_source_ids=["S1", "S1"])), "duplicate_id"),
        ("duplicate_case_id", m(lambda e: e["cases"].append(case("x", ["S2"]))), "duplicate_id"),
        ("eight_user_cases", m(lambda e: e.update(cases=[case(f"c{i}", ["S1"]) for i in range(8)])), "bad_cases"),
        ("zero_cases", m(lambda e: e.update(cases=[])), "bad_cases"),
        ("derived_field", m(lambda e: e.update(derived_results={})), "unexpected_field"),
        ("case_extra_field", m(lambda e: e["cases"][0].update(note="x")), "bad_case"),
        ("bad_version", m(lambda e: e.update(schema_version="city-resilience-v0")), "bad_version"),
        ("too_many_candidates_13", thirteen, "too_many_candidates"),
        ("plan_invalid_inside", m(lambda e: e["plan"].update(budget=-1)), "out_of_range"),
    ], ctx


def rnd(rng, n, ctx, recs, prefix, kind, cat):
    out, bb = [], ctx["bbox"]
    src_ids = [r["id"] for r in recs if r["group"] == cat]
    for i in range(n):
        u = lambda: (rng.uniform(bb[0], bb[2]), rng.uniform(bb[1], bb[3]))
        pts = [dict(zip(("lon", "lat"), u()), id=f"p{j}", weight=rng.choice([1, 1, 2, 5, 20])) for j in range(rng.randint(1, 6))]
        cands = [dict(zip(("lon", "lat"), u()), id=f"k{j}", category=cat, kind="hypothetical", cost=rng.choice([100, 200, 300]))
                 for j in range(rng.randint(0, 6))]
        p = plan(ctx, pts, cands, category=cat, budget=rng.choice([0, 200, 400, 700]), max_selected=rng.choice([0, 1, 2, 3]),
                 coverage_radius_m=rng.choice([100, 300, 600]))
        if cands and rng.random() < 0.2:
            p["required_ids"] = [cands[0]["id"]]
        cs = []
        for k in range(rng.randint(1, 3)):
            if src_ids:
                cs.append(case(f"c{k}", sorted(rng.sample(src_ids, rng.randint(1, min(3, len(src_ids)))))))
        if not cs:
            continue
        out.append({"case": f"{prefix}_{i:02d}", "kind": kind, "context": dict(ctx, records=recs), "envelope": env(p, cs)})
    return out


def real(app_root):
    txt = open(os.path.join(app_root, "web", "data.js"), "rb").read()
    D = json.loads(re.search(rb"window\.CITY_EVIDENCE\s*=\s*(\{.*\})\s*;\s*$", txt, re.S).group(1))
    man = os.path.join(app_root, "_extract_manifest.json")
    prov = {"build_commit": json.load(open(man))["commit"] if os.path.exists(man) else None,
            "file": "prototypes/city-evidence/web/data.js", "sha256": hashlib.sha256(txt).hexdigest()}
    for city in D["city_order"]:
        c = D["cities"][city]
        recs = [{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "group": p["group"]} for p in c["places"]]
        snap = "k06-r9:" + hashlib.sha256(json.dumps(sorted([r["id"], r["lon"], r["lat"], r["group"]] for r in recs)).encode()).hexdigest()[:16]
        yield city, {"city_id": city, "bbox": c["bbox"], "source_snapshot": snap}, recs, prov


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app-root")
    ap.add_argument("--out", default=os.path.join(HERE, "fixtures", "resilience_gold.json"))
    a = ap.parse_args()
    rng = random.Random(9_2026_10_06)
    cases = named()
    syn = [S(f"s{i}", rng.uniform(40.0, 40.03), lon=rng.uniform(50.0, 50.03)) for i in range(4)]
    grid = {"city_id": "synthetic-grid", "bbox": [50.0, 40.0, 50.03, 40.03], "source_snapshot": "synthetic-grid-v1"}
    cases += rnd(rng, 30, grid, syn, "syn_random", "synthetic", "school")
    prov = None
    if a.app_root:
        for city, ctx, recs, prov in real(a.app_root):
            for cat in ("school", "outpatient_clinic"):
                cases += rnd(rng, 5, ctx, recs, f"real_{city}_{cat}", "real_records_synthetic_inputs", cat)
    for c in cases:
        c["gold"] = RG.solve(c["context"]["records"], c["envelope"])
    rej, rctx = must_reject()
    doc = {"schema": "k06-resilience-gold-v1", "objective_version": "worst-lex-v1", "metric_version": "haversine-mm-v1",
           "spec": "research/round-9/CORE_SPEC.txt @ codex/research-import-2026-10-05 0ab1667",
           "gold_solver": "resilience_gold.py (independent of resilience_oracle.py)", "seed": 9_2026_10_06,
           "real_records_provenance": prov, "cases": cases,
           "must_reject": {"context": rctx, "items": [{"case": n, "envelope": e, "k06_code": code} for n, e, code in rej]},
           "note": "points, candidates, costs and exclusions are synthetic user-style inputs; exclusions are assumptions, not closures"}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(doc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(cases), "cases,", len(rej), "must_reject ->", a.out)


if __name__ == "__main__":
    main()
