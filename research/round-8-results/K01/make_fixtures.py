"""Generate city-plan-v2 fixtures for both cities from an extracted prototype (deterministic).
  python3 make_fixtures.py --app-root APP --build-sha SHA
fixtures/real/context_<city>.json  — slice context derived from the real prototype data (provenance: build SHA, file hashes)
fixtures/synthetic/*.json          — synthetic scenarios: points, weights, candidates, costs, budgets are invented demo values
fixtures/EXPECTED.json             — expected verdict per fixture (context city, valid/code)
fixtures/MANIFEST.json             — sha256/bytes of every fixture
"""
import hashlib, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planv2_ref as R  # noqa: E402

args = sys.argv[1:]
APP = Path(args[args.index("--app-root") + 1])
BUILD_SHA = args[args.index("--build-sha") + 1]
data = R.load_data(APP)
FX = HERE / "fixtures"
(FX / "real").mkdir(parents=True, exist_ok=True)
(FX / "synthetic").mkdir(parents=True, exist_ok=True)
ctx = {c: R.context(data, c) for c in ("shymkent", "astana")}
for c, x in ctx.items():
    cc = data["cities"][c]
    (FX / "real" / f"context_{c}.json").write_text(json.dumps({
        "kind": "derived_from_observed_secondary", "city_id": c, "bbox": x["bbox"], "source_snapshot": x["source_snapshot"],
        "release": x["release"], "provenance": {"build_branch": "claude/beautiful-clarke-sbzomj", "build_sha": BUILD_SHA,
        "data_js_sha256": hashlib.sha256((APP / "web/data.js").read_bytes()).hexdigest(),
        "places_social_sha256": cc["files"]["places_social"]["sha256"], "places_digest": R.places_digest(data, c),
        "snapshot_rule": "sha256(JSON.stringify(['city-plan-v2', city, release, places_social_sha256, placesDigest, 'haversine-mm-v1']))"},
        "category_records": {g: sum(1 for p in cc["places"] if p["group"] == g) for g in ("school", "outpatient_clinic")}},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def lerp(bb, fx, fy):
    return round(bb[0] + (bb[2] - bb[0]) * fx, 6), round(bb[1] + (bb[3] - bb[1]) * fy, 6)


def base(city, category="school", n_pts=5, n_cand=4):
    bb = ctx[city]["bbox"]
    pts = []
    for i in range(n_pts):
        lon, lat = lerp(bb, 0.1 + 0.8 * ((i * 7) % n_pts) / max(1, n_pts), 0.15 + 0.7 * ((i * 3) % n_pts) / max(1, n_pts))
        pts.append({"id": f"cp-{i + 1:02d}", "lon": lon, "lat": lat, "weight": 1 + (i * 13) % 5})
    cands = []
    for j in range(n_cand):
        lon, lat = lerp(bb, 0.2 + 0.6 * ((j * 5) % max(1, n_cand)) / max(1, n_cand), 0.8 - 0.6 * j / max(1, n_cand))
        cands.append({"id": f"cand-{j + 1:02d}", "lon": lon, "lat": lat, "category": category, "kind": "hypothetical",
                      "cost": 1000 * (3 + (j * 7) % 9)})
    return {"schema_version": "city-plan-v2", "city_id": city, "source_snapshot": ctx[city]["source_snapshot"], "category": category,
            "control_points": pts, "candidates": cands, "budget": 12000, "max_selected": min(2, n_cand), "coverage_radius_m": 500,
            "required_ids": [], "excluded_ids": [], "selected_ids": [c["id"] for c in cands[:1]]}


FIX, EXP = {}, {}


def add(name, ctx_city, obj=None, valid=True, code=None, note="", raw=None):
    b = raw if raw is not None else (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    FIX[name] = b
    EXP[name] = {"context_city": ctx_city, "valid": valid, **({"code": code} if code else {}), **({"note": note} if note else {})}


def mut(city, f, **kw):
    o = base(city, **kw); f(o); return o


for city, pre in (("shymkent", "shy"), ("astana", "ast")):
    other = "astana" if city == "shymkent" else "shymkent"
    add(f"{pre}_valid_basic.json", city, base(city))
    add(f"{pre}_valid_clinic_constraints.json", city, mut(city, lambda o: o.update(required_ids=["cand-02"], excluded_ids=["cand-03"],
        selected_ids=["cand-02", "cand-01"]), category="outpatient_clinic"))
    add(f"{pre}_valid_forged_derived.json", city, mut(city, lambda o: o.update(derived_results={"objectives": {"mean": {"ids": ["cand-04"],
        "weighted_sum_mm": 0}}, "status": "optimal", "problem_digest": "pd1:" + "0" * 64})), note="derived_results forged: must be dropped")
    add(f"{pre}_valid_limits.json", city, mut(city, lambda o: o.update(budget=1000000, max_selected=5, coverage_radius_m=5000), n_pts=25, n_cand=16))
    add(f"{pre}_valid_empty_candidates.json", city, mut(city, lambda o: o.update(budget=0, max_selected=0, selected_ids=[]), n_cand=0))
    add(f"{pre}_invalid_foreign_snapshot.json", city, mut(city, lambda o: o.update(source_snapshot=ctx[other]["source_snapshot"])), False, "foreign_snapshot")
    add(f"{pre}_invalid_foreign_city.json", other, base(city), False, "foreign_city", "valid file of the other city opened in this context")
    add(f"{pre}_invalid_outside_bbox.json", city, mut(city, lambda o: o["candidates"][0].update(lon=o["candidates"][0]["lon"] + 0.5)), False, "outside_bbox")
    add(f"{pre}_invalid_weight_fraction.json", city, mut(city, lambda o: o["control_points"][0].update(weight=1.5)), False, "bad_weight")
    add(f"{pre}_invalid_cost_zero.json", city, mut(city, lambda o: o["candidates"][1].update(cost=0)), False, "bad_cost")
    add(f"{pre}_invalid_conflict.json", city, mut(city, lambda o: o.update(required_ids=["cand-01"], excluded_ids=["cand-01"])), False, "constraint_conflict")
    add(f"{pre}_invalid_unknown_ref.json", city, mut(city, lambda o: o.update(selected_ids=["cand-99"])), False, "unknown_ref")
    add(f"{pre}_invalid_17_candidates.json", city, base(city, n_cand=17), False, "bad_candidates")

S = ctx["shymkent"]["source_snapshot"]
b = base("shymkent")
add("shy_invalid_26_points.json", "shymkent", base("shymkent", n_pts=26), False, "bad_points")
add("shy_invalid_dup_candidate_id.json", "shymkent", mut("shymkent", lambda o: o["candidates"][1].update(id="cand-01")), False, "duplicate_id")
add("shy_invalid_kind.json", "shymkent", mut("shymkent", lambda o: o["candidates"][0].update(kind="planned")), False, "bad_kind")
add("shy_invalid_candidate_category.json", "shymkent", mut("shymkent", lambda o: o["candidates"][0].update(category="outpatient_clinic")), False, "bad_category")
add("shy_invalid_extra_field.json", "shymkent", mut("shymkent", lambda o: o.update(script_url="https://example.org/x.js")), False, "unknown_field")
add("shy_invalid_missing_field.json", "shymkent", mut("shymkent", lambda o: o.pop("excluded_ids")), False, "missing_field")
add("shy_invalid_url_id.json", "shymkent", mut("shymkent", lambda o: o["control_points"][0].update(id="https://evil.example")), False, "bad_id")
add("shy_invalid_long_id.json", "shymkent", mut("shymkent", lambda o: o["control_points"][0].update(id="a" * 65)), False, "bad_id")
add("shy_invalid_bool_weight.json", "shymkent", mut("shymkent", lambda o: o["control_points"][0].update(weight=True)), False, "bad_weight")
add("ast_invalid_budget.json", "astana", mut("astana", lambda o: o.update(budget=1000001)), False, "bad_budget")
add("ast_invalid_max_selected.json", "astana", mut("astana", lambda o: o.update(max_selected=6)), False, "bad_max_selected")
add("ast_invalid_radius.json", "astana", mut("astana", lambda o: o.update(coverage_radius_m=99)), False, "bad_radius")
add("ast_invalid_v1_schema.json", "astana", {"schema_version": "city-whatif-v1", "city_id": "astana", "source_snapshot": ctx["astana"]["source_snapshot"],
    "category": "school", "control_points": [], "candidates": [], "budget": 0, "max_selected": 0, "coverage_radius_m": 100,
    "required_ids": [], "excluded_ids": [], "selected_ids": []}, False, "bad_version")
txt = json.dumps(b, indent=1)
add("shy_valid_unicode_escaped_keys.json", "shymkent", raw=txt.replace('"city_id"', '"\\u0063ity_id"', 1).replace('"budget"', '"bud\\u0067et"', 1).encode(),
    note="keys spelled with \\u escapes are the same keys")
add("shy_invalid_dup_key_via_escape.json", "shymkent", raw=txt.replace('"budget": 12000', '"budget": 12000, "bud\\u0067et": 0', 1).encode(), valid=False, code="duplicate_key")
add("shy_invalid_nan.json", "shymkent", raw=txt.replace('"budget": 12000', '"budget": NaN', 1).encode(), valid=False, code="non_finite")
add("shy_invalid_1e999.json", "shymkent", raw=txt.replace('"budget": 12000', '"budget": 1e999', 1).encode(), valid=False, code="non_finite")
add("shy_invalid_bad_utf8.json", "shymkent", raw=txt.replace('"cp-01"', '"cp-\xff"', 1).encode("latin-1"), valid=False, code="bad_encoding")
big = txt.encode()
add("shy_invalid_too_large.json", "shymkent", raw=big[:-1] + b" " * (R.MAX_BYTES - len(big) + 1) + b"}", valid=False, code="too_large")
add("shy_valid_exactly_256k.json", "shymkent", raw=big[:-1] + b" " * (R.MAX_BYTES - len(big)) + b"}", note="exactly 262144 bytes")

for name, b in FIX.items():
    (FX / "synthetic" / name).write_bytes(b)
EXP_DOC = {"note": "SYNTHETIC scenarios (invented points/weights/costs/budgets) on REAL slice contexts of build " + BUILD_SHA[:7],
           "build_sha": BUILD_SHA, "fixtures": EXP}
(FX / "EXPECTED.json").write_text(json.dumps(EXP_DOC, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
man = []
for p in sorted(FX.rglob("*.json")):
    if p.name == "MANIFEST.json":
        continue
    bts = p.read_bytes()
    man.append({"path": p.relative_to(FX).as_posix(), "bytes": len(bts), "sha256": hashlib.sha256(bts).hexdigest()})
(FX / "MANIFEST.json").write_text(json.dumps({"build_sha": BUILD_SHA, "files": man}, indent=1) + "\n", encoding="utf-8", newline="\n")
print(f"{len(FIX)} synthetic fixtures, 2 real contexts, {len(man)} files in MANIFEST")
