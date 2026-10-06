// Public API boundary of web/plan.js (CORE_SPEC r9): evaluatePlan / createSearch / optimizePlans / sensitivity validate an
// unvalidated object before any precomputation, and a running search uses its own clean copy. Headless, no DOM.
// Regression test for K12 r8 F1 and K12 r9 api_guard findings (repro on d865dd4). Usage: node tests/plan_api_guard.cjs
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = path.join(__dirname, "..", "web");
const ctx0 = {}; vm.createContext(ctx0); ctx0.window = ctx0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx0, { filename: f });
const F = require(path.join(W, "facts.js"));
const PL = require(path.join(W, "plan.js"));
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(detail).slice(0, 300) : "")); };
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || `untyped ${e.name}`; } };
const ctx = PL.makeContext(ctx0.CITY_EVIDENCE, "shymkent", F), bb = ctx.bbox;
const plan = (nc) => ({ schema_version: PL.SCHEMA, city_id: "shymkent", source_snapshot: ctx.source_snapshot, category: "school",
  control_points: Array.from({ length: 6 }, (_, k) => ({ id: `p${k}`, lon: +(bb[0] + 0.001 + k * 0.003).toFixed(6), lat: +(bb[1] + 0.002 + k * 0.002).toFixed(6), weight: 1 + (k % 5) })),
  candidates: Array.from({ length: nc }, (_, k) => ({ id: `c${k}`, lon: +(bb[0] + 0.001 + (k % 7) * 0.0025).toFixed(6), lat: +(bb[1] + 0.006 + Math.floor(k / 7) * 0.003).toFixed(6),
    category: "school", kind: "hypothetical", cost: 1000 + 37 * k })),
  budget: 1000000, max_selected: 5, coverage_radius_m: 500, required_ids: [], excluded_ids: [], selected_ids: [] });
const fast = (fn) => { const t = Date.now(); const c = code(fn); return { c, ms: Date.now() - t }; };

for (const [name, fn] of [["createSearch", () => PL.createSearch(ctx, plan(17), { F })], ["optimizePlans", () => PL.optimizePlans(ctx, plan(17), { F })],
  ["sensitivity", () => PL.sensitivity(ctx, plan(17), { F })], ["evaluatePlan", () => PL.evaluatePlan(ctx, plan(17), ["c0"])]]) {
  const r = fast(fn);
  check(`${name}: 17 candidates refused before enumeration (too_many_candidates, < 200 ms)`, r.c === "too_many_candidates" && r.ms < 200, J(r));
}
function J(x) { return JSON.stringify(x); }
const v = PL.validatePlanScenario(plan(3), ctx);
v.candidates.push(...plan(17).candidates.slice(3));
check("validated object grown to 17 candidates afterwards: optimizePlans refuses", code(() => PL.optimizePlans(ctx, v, { F })) === "too_many_candidates");
const mut = (f) => { const p = plan(3); f(p); return p; };
const cases = [
  ["weight \"5\" (string)", "bad_weight", () => PL.evaluatePlan(ctx, mut((p) => { p.control_points[0].weight = "5"; }), ["c1"])],
  ["cost \"100\" (string)", "bad_cost", () => PL.optimizePlans(ctx, mut((p) => { p.candidates[0].cost = "100"; }), { F })],
  ["lon NaN", "bad_coord", () => PL.evaluatePlan(ctx, mut((p) => { p.control_points[0].lon = NaN; }), ["c1"])],
  ["weight −50", "bad_weight", () => PL.optimizePlans(ctx, mut((p) => { p.control_points[0].weight = -50; }), { F })],
  ["duplicate candidate ID", "duplicate_id", () => PL.optimizePlans(ctx, mut((p) => { p.candidates.push({ ...p.candidates[0] }); }), { F })],
  ["max_selected 99", "bad_max_selected", () => PL.optimizePlans(ctx, mut((p) => { p.max_selected = 99; }), { F })],
  ["city astana in a Shymkent context", "other_city", () => PL.evaluatePlan(ctx, mut((p) => { p.city_id = "astana"; }), ["c1"])],
  ["unknown required ID (typed, not TypeError)", "unknown_ref", () => PL.optimizePlans(ctx, mut((p) => { p.required_ids = ["nope"]; }), { F })],
  ["selectedIds not an array", "bad_shape", () => PL.evaluatePlan(ctx, plan(3), "c1")],
];
for (const [name, want, fn] of cases) { const c = code(fn); check(`direct API, ${name}: ${want}`, c === want, c); }

// a running search keeps its own copy: changing the passed object between steps changes nothing
const p = plan(10); p.budget = 5000;
const ref = PL.optimizePlans(ctx, JSON.parse(J(p)), { F });
const s = PL.createSearch(ctx, p, { F }); s.step(64); p.budget = 0; p.max_selected = 0; p.control_points[0].weight = 100;
while (!s.step(4096));
const got = s.result();
check("object changed between search steps: result equals the unchanged problem", J([got.objectives, got.feasible_count]) === J([ref.objectives, ref.feasible_count]),
  J([ref.feasible_count, got.feasible_count]));
// valid input through the direct API still works and equals the validated path
const p16 = plan(16), r16 = PL.optimizePlans(ctx, p16, { F });
check("valid 16 candidates via direct API: optimal, 65536 subsets, same as validated input",
  r16.status === "optimal" && r16.evaluated === 65536 && J(r16.objectives) === J(PL.optimizePlans(ctx, PL.validatePlanScenario(p16, ctx), { F }).objectives));
check("evaluatePlan accepts an editor state without points (requirePoints: false)", code(() => PL.evaluatePlan(ctx, { ...plan(2), control_points: [] }, [])) === "accepted");

console.log(fails ? `${fails} FAILED` : "all plan API guard checks passed");
process.exit(fails ? 1 : 0);
