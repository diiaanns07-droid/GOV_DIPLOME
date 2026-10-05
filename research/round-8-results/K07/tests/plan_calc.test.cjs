// K07 round 8: headless tests of web/plan_calc.js + web/plan_runner.js (no DOM, no browser).
// Usage: node plan_calc.test.cjs --app-root <dir with web/data.js and web/facts.js of BUILD> [--out <dir>]
// 1) hand cases on a SYNTHETIC equator test city (not city data): ties, infeasible, zero budget, no candidates,
//    no baseline, dominated plans, coverage, order independence, digests, partial/cancelled search, validation refusals;
// 2) real slices (both cities, both categories) with the SYNTHETIC demo set and parameter variations, compared with the
//    independent Python oracle tests/oracle_plan.py (python3 needed; without it those checks are TEST_INCOMPATIBLE).
const fs = require("fs"), path = require("path"), vm = require("vm"), { spawnSync } = require("child_process");
const HERE = __dirname, K = path.join(HERE, "..");
const C = require(path.join(K, "web", "plan_calc.js")), RUN = require(path.join(K, "web", "plan_runner.js")), DEMO = require(path.join(K, "web", "plan_demo.js"));
const argv = process.argv.slice(2), arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const ROOT = path.resolve(arg("--app-root", "")), W = fs.existsSync(path.join(ROOT, "web")) ? path.join(ROOT, "web") : ROOT;
const OUT = path.resolve(arg("--out", path.join(K, "results", "calc")));
fs.mkdirSync(OUT, { recursive: true });
const F = require(path.join(W, "facts.js"));
const box = {}; vm.createContext(box); box.window = box;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), box, { filename: "data.js" });
const D = box.CITY_EVIDENCE;
const checks = [];
function check(id, name, ok, observed, pre) { const v = pre === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL"; checks.push({ id, name, verdict: v, observed: ok ? undefined : observed }); }
const clone = (x) => JSON.parse(JSON.stringify(x));

// ---------- SYNTHETIC equator test city: 0.001° of longitude at lat 0 ≈ 111.195 m ----------
const EQ = require(path.join(HERE, "plan_cases.cjs")).EQ_DATA;  // SYNTHETIC equator test city (shared with the oracle run)
const ctxEq = C.makeContext(EQ, "synthetic_eq", F);
function eqScenario(over = {}) {
  return { schema_version: C.SCHEMA, city_id: "synthetic_eq", source_snapshot: ctxEq.source_snapshot, category: "school",
    control_points: [{ id: "p1", lon: 0.005, lat: 0, weight: 1 }, { id: "p2", lon: 0.01, lat: 0, weight: 1 }, { id: "p3", lon: 0.015, lat: 0, weight: 1 }],
    candidates: [{ id: "c1", lon: 0.005, lat: 0, category: "school", kind: "hypothetical", cost: 10 },
      { id: "c2", lon: 0.01, lat: 0, category: "school", kind: "hypothetical", cost: 10 },
      { id: "c3", lon: 0.015, lat: 0, category: "school", kind: "hypothetical", cost: 10 }],
    budget: 20, max_selected: 2, coverage_radius_m: 100, required_ids: [], excluded_ids: [], selected_ids: [], ...over };
}
const V = (sc, ctx = ctxEq) => { const r = C.validatePlanScenario(sc, ctx); if (!r.ok) throw new Error(JSON.stringify(r.error)); return r.scenario; };
const ids = (p) => p && p.selected_ids.join(",");
const mm1 = C.toMm(C.haversine(0, 0, 0.001, 0));

check("C01", "haversine: 1° of latitude = R·π/180 (111 195.08 m), mm rounding once", Math.abs(C.haversine(0, 0, 0, 1) - 6371008.8 * Math.PI / 180) < 1e-6 && mm1 === 111195, { mm1 });
{
  const r = C.optimizePlans(ctxEq, V(eqScenario()));
  // p1,p3 are 5 mm-units from sources; c2 serves p2 exactly; {c1,c3}: p2 stays 556 m. Best mean: two sites.
  check("C02", "mean objective on the equator case is {c1,c2}: ties of equal cost/sum broken by sorted IDs", r.status === "optimal" && ids(r.objectives.mean) === "c1,c2", r.objectives);
  check("C03", "all subsets enumerated (2^3=8), feasible = subsets with ≤2 sites and cost ≤ 20 (7)", r.evaluated === 8 && r.total_subsets === 8 && r.feasible_count === 7, { evaluated: r.evaluated, feasible: r.feasible_count });
  check("C04", "three objectives may coincide: no artificial difference", !!r.objectives.minimax && !!r.objectives.coverage, r.objectives);
}
{
  const r = C.optimizePlans(ctxEq, V(eqScenario({ required_ids: ["c1", "c2"], budget: 15 })));
  check("C05", "required sites cost more than the budget → infeasible with reason, constraints not dropped", r.status === "infeasible" && r.feasible_count === 0 && r.objectives.mean === null && r.infeasible_reasons.some((x) => x.code === "required_over_budget"), r);
  const r2 = C.optimizePlans(ctxEq, V(eqScenario({ required_ids: ["c1", "c2", "c3"], budget: 100, max_selected: 2 })));
  check("C06", "more required sites than max_selected → infeasible (required_over_count)", r2.status === "infeasible" && r2.infeasible_reasons.some((x) => x.code === "required_over_count"), r2.infeasible_reasons);
}
{
  const r = C.optimizePlans(ctxEq, V(eqScenario({ budget: 0 })));
  check("C07", "zero budget: only the empty plan is feasible; all three winners are the empty plan", r.status === "optimal" && r.feasible_count === 1 && ids(r.objectives.mean) === "" && ids(r.objectives.coverage) === "", r.objectives);
  const r2 = C.optimizePlans(ctxEq, V(eqScenario({ candidates: [], selected_ids: [] })));
  check("C08", "no candidates: one subset (the empty plan), status optimal", r2.status === "optimal" && r2.total_subsets === 1 && r2.feasible_count === 1, r2);
}
{
  const sc = V(eqScenario({ category: "outpatient_clinic", candidates: eqScenario().candidates.map((c) => ({ ...c, category: "outpatient_clinic" })) }));
  const e = C.evaluatePlan(ctxEq, sc, []);
  check("C09", "no baseline records of the category: before = null, after = null for the empty plan (not 0)", e.baseline_records === 0 && e.rows.every((r) => r.before_mm === null && r.after_mm === null) && e.metrics.unknown_count === 3 && e.metrics.weighted_mean_mm === null && e.metrics.max_mm === null, e.metrics);
  const e2 = C.evaluatePlan(ctxEq, sc, ["c2"]);
  check("C10", "no baseline: after known from a site, delta stays null", e2.rows.every((r) => r.before_mm === null && r.after_mm !== null && r.delta_mm === null) && e2.metrics.unknown_count === 0, e2.rows);
  const r = C.optimizePlans(ctxEq, sc);
  check("C11", "no baseline: winners minimise unknown_count first (never a partial sum before it)", r.objectives.mean.metrics.unknown_count === 0 && r.objectives.minimax.metrics.unknown_count === 0, r.objectives);
}
{
  // dominated plans: c4 is expensive and serves no one better than c2
  const sc = V(eqScenario({ candidates: eqScenario().candidates.concat({ id: "c4", lon: 0.0101, lat: 0, category: "school", kind: "hypothetical", cost: 15 }), budget: 30, max_selected: 3 }));
  const r = C.optimizePlans(ctxEq, sc);
  const front = r.pareto.map((q) => `${q.cost}:${q.selected_ids.join("+")}`);
  const nonDom = r.pareto.every((q, i) => r.pareto.every((o, j) => i === j || !(o.cost <= q.cost && o.weighted_sum_mm <= q.weighted_sum_mm)));
  check("C12", "Pareto (cost, weighted_sum_mm): no point dominated, equal pairs collapsed, sorted by cost, plans with c4 absent", nonDom && !front.some((f) => f.includes("c4")) && r.pareto[0].cost === 0, front);
}
{
  // coverage: radius 100 m covers only an exact hit; one site covers weight 5 (p2) vs the mean winner
  const sc = V(eqScenario({ control_points: [{ id: "p1", lon: 0.005, lat: 0, weight: 1 }, { id: "p2", lon: 0.0102, lat: 0, weight: 5 }, { id: "p3", lon: 0.015, lat: 0, weight: 1 }], max_selected: 1, budget: 10 }));
  const r = C.optimizePlans(ctxEq, sc);
  check("C13", "coverage objective maximises covered weight first", r.objectives.coverage.metrics.covered_weight === 5 && ids(r.objectives.coverage) === "c2", r.objectives.coverage);
}
{
  const a = V(eqScenario()), b = clone(a);
  b.candidates.reverse(); b.control_points.reverse();
  const ra = C.optimizePlans(ctxEq, a), rb = C.optimizePlans(ctxEq, V(b));
  check("C14", "input order of points/candidates changes neither the plans nor problem_digest", JSON.stringify(ra.objectives) === JSON.stringify(rb.objectives) && ra.problem_digest === rb.problem_digest, { a: ra.problem_digest, b: rb.problem_digest });
  const s1 = V(eqScenario({ selected_ids: ["c1"] })), s2 = V(eqScenario({ selected_ids: ["c2"] }));
  check("C15", "selected_ids: same problem_digest, different scenario digest", C.problemDigest(ctxEq, s1) === C.problemDigest(ctxEq, s2) && C.scenarioDigest(ctxEq, s1) !== C.scenarioDigest(ctxEq, s2), null);
  const s3 = V(eqScenario({ budget: 21 }));
  check("C16", "budget (or any problem field) changes problem_digest", C.problemDigest(ctxEq, s3) !== C.problemDigest(ctxEq, a), null);
}
{
  const s = C.createSearch(ctxEq, V(eqScenario())); s.step(3);
  const part = s.result(), canc = s.result("cancelled");
  check("C17", "unfinished search is never 'optimal' and carries no winners", part.status === "partial" && part.objectives === null && canc.status === "cancelled" && part.evaluated === 3, { part: part.status, canc: canc.status });
  const e = C.evaluatePlan(ctxEq, V(eqScenario({ selected_ids: ["c1", "c2", "c3"] })));
  check("C18", "manual plan over count and budget is evaluated and marked infeasible with both reasons", !e.feasibility.feasible && e.feasibility.reasons.map((x) => x.code).join(",") === "over_budget,too_many", e.feasibility);
  const ex = C.evaluatePlan(ctxEq, V(eqScenario({ excluded_ids: ["c2"], required_ids: ["c3"], selected_ids: ["c2"] })));
  check("C19", "manual plan with an excluded site and without a required one → has_excluded, missing_required", ex.feasibility.reasons.map((x) => x.code).sort().join(",") === "has_excluded,missing_required", ex.feasibility);
  const t = C.evaluatePlan(ctxEq, V(eqScenario({ candidates: [{ id: "c0", lon: 0, lat: 0, category: "school", kind: "hypothetical", cost: 1 }], selected_ids: ["c0"], control_points: [{ id: "p1", lon: 0, lat: 0, weight: 1 }] })));
  check("C20", "tie between a source record and a site at the same place: nearest after stays the source (no fake improvement)", t.rows[0].nearest_after.kind === "source" && t.rows[0].delta_mm === 0, t.rows[0]);
}
{
  // equal (cost, weighted_sum_mm) pairs: {c1} and {c3} are mirror images → one representative, the smaller sorted IDs
  const sc = V(eqScenario({ candidates: [eqScenario().candidates[0], eqScenario().candidates[2]], max_selected: 1, budget: 10 }));
  const r = C.optimizePlans(ctxEq, sc);
  const one = r.pareto.filter((q) => q.cost === 10);
  check("C21", "Pareto: two plans with equal cost and sum collapse to one point with the smaller IDs ({c1}, not {c3})", one.length === 1 && one[0].selected_ids.join() === "c1" && ids(r.objectives.mean) === "c1", r.pareto);
}
// validation refusals
const { REJ, eqCases, realScenarios, EQ_DATA } = require(path.join(HERE, "plan_cases.cjs"));
for (const [name, mut, code] of REJ) {
  const o = eqScenario(); mut(o);
  const r = C.validatePlanScenario(o, ctxEq);
  check("V-" + name, `validator rejects: ${name} → ${code}`, !r.ok && r.error.code === code, r.ok ? "accepted" : r.error);
}
{
  const o = eqScenario(); o.derived_results = { objectives: { mean: { selected_ids: ["c3"] } }, weighted_sum_mm: -1 };
  const r = C.validatePlanScenario(o, ctxEq);
  check("V-derived", "derived_results is allowed but dropped (never trusted)", r.ok && !("derived_results" in r.scenario), r);
  check("V-empty-ui", "editor state with 0 points is accepted only with allowEmptyPoints", C.validatePlanScenario({ ...eqScenario(), control_points: [] }, ctxEq, { allowEmptyPoints: true }).ok, null);
}

// ---------- runner: progress, cancel, stale ----------
async function runnerChecks() {
  const sc = V(eqScenario({ candidates: Array.from({ length: 12 }, (_, i) => ({ id: "k" + String(i).padStart(2, "0"), lon: 0.001 * (i + 1), lat: 0, category: "school", kind: "hypothetical", cost: 5 })), budget: 25, max_selected: 5 }));
  const prog = [];
  const r = await new Promise((res) => RUN.start(C, ctxEq, sc, { chunk: 512, onProgress: (p) => prog.push(p.evaluated), onDone: res }));
  const sync = C.optimizePlans(ctxEq, sc);
  check("R01", "chunked run: progress grows in steps to 4096 and the result equals the one-call search", prog.length === 8 && prog[7] === 4096 && r.status === "optimal" && JSON.stringify(r.objectives) === JSON.stringify(sync.objectives) && /^req-/.test(r.request_id), { prog });
  const c = await new Promise((res) => { const h = RUN.start(C, ctxEq, sc, { chunk: 256, delayMs: 5, onDone: res }); setTimeout(() => h.cancel(), 12); });
  check("R02", "cancel stops the search: status cancelled, no winners, fewer subsets than total", c.status === "cancelled" && c.objectives === null && c.evaluated < c.total_subsets, { status: c.status, evaluated: c.evaluated });
  const h1 = RUN.start(C, ctxEq, sc, { onDone: () => {} }), h2 = RUN.start(C, ctxEq, V({ ...sc, budget: 26 }), { onDone: () => {} });
  check("R03", "each run has its own request_id; a changed problem has another problem_digest", h1.request_id !== h2.request_id && h1.problem_digest !== h2.problem_digest, null);
  h1.cancel(); h2.cancel();
}

// ---------- real slices (and the equator hand cases) vs the Python oracle ----------
function realCases() {
  const ctxs = {};
  return realScenarios(C, D, F, DEMO).map((c) => { const ctx = ctxs[c.scenario.city_id] || (ctxs[c.scenario.city_id] = C.makeContext(D, c.scenario.city_id, F)); return { ...c, scenario: V(c.scenario, ctx), ctx }; });
}
function eqCasesV() { return eqCases(ctxEq.source_snapshot).map((c) => ({ ...c, scenario: V(c.scenario), ctx: ctxEq })); }
function compareWithOracle(cases, dataFile, tag) {
  const casesFile = path.join(OUT, `cases${tag}.json`), oracleFile = path.join(OUT, `oracle${tag}.json`);
  fs.writeFileSync(casesFile, JSON.stringify(cases.map((c) => ({ name: c.name, scenario: c.scenario })), null, 1) + "\n");
  const py = spawnSync("python3", [path.join(HERE, "oracle_plan.py"), "--data", dataFile, "--cases", casesFile, "--out", oracleFile], { encoding: "utf8" });
  if (py.status !== 0) { check("O00", "Python oracle ran", false, (py.stderr || String(py.error)).slice(0, 300), false); return; }
  const orc = JSON.parse(fs.readFileSync(oracleFile, "utf8"));
  const pick = (p) => p && { selected_ids: p.selected_ids, unknown_count: p.metrics.unknown_count, weighted_sum_mm: p.metrics.weighted_sum_mm, max_mm: p.metrics.max_mm, covered_weight: p.metrics.covered_weight, cost: p.metrics.cost };
  const timing = [];
  cases.forEach((c, i) => {
    const t0 = process.hrtime.bigint(), r = C.optimizePlans(c.ctx, c.scenario), ms = Number(process.hrtime.bigint() - t0) / 1e6, o = orc[i];
    timing.push({ name: c.name, ms: Math.round(ms * 10) / 10, subsets: r.total_subsets, feasible: r.feasible_count });
    const js = { status: r.status, feasible_count: r.feasible_count, objectives: r.objectives ? Object.fromEntries(Object.entries(r.objectives).map(([k, v]) => [k, pick(v)])) : { mean: null, minimax: null, coverage: null },
      pareto: (r.pareto || []).map((q) => ({ selected_ids: q.selected_ids, cost: q.cost, weighted_sum_mm: q.weighted_sum_mm })), pareto_excluded_unknown: r.pareto_excluded_unknown,
      sensitivity: (r.sensitivity || []).map((t) => ({ budget: t.budget, feasible_count: t.feasible_count, objectives: Object.fromEntries(Object.entries(t.objectives).map(([k, v]) => [k, pick(v)])) })) };
    const ref = { status: o.status, feasible_count: o.feasible_count, objectives: o.objectives, pareto: o.pareto, pareto_excluded_unknown: o.pareto_excluded_unknown, sensitivity: o.sensitivity };
    const a = JSON.stringify(js), b = JSON.stringify(ref);
    check("O-" + c.name, `optimizePlans = Python oracle (objectives, feasible count, Pareto, budgets [0, B/2, B]): ${c.name}`, a === b, { js: a.slice(0, 400), oracle: b.slice(0, 400) });
    const e = C.evaluatePlan(c.ctx, c.scenario), m = o.manual;
    check("E-" + c.name, `evaluatePlan (manual plan) = oracle: ${c.name}`, JSON.stringify(e.rows.map((x) => x.before_mm)) === JSON.stringify(m.before_mm) &&
      e.metrics.weighted_sum_mm === m.weighted_sum_mm && e.metrics.max_mm === m.max_mm && e.metrics.covered_weight === m.covered_weight && e.metrics.unknown_count === m.unknown_count && e.metrics.cost === m.cost,
      { js: e.metrics, oracle: m });
  });
  if (!tag) fs.writeFileSync(path.join(OUT, "timing.json"), JSON.stringify({ node: process.version, platform: `${process.platform} ${process.arch}`, cases: timing }, null, 1) + "\n");
}

(async () => {
  await runnerChecks();
  compareWithOracle(realCases(), path.join(W, "data.js"), "");
  const eqFile = path.join(OUT, "synthetic_eq_data.js");  // SYNTHETIC test city for the oracle (same text format as data.js)
  fs.writeFileSync(eqFile, "// SYNTHETIC equator test city (K07 r8 tests), not city data\nwindow.CITY_EVIDENCE = " + JSON.stringify(EQ_DATA) + ";\n");
  compareWithOracle(eqCasesV(), eqFile, "_eq");
  const by = (v) => checks.filter((c) => c.verdict === v).length;
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify({ kind: "K07 r8 headless calculator tests", app_root: path.basename(ROOT), calc_version: C.CALC_VERSION,
    total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"), checks }, null, 1) + "\n");
  for (const c of checks) if (c.verdict !== "PASS") console.log(`${c.verdict} ${c.id} ${c.name} -> ${JSON.stringify(c.observed).slice(0, 300)}`);
  console.log(`PASS ${by("PASS")} · FAIL ${by("FAIL")} · TEST_INCOMPATIBLE ${by("TEST_INCOMPATIBLE")} of ${checks.length}`);
  process.exitCode = by("FAIL") || by("TEST_INCOMPATIBLE") ? 1 : 0;
})();
