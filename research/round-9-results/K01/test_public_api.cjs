// K01 round 9 stage 3: CORE_SPEC r9 — public evaluate/optimize/search must validate unverified objects (typed error, no compute).
//   node test_public_api.cjs --app-root APP     exit 1 = defect present (each case prints its minimal input)
const fs = require("fs"), path = require("path");
const { loadBuild } = require("./build_adapter.cjs");
const B = loadBuild(process.argv[process.argv.indexOf("--app-root") + 1]);
const R8 = path.join(__dirname, "..", "..", "round-8-results", "K01", "fixtures", "synthetic");
const sc0 = B.importV2(new Uint8Array(fs.readFileSync(path.join(R8, "shy_valid_clinic_constraints.json")))).scenario;
const ctx = B.ctxFor("shymkent");
const cl = () => JSON.parse(JSON.stringify(sc0));
let pass = 0, fail = 0;
const typed = (name, minimal, fn, codes) => {
  let r, code = null;
  try { r = fn(); } catch (e) { code = e && e.code ? e.code : "UNTYPED " + e.message; }
  const ok = code !== null && !code.startsWith("UNTYPED") && (!codes || codes.includes(code));
  ok ? pass++ : fail++;
  console.log(ok ? "PASS" : "FAIL", name, ok ? `(${code})` : `— accepted/untyped: ${code || JSON.stringify(r && (r.status || (r.metrics && r.metrics.weighted_sum_mm) || "computed"))}; minimal: ${minimal}`);
};
const c17 = cl(); c17.required_ids = []; c17.excluded_ids = []; c17.selected_ids = [];
c17.candidates = Array.from({ length: 17 }, (_, k) => Object.assign({}, sc0.candidates[0], { id: "k" + k }));
typed("createSearch: 17 candidates", "valid scenario with candidates k0..k16 passed to CITY_PLAN.createSearch", () => B.PL.createSearch(ctx, c17, { F: B.F }), ["too_many_candidates"]);
typed("optimizePlans: 17 candidates", "same scenario passed to CITY_PLAN.optimizePlans (runs 2^17 subsets if unguarded)", () => B.PL.optimizePlans(ctx, c17, { F: B.F }), ["too_many_candidates"]);
const nan = cl(); nan.control_points[0].weight = NaN;
typed("evaluatePlan: NaN weight", "control_points[0].weight = NaN", () => B.PL.evaluatePlan(ctx, nan, []), ["bad_weight"]);
const ob = cl(); ob.candidates[0].lon = 0;
typed("evaluatePlan: candidate outside bbox", "candidates[0].lon = 0", () => B.PL.evaluatePlan(ctx, ob, [ob.candidates[0].id]), ["outside_bbox"]);
typed("optimizePlans: Shymkent scenario with Astana context", "optimizePlans(makeContext(astana), shymkentScenario)", () => B.PL.optimizePlans(B.ctxFor("astana"), cl(), { F: B.F }), ["other_city", "foreign_snapshot"]);
const mut = cl(); const v = B.PL.validatePlanScenario(mut, ctx); v.budget = 5e6;
typed("evaluatePlan: validated object mutated afterwards (budget 5e6)", "validated scenario, then sc.budget = 5000000", () => B.PL.evaluatePlan(ctx, v, []), ["bad_budget"]);
typed("evaluatePlan: unknown selected id", "selectedIds = ['nope']", () => B.PL.evaluatePlan(ctx, cl(), ["nope"]), ["unknown_ref"]);
console.log(`\n${pass} passed, ${fail} failed, 0 skipped`);
process.exitCode = fail ? 1 : 0;
