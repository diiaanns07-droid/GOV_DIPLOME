// web/plan.js (city-plan-v2) vs the independent Python oracle (tests/expected_plans.json) + contract rules. Headless, no DOM.
// Usage: node tests/plan.cjs
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = path.join(__dirname, "..", "web");
const ctx0 = {}; vm.createContext(ctx0); ctx0.window = ctx0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx0, { filename: f });
const F = require(path.join(W, "facts.js"));
const X = require(path.join(W, "whatif.js"));
const PL = require(path.join(W, "plan.js"));
const D = ctx0.CITY_EVIDENCE;
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(detail).slice(0, 400) : "")); };
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || e.message; } };
const J = JSON.stringify;

const exp = JSON.parse(fs.readFileSync(path.join(__dirname, "expected_plans.json"), "utf8"));
// context for a case: synthetic equator "city" for hand fixtures, the real slice otherwise
function caseCtx(c) {
  if (c.kind === "synthetic_hand") {
    const data = { cities: { "synthetic-eq": { bbox: c.bbox, release: "synthetic", files: {}, places: c.places } } };
    return PL.makeContext(data, "synthetic-eq", F);
  }
  return PL.makeContext(D, c.city, F);
}
function caseScenario(c, ctx) {
  return PL.validatePlanScenario({ schema_version: PL.SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, ...c.scenario }, ctx);
}
const reversed = (sc) => ({ ...sc, control_points: sc.control_points.slice().reverse(), candidates: sc.candidates.slice().reverse(),
  required_ids: sc.required_ids.slice().reverse(), excluded_ids: sc.excluded_ids.slice().reverse(), selected_ids: sc.selected_ids.slice().reverse() });

// 1. manual plan evaluation = oracle (rows in mm, nearest with kind, metrics)
for (const c of exp.cases) {
  const ctx = caseCtx(c), sc = caseScenario(c, ctx), r = PL.evaluatePlan(ctx, sc, sc.selected_ids), e = c.expected.manual;
  const rowsOk = r.rows.every((row) => { const o = e.rows[row.id]; return o && row.before_mm === o.before_mm && row.after_mm === o.after_mm && row.delta_mm === o.delta_mm
    && J(row.nearest_before) === J(o.nearest_before) && J(row.nearest_after) === J(o.nearest_after); });
  const m = r.metrics;
  const mOk = m.unknown_count === e.unknown_count && m.weighted_sum_mm === e.weighted_sum_mm && m.max_mm === e.max_mm && m.covered_weight === e.covered_weight
    && m.total_weight === e.total_weight && m.cost === e.cost && J(r.selected_ids) === J(e.ids);
  check(`evaluatePlan = oracle: ${c.name}`, rowsOk && mOk, J({ m, e: { ...e, rows: undefined } }));
  const r2 = PL.evaluatePlan(ctx, reversed(sc), reversed(sc).selected_ids);
  check(`input order does not change the result: ${c.name}`, J(r2.metrics) === J(r.metrics) && PL.problemDigest(reversed(sc), F) === PL.problemDigest(sc, F));
}

// 2. hand geometry and semantics on the synthetic equator fixture
const hand = exp.cases.find((c) => c.name === "no_baseline"), hctx = caseCtx(hand), hsc = caseScenario(hand, hctx);
const empty = PL.evaluatePlan(hctx, hsc, []);
check("no baseline + empty plan: distance null (not 0), delta null, mean/max null", empty.rows.every((r) => r.before_mm === null && r.after_mm === null && r.delta_mm === null)
  && empty.metrics.unknown_count === 3 && empty.metrics.weighted_mean_mm === null && empty.metrics.max_mm === null && empty.metrics.covered_weight === 0);
const withC = PL.evaluatePlan(hctx, hsc, ["C3"]);
check("no baseline + candidate: after known, delta still null", withC.rows.every((r) => r.after_mm !== null && r.delta_mm === null));
const one = PL.mmOf(X.haversine(0, 0, 1, 0));
check("metric haversine-mm-v1: 1° on the equator = 111195080 mm", one === 111195080, one);
const tie = exp.cases.find((c) => c.name === "source_hyp_tie"), tctx = caseCtx(tie), tsc = caseScenario(tie, tctx);
check("equal mm: source record wins over hypothetical", PL.evaluatePlan(tctx, tsc, ["C1"]).rows[0].nearest_after.kind === "source");
const ex = exp.cases.find((c) => c.name === "excluded_and_required"), ectx = caseCtx(ex), esc = caseScenario(ex, ectx);
const ef = PL.evaluatePlan(ectx, esc, esc.selected_ids).feasibility;
check("manual plan feasibility lists reasons (excluded chosen, required missing)", !ef.feasible && ef.reasons.map((x) => x.code).sort().join() === "has_excluded,missing_required", J(ef));
const rq = exp.cases.find((c) => c.name === "required_cost_over_budget"), rctx = caseCtx(rq), rsc = caseScenario(rq, rctx);
check("manual plan over budget is reported, not silently changed", PL.evaluatePlan(rctx, rsc, rsc.selected_ids).feasibility.reasons[0].code === "over_budget");

