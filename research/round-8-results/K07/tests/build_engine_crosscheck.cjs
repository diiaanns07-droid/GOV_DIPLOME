// K07 round 8: independent check of the BUILD engine web/plan.js (city-plan-v2) against the K07 Python oracle.
// Usage: node build_engine_crosscheck.cjs --app-root <BUILD extraction with web/plan.js> [--out <dir>]
// The BUILD module is only loaded and called (read first: pure functions, no I/O). Adapter: BUILD names objectives
// {ids, cost, unknown_count, weighted_sum_mm, max_mm, covered_weight} and Pareto {ids, cost, weighted_sum_mm}.
// Cases (tests/plan_cases.cjs): 34 real-slice scenarios (SYNTHETIC points/sites/costs, real bbox/snapshot) and 11 hand cases
// on a SYNTHETIC equator test city; validator refusals of tests/plan_cases.cjs REJ. python3 needed for the oracle part.
const fs = require("fs"), path = require("path"), vm = require("vm"), { spawnSync } = require("child_process");
const HERE = __dirname, K = path.join(HERE, "..");
const argv = process.argv.slice(2), arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const ROOT = path.resolve(arg("--app-root", "")), W = fs.existsSync(path.join(ROOT, "web")) ? path.join(ROOT, "web") : ROOT;
const OUT = path.resolve(arg("--out", path.join(K, "results", "build_engine")));
fs.mkdirSync(OUT, { recursive: true });
const checks = [];
function check(id, name, ok, observed, pre) { checks.push({ id, name, verdict: pre === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL", observed: ok ? undefined : observed }); }
const finish = () => {
  const by = (v) => checks.filter((c) => c.verdict === v).length;
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify({ kind: "K07 r8 cross-check of BUILD web/plan.js vs K07 oracle", app_root: path.basename(ROOT),
    total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"), checks }, null, 1) + "\n");
  for (const c of checks) if (c.verdict !== "PASS") console.log(`${c.verdict} ${c.id} ${c.name} -> ${JSON.stringify(c.observed).slice(0, 300)}`);
  console.log(`PASS ${by("PASS")} · FAIL ${by("FAIL")} · TEST_INCOMPATIBLE ${by("TEST_INCOMPATIBLE")} of ${checks.length}`);
  process.exitCode = by("FAIL") || by("TEST_INCOMPATIBLE") ? 1 : 0;
};
if (!fs.existsSync(path.join(W, "plan.js"))) { check("X00", "BUILD web/plan.js present", false, W, false); finish(); return; }
const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js"));
const C = require(path.join(K, "web", "plan_calc.js")), DEMO = require(path.join(K, "web", "plan_demo.js"));
const { EQ_DATA, eqCases, realScenarios, REJ, eqScenario } = require(path.join(HERE, "plan_cases.cjs"));
const box = {}; vm.createContext(box); box.window = box;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), box, { filename: "data.js" });
const D = box.CITY_EVIDENCE;

// snapshot: both modules derive it from the same inputs (CORE_SPEC); equal strings = the K07 fixtures are valid for BUILD
for (const city of ["shymkent", "astana"]) check("X01-" + city, `source_snapshot of BUILD = K07 for ${city}`, PL.makeContext(D, city, F).source_snapshot === C.makeContext(D, city, F).source_snapshot, null);
const bctx = { synthetic_eq: PL.makeContext(EQ_DATA, "synthetic_eq", F) };
const bCtx = (city) => bctx[city] || (bctx[city] = PL.makeContext(city === "synthetic_eq" ? EQ_DATA : D, city, F));
// validator refusals (codes differ between modules: only "refused" is compared)
for (const [name, mut] of REJ) {
  const o = eqScenario(bCtx("synthetic_eq").source_snapshot); mut(o);
  let refused = false, code = null; try { PL.validatePlanScenario(o, bCtx("synthetic_eq")); } catch (e) { refused = true; code = e.code; }
  check("XV-" + name, `BUILD validator refuses: ${name}`, refused, { code });
}
{ const o = eqScenario(bCtx("synthetic_eq").source_snapshot); o.derived_results = { weighted_sum_mm: -1 };
  let ok = false; try { PL.validatePlanScenario(o, bCtx("synthetic_eq")); ok = true; } catch (e) { ok = false; }
  check("XV-derived", "BUILD validator does not reject the allowed derived_results field (it is checked on import)", ok, null); }

function runCases(cases, dataFile, tag) {
  const casesFile = path.join(OUT, `cases${tag}.json`), oracleFile = path.join(OUT, `oracle${tag}.json`);
  fs.writeFileSync(casesFile, JSON.stringify(cases, null, 1) + "\n");
  const py = spawnSync("python3", [path.join(HERE, "oracle_plan.py"), "--data", dataFile, "--cases", casesFile, "--out", oracleFile], { encoding: "utf8" });
  if (py.status !== 0) { check("XO00" + tag, "Python oracle ran", false, (py.stderr || String(py.error)).slice(0, 300), false); return; }
  const orc = JSON.parse(fs.readFileSync(oracleFile, "utf8"));
  const pickB = (o) => o && { selected_ids: o.ids, unknown_count: o.unknown_count, weighted_sum_mm: o.weighted_sum_mm, max_mm: o.max_mm, covered_weight: o.covered_weight, cost: o.cost };
  const pickO = (o) => o && { selected_ids: o.selected_ids, unknown_count: o.unknown_count, weighted_sum_mm: o.weighted_sum_mm, max_mm: o.max_mm, covered_weight: o.covered_weight, cost: o.cost };
  cases.forEach((c, i) => {
    const o = orc[i], ctx = bCtx(c.scenario.city_id);
    let sc, r, sens, ev;
    try { sc = PL.validatePlanScenario(c.scenario, ctx); r = PL.optimizePlans(ctx, sc, { F }); sens = PL.sensitivity(ctx, sc, { F }); ev = PL.evaluatePlan(ctx, sc, sc.selected_ids); }
    catch (e) { check("XO-" + c.name, `BUILD optimizePlans runs: ${c.name}`, false, String(e.code || e.message)); return; }
    const objB = r.objectives ? Object.fromEntries(["mean", "minimax", "coverage"].map((k) => [k, pickB(r.objectives[k])])) : { mean: null, minimax: null, coverage: null };
    const objO = Object.fromEntries(["mean", "minimax", "coverage"].map((k) => [k, pickO(o.objectives[k])]));
    check("XO-" + c.name, `BUILD optimum = oracle (status, feasible count, three winners with metrics): ${c.name}`,
      r.status === o.status && (r.status === "infeasible" || r.feasible_count === o.feasible_count) && JSON.stringify(objB) === JSON.stringify(objO),
      { build: { status: r.status, feasible: r.feasible_count, obj: objB }, oracle: { status: o.status, feasible: o.feasible_count, obj: objO } });
    const parB = (r.pareto || []).map((q) => ({ selected_ids: q.ids, cost: q.cost, weighted_sum_mm: q.weighted_sum_mm }));
    check("XP-" + c.name, `BUILD Pareto front = oracle: ${c.name}`, JSON.stringify(parB) === JSON.stringify(o.pareto), { build: parB, oracle: o.pareto });
    const sB = sens.map((t) => ({ budget: t.budget, feasible_count: t.status === "infeasible" ? 0 : t.feasible_count, objectives: t.objectives ? Object.fromEntries(["mean", "minimax", "coverage"].map((k) => [k, pickB(t.objectives[k])])) : { mean: null, minimax: null, coverage: null } }));
    const sO = o.sensitivity.map((t) => ({ budget: t.budget, feasible_count: t.feasible_count, objectives: Object.fromEntries(["mean", "minimax", "coverage"].map((k) => [k, pickO(t.objectives[k])])) }));
    check("XS-" + c.name, `BUILD budgets [0, B/2, B] = oracle: ${c.name}`, JSON.stringify(sB) === JSON.stringify(sO), { build: sB, oracle: sO });
    const m = o.manual;
    check("XE-" + c.name, `BUILD evaluatePlan (manual plan) = oracle: ${c.name}`, JSON.stringify(ev.rows.map((x) => x.before_mm)) === JSON.stringify(m.before_mm) &&
      ev.metrics.weighted_sum_mm === m.weighted_sum_mm && ev.metrics.max_mm === m.max_mm && ev.metrics.covered_weight === m.covered_weight && ev.metrics.unknown_count === m.unknown_count && ev.metrics.cost === m.cost,
      { build: ev.metrics, oracle: m });
  });
}
runCases(realScenarios(C, D, F, DEMO), path.join(W, "data.js"), "");
const eqFile = path.join(OUT, "synthetic_eq_data.js");
fs.writeFileSync(eqFile, "// SYNTHETIC equator test city (K07 r8 tests), not city data\nwindow.CITY_EVIDENCE = " + JSON.stringify(EQ_DATA) + ";\n");
runCases(eqCases(bCtx("synthetic_eq").source_snapshot), eqFile, "_eq");
finish();