// 3. contract city-plan-v2: validation and digests
const sh = PL.makeContext(D, "shymkent", F), ast = PL.makeContext(D, "astana", F);
const real = exp.cases.find((c) => c.name === "shymkent_school_16x25");
const base = () => JSON.parse(J({ schema_version: PL.SCHEMA, city_id: "shymkent", source_snapshot: sh.source_snapshot, ...real.scenario }));
check("valid 16×25 scenario accepted", code(() => PL.validatePlanScenario(base(), sh)) === "accepted");
check("context source records frozen (immutable)", Object.isFrozen(sh.places) && Object.isFrozen(sh.places[0]) && code(() => { "use strict"; sh.places[0].lon = 0; }) !== "accepted");
check("v2 snapshot differs from v1 snapshot and between cities", sh.source_snapshot !== X.sourceSnapshot(D, "shymkent", F) && sh.source_snapshot !== ast.source_snapshot);
const rej = (name, mut, want) => { const o = base(); mut(o); check(`rejects ${name} (${want})`, code(() => PL.validatePlanScenario(o, sh)) === want); };
rej("v1 scenario (no silent migration)", (o) => { o.schema_version = X.SCHEMA; }, "wrong_version");
rej("unknown version", (o) => { o.schema_version = "city-plan-v3"; }, "bad_version");
rej("Astana scenario in Shymkent context", (o) => { o.city_id = "astana"; }, "other_city");
rej("unknown city", (o) => { o.city_id = "almaty"; }, "bad_city");
rej("foreign snapshot", (o) => { o.source_snapshot = ast.source_snapshot; }, "foreign_snapshot");
rej("unknown field", (o) => { o.script = "alert(1)"; }, "unknown_field");
rej("missing field", (o) => { delete o.coverage_radius_m; }, "missing_field");
rej("26 control points", (o) => { o.control_points = Array.from({ length: 26 }, (_, k) => ({ ...o.control_points[0], id: "Q" + k })); }, "bad_points");
rej("0 control points", (o) => { o.control_points = []; }, "bad_points");
rej("17 candidates", (o) => { o.candidates.push({ ...o.candidates[0], id: "K17" }); }, "too_many_candidates");
rej("duplicate point id", (o) => { o.control_points[1].id = o.control_points[0].id; }, "duplicate_id");
rej("duplicate candidate id", (o) => { o.candidates[1].id = o.candidates[0].id; }, "duplicate_id");
rej("id longer than 64", (o) => { o.candidates[0].id = "x".repeat(65); }, "bad_id");
rej("id with markup", (o) => { o.control_points[0].id = "<b>x</b>"; }, "bad_id");
rej("weight 0", (o) => { o.control_points[0].weight = 0; }, "bad_weight");
rej("weight 1.5", (o) => { o.control_points[0].weight = 1.5; }, "bad_weight");
rej("weight 101", (o) => { o.control_points[0].weight = 101; }, "bad_weight");
rej("cost 0", (o) => { o.candidates[0].cost = 0; }, "bad_cost");
rej("cost 1000001", (o) => { o.candidates[0].cost = 1000001; }, "bad_cost");
rej("budget negative", (o) => { o.budget = -1; }, "bad_budget");
rej("budget not integer", (o) => { o.budget = 10.5; }, "bad_budget");
rej("max_selected 6", (o) => { o.max_selected = 6; }, "bad_max_selected");
rej("radius 99", (o) => { o.coverage_radius_m = 99; }, "bad_radius");
rej("radius 5001", (o) => { o.coverage_radius_m = 5001; }, "bad_radius");
rej("required unknown candidate", (o) => { o.required_ids = ["NOPE"]; }, "unknown_ref");
rej("selected unknown candidate", (o) => { o.selected_ids = ["NOPE"]; }, "unknown_ref");
rej("required ∩ excluded", (o) => { o.required_ids = ["K01"]; o.excluded_ids = ["K01"]; }, "required_excluded_overlap");
rej("duplicate in required", (o) => { o.required_ids = ["K01", "K01"]; }, "duplicate_id");
rej("candidate kind observed", (o) => { o.candidates[0].kind = "observed"; }, "bad_kind");
rej("candidate other category", (o) => { o.candidates[0].category = "outpatient_clinic"; }, "bad_category");
rej("candidate outside bbox", (o) => { o.candidates[0].lon = 70.5; }, "outside_bbox");
rej("point NaN-like string", (o) => { o.control_points[0].lat = "42.3"; }, "bad_coord");
rej("extra field in candidate", (o) => { o.candidates[0].url = "https://example.com"; }, "bad_shape");
check("derived_results field tolerated by validation (ignored)", code(() => PL.validatePlanScenario({ ...base(), derived_results: { forged: true } }, sh)) === "accepted");
const v = PL.validatePlanScenario(base(), sh);
check("problem digest ignores selected_ids; scenario digest includes them",
  PL.problemDigest({ ...v, selected_ids: [] }, F) === PL.problemDigest(v, F) && PL.scenarioDigest({ ...v, selected_ids: [] }, F) !== PL.scenarioDigest(v, F));
check("problem digest changes with budget / weight / cost / radius / required",
  new Set([PL.problemDigest(v, F), PL.problemDigest({ ...v, budget: v.budget + 1 }, F), PL.problemDigest({ ...v, coverage_radius_m: 401 }, F),
    PL.problemDigest({ ...v, required_ids: ["K01"] }, F),
    PL.problemDigest({ ...v, control_points: v.control_points.map((p, k) => (k ? p : { ...p, weight: p.weight + 1 })) }, F),
    PL.problemDigest({ ...v, candidates: v.candidates.map((c, k) => (k ? c : { ...c, cost: c.cost + 1 })) }, F)]).size === 6);

/*__OPT__*/
console.log(fails ? `${fails} FAILED` : "all plan checks passed");
process.exit(fails ? 1 : 0);
