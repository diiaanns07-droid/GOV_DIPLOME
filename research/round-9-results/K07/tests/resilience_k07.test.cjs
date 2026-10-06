// K07 round 9: headless tests of web/resilience_k07.js on top of the REAL BUILD plan.js (no DOM).
// Usage: node resilience_k07.test.cjs --app-root <BUILD extraction with web/plan.js> [--out <dir>]
// 1) hand cases on the SYNTHETIC equator test city (values worked out by hand in the comments);
// 2) envelope refusals (CORE_SPEC r9); order independence; mutation after validation; partial/cancel;
// 3) both real slices with the K07 r8 SYNTHETIC fixtures + cases built from real source IDs, compared with the independent
//    Python oracle tests/oracle_resilience.py and with BUILD's own v2 mean optimum (nominal plan). python3 needed for 3).
const fs = require("fs"), path = require("path"), vm = require("vm"), { spawnSync } = require("child_process");
const HERE = __dirname, K = path.join(HERE, ".."), R8 = path.join(K, "..", "..", "round-8-results", "K07");
const argv = process.argv.slice(2), arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const ROOT = path.resolve(arg("--app-root", "")), W = fs.existsSync(path.join(ROOT, "web")) ? path.join(ROOT, "web") : ROOT;
const OUT = path.resolve(arg("--out", path.join(K, "results", "resilience_calc")));
fs.mkdirSync(OUT, { recursive: true });
const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js"));
const RS = require(path.join(K, "web", "resilience_k07.js"))(PL);
const { EQ_DATA } = require(path.join(R8, "tests", "plan_cases.cjs"));
const box = {}; vm.createContext(box); box.window = box;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), box);
const D = box.CITY_EVIDENCE;
const checks = [];
function check(id, name, ok, observed, pre) { checks.push({ id, name, verdict: pre === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL", observed: ok ? undefined : observed }); }
const clone = (x) => JSON.parse(JSON.stringify(x));
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || e.message; } };

// ---------- SYNTHETIC equator city: sources s-a (lon 0) and s-b (lon 0.02); 0.005° ≈ 555 975 mm ----------
const ctxEq = PL.makeContext(EQ_DATA, "synthetic_eq", F);
const eqPlan = (over = {}) => ({ schema_version: "city-plan-v2", city_id: "synthetic_eq", source_snapshot: ctxEq.source_snapshot, category: "school",
  control_points: [{ id: "p1", lon: 0.005, lat: 0, weight: 1 }, { id: "p2", lon: 0.01, lat: 0, weight: 1 }, { id: "p3", lon: 0.015, lat: 0, weight: 1 }],
  candidates: ["c1", "c2", "c3"].map((id, i) => ({ id, lon: 0.005 * (i + 1), lat: 0, category: "school", kind: "hypothetical", cost: 10 })),
  budget: 10, max_selected: 1, coverage_radius_m: 100, required_ids: [], excluded_ids: [], selected_ids: [], ...over });
const env = (plan, cases) => ({ schema_version: "city-resilience-v1", plan, cases });
{
  // one site; case Y drops s-b. Base: {c1},{c2},{c3} all sum 1 111 950, max 555 975 → nominal = {c1} (IDs).
  // Y: {c1} → p3 = 1 111 951 (sum 1 667 926); {c2},{c3} → sum 1 111 950, max 555 975 → robust = {c2}; base means equal → price 0.
  const r = RS.optimizeResilience(ctxEq, env(eqPlan(), [{ id: "Y", label: "без записи s-b", disabled_source_ids: ["s-b"] }]), { F });
  check("H01", "robust ≠ nominal with zero price: nominal {c1}, robust {c2}, worst case Y for the nominal, price 0 m (not an invented advantage)",
    r.status === "optimal" && r.nominal.selected_ids.join() === "c1" && r.robust.selected_ids.join() === "c2" && r.nominal.worst_case_ids.join() === "Y" && r.price_of_robustness_m === 0 && r.same_plan === false,
    { nominal: r.nominal && r.nominal.selected_ids, robust: r.robust && r.robust.selected_ids, price: r.price_of_robustness_m, worst: r.nominal && r.nominal.worst_case_ids });
  check("H02", "W of the robust plan is one real case vector (base and Y tie → both listed, sorted)", r.robust.worst_case_ids.join() === "Y,base" && JSON.stringify(r.robust.worst_vector) === "[0,1111950,555975]", r.robust);
  // drop every source: without a site all points are unknown in that case; the empty plan has W = (3, 0, null)
  const all = RS.optimizeResilience(ctxEq, env(eqPlan({ budget: 0 }), [{ id: "Z", label: "все записи исключены", disabled_source_ids: ["s-a", "s-b"] }]), { F });
  const z = all.robust.per_case.find((x) => x.case_id === "Z");
  check("H03", "all records of the category excluded and budget 0: unknown 3, mean/max null (not 0), W = (3, 0, null); price known (base means)",
    all.status === "optimal" && z.metrics.unknown_count === 3 && z.metrics.weighted_mean_mm === null && z.metrics.max_mm === null && JSON.stringify(all.robust.worst_vector) === "[3,0,null]" && all.price_of_robustness_m === 0, { z, W: all.robust.worst_vector });
  const two = RS.optimizeResilience(ctxEq, env(eqPlan({ budget: 20, max_selected: 2 }), [{ id: "Y", label: "без s-b", disabled_source_ids: ["s-b"] }, { id: "Y2", label: "то же, другой ID", disabled_source_ids: ["s-b"] }]), { F });
  const one = RS.optimizeResilience(ctxEq, env(eqPlan({ budget: 20, max_selected: 2 }), [{ id: "Y", label: "без s-b", disabled_source_ids: ["s-b"] }]), { F });
  check("H04", "two cases with the same exclusions: allowed, both reported, the plans do not change because of the duplicate",
    two.robust.selected_ids.join() === one.robust.selected_ids.join() && two.nominal.selected_ids.join() === one.nominal.selected_ids.join() && two.robust.per_case.length === 3, { two: two.robust.selected_ids, one: one.robust.selected_ids });
  const inf = RS.optimizeResilience(ctxEq, env(eqPlan({ required_ids: ["c1", "c2"], budget: 15, max_selected: 2 }), [{ id: "Y", label: "без s-b", disabled_source_ids: ["s-b"] }]), { F });
  check("H05", "required sites over the budget: infeasible with the reason, price null with a reason, constraints not dropped", inf.status === "infeasible" && inf.robust === null && inf.price_of_robustness_m === null && /обязательных/.test(inf.reasons[0].text) && !!inf.price_reason, inf);
  const ev = RS.evaluateResilience(ctxEq, env(eqPlan({ selected_ids: ["c1"] }), [{ id: "Y", label: "без s-b", disabled_source_ids: ["s-b"] }]));
  check("H06", "evaluateResilience (manual {c1}): per case metrics; worst case Y with W = (0, 1 667 926, 1 111 951)", ev.feasible && ev.worst_case_ids.join() === "Y" && JSON.stringify(ev.worst_vector) === "[0,1667926,1111951]", ev);
}
// ---------- refusals ----------
const good = () => env(eqPlan(), [{ id: "Y", label: "без s-b", disabled_source_ids: ["s-b"] }]);
const { REJ } = require(path.join(HERE, "resilience_cases.cjs"));  // shared with build_resilience_crosscheck.cjs
for (const [name, mut, want] of REJ) {
  const e = good(); e.__ctx = ctxEq; mut(e); delete e.__ctx;
  const got = code(() => RS.validateResilience(e, ctxEq));
  check("V-" + name, `refused: ${name}${want ? " → " + want : " (v2 code)"}`, got !== "accepted" && (want === null || got === want), got);
}
check("V-ok", "a valid envelope with 12 candidates is accepted (limit is 12)", code(() => RS.validateResilience(env(eqPlan({ candidates: Array.from({ length: 12 }, (_, i) => ({ id: "k" + i, lon: 0.001 * (i + 1), lat: 0, category: "school", kind: "hypothetical", cost: 1 })) }), good().cases), ctxEq)) === "accepted", null);
{
  // mutation after validation cannot bypass the limit: public search entry re-validates
  const e = RS.validateResilience(env(eqPlan({ candidates: Array.from({ length: 12 }, (_, i) => ({ id: "k" + i, lon: 0.001 * (i + 1), lat: 0, category: "school", kind: "hypothetical", cost: 1 })) }), good().cases), ctxEq);
  e.plan.candidates.push({ id: "k12", lon: 0.0005, lat: 0, category: "school", kind: "hypothetical", cost: 1 });
  check("V-mutated", "a validated envelope mutated to 13 candidates → createResilienceSearch refuses (too_many_candidates) before precomputation", code(() => RS.createResilienceSearch(ctxEq, e, { F })) === "too_many_candidates", null);
  const s = RS.createResilienceSearch(ctxEq, good(), { F }); s.step(3);
  const part = s.result(); s.cancel(); const canc = s.result();
  check("V-partial", "an unfinished search is «incomplete», a cancelled one «cancelled»; neither is «optimal» nor has plans", part.status === "incomplete" && canc.status === "cancelled" && !part.robust && !canc.nominal, { part: part.status, canc: canc.status });
  const a = env(eqPlan({ budget: 20, max_selected: 2 }), [{ id: "Y", label: "без s-b", disabled_source_ids: ["s-b"] }, { id: "X", label: "без s-a", disabled_source_ids: ["s-a"] }]);
  const b = clone(a); b.cases.reverse(); b.plan.candidates.reverse(); b.plan.control_points.reverse();
  const ra = RS.optimizeResilience(ctxEq, a, { F }), rb = RS.optimizeResilience(ctxEq, b, { F });
  check("V-order", "order of cases, candidates and points changes neither the plans nor resilience_problem_digest", ra.resilience_problem_digest === rb.resilience_problem_digest && ra.robust.selected_ids.join() === rb.robust.selected_ids.join() && ra.nominal.selected_ids.join() === rb.nominal.selected_ids.join(), { a: ra.resilience_problem_digest, b: rb.resilience_problem_digest });
  const c = clone(a); c.plan.selected_ids = ["c2"];
  const va = RS.validateResilience(a, ctxEq), vc = RS.validateResilience(c, ctxEq);
  check("V-digest", "selected_ids: same problem digest, different scenario digest; a changed label changes the problem digest",
    RS.resilienceProblemDigest(va, F) === RS.resilienceProblemDigest(vc, F) && RS.resilienceScenarioDigest(va, F) !== RS.resilienceScenarioDigest(vc, F) &&
    RS.resilienceProblemDigest(RS.validateResilience({ ...a, cases: [{ ...a.cases[0], label: "другое" }, a.cases[1]] }, ctxEq), F) !== RS.resilienceProblemDigest(va, F), null);
  const frozen = JSON.stringify(ctxEq.places);
  RS.optimizeResilience(ctxEq, a, { F });
  check("V-immutable", "the source context is not mutated by case filtering", JSON.stringify(ctxEq.places) === frozen && Object.isFrozen(ctxEq.places), null);
}
{
  // a real school record ID inside an outpatient-clinic envelope (Shymkent) → unknown_source
  const ctx = PL.makeContext(D, "shymkent", F), plan = JSON.parse(fs.readFileSync(path.join(R8, "fixtures", "synthetic_demo_shymkent_outpatient_clinic.json"), "utf8"));
  const school = RS.sourceIds(ctx, "school")[0], clinic = RS.sourceIds(ctx, "outpatient_clinic")[0];
  check("V-other-category", "a real school record ID in a clinic envelope is refused (unknown_source); a clinic ID is accepted",
    code(() => RS.validateResilience(env(plan, [{ id: "C1", label: "школа", disabled_source_ids: [school] }]), ctx)) === "unknown_source" &&
    code(() => RS.validateResilience(env(plan, [{ id: "C1", label: "поликлиника", disabled_source_ids: [clinic] }]), ctx)) === "accepted", { school, clinic });
}
// ---------- real slices (and the hand envelopes) vs the Python oracle ----------
const timing = [];
const { realEnvelopes, handEnvelopes } = require(path.join(HERE, "resilience_cases.cjs"));
const ctxs = { synthetic_eq: ctxEq };
const ctxOf = (city) => ctxs[city] || (ctxs[city] = PL.makeContext(D, city, F));
function compareWithOracle(items, dataFile, tag) {
  fs.writeFileSync(path.join(OUT, `cases${tag}.json`), JSON.stringify(items.map((c) => ({ name: c.name, envelope: c.envelope })), null, 1) + "\n");
  const py = spawnSync("python3", [path.join(HERE, "oracle_resilience.py"), "--data", dataFile, "--cases", path.join(OUT, `cases${tag}.json`), "--out", path.join(OUT, `oracle${tag}.json`)], { encoding: "utf8" });
  if (py.status !== 0) { check("O00" + tag, "Python oracle ran", false, (py.stderr || String(py.error)).slice(0, 300), false); return; }
  const orc = JSON.parse(fs.readFileSync(path.join(OUT, `oracle${tag}.json`), "utf8"));
  const pick = (x) => x && { selected_ids: x.selected_ids, cost: x.cost, worst_case_ids: x.worst_case_ids, worst_vector: x.worst_vector,
    per_case: x.per_case.map((c) => ({ case_id: c.case_id, unknown_count: c.metrics ? c.metrics.unknown_count : c.unknown_count, weighted_sum_mm: c.metrics ? c.metrics.weighted_sum_mm : c.weighted_sum_mm, max_mm: c.metrics ? c.metrics.max_mm : c.max_mm, covered_weight: c.metrics ? c.metrics.covered_weight : c.covered_weight })) };
  items.forEach((c, i) => {
    const ctx = ctxOf(c.envelope.plan.city_id), t0 = process.hrtime.bigint(), r = RS.optimizeResilience(ctx, c.envelope, { F }), ms = Number(process.hrtime.bigint() - t0) / 1e6, o = orc[i];
    timing.push({ name: c.name, ms: Math.round(ms * 10) / 10, subsets: r.total_subsets, feasible: r.feasible_count, cases: c.envelope.cases.length + 1 });
    const a = JSON.stringify({ status: r.status, feasible: r.status === "optimal" ? r.feasible_count : 0, nominal: pick(r.nominal), robust: pick(r.robust), price: r.price_of_robustness_m });
    const b = JSON.stringify({ status: o.status, feasible: o.feasible_count, nominal: o.nominal && pick(o.nominal), robust: o.robust && pick(o.robust), price: o.price_of_robustness_m });
    check("O-" + c.name, `adapter on BUILD plan.js = Python oracle (nominal, robust, W, worst cases, per-case metrics, price): ${c.name}`, a === b, { js: a.slice(0, 500), oracle: b.slice(0, 500) });
    if (o.status !== "optimal") return;
    const m = RS.evaluateResilience(ctx, c.envelope);
    check("E-" + c.name, `evaluateResilience of the manual plan = oracle: ${c.name}`, JSON.stringify(pick({ ...m })) === JSON.stringify(pick(o.manual)), { js: pick(m), oracle: o.manual });
    const v2 = PL.optimizePlans(ctx, PL.validatePlanScenario(c.envelope.plan, ctx), { F });
    check("N-" + c.name, `nominal plan = BUILD v2 mean optimum on the same plan: ${c.name}`, r.nominal && v2.objectives && r.nominal.selected_ids.join() === v2.objectives.mean.ids.join(), { resilience: r.nominal && r.nominal.selected_ids, v2: v2.objectives && v2.objectives.mean.ids });
  });
}
compareWithOracle(realEnvelopes(PL, D, F, R8), path.join(W, "data.js"), "");
const eqFile = path.join(OUT, "synthetic_eq_data.js");
fs.writeFileSync(eqFile, "// SYNTHETIC equator test city (K07 tests), not city data\nwindow.CITY_EVIDENCE = " + JSON.stringify(EQ_DATA) + ";\n");
compareWithOracle(handEnvelopes(ctxEq), eqFile, "_eq");
fs.writeFileSync(path.join(OUT, "timing.json"), JSON.stringify({ node: process.version, platform: `${process.platform} ${process.arch}`, cases: timing }, null, 1) + "\n");
const by = (v) => checks.filter((c) => c.verdict === v).length;
fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify({ kind: "K07 r9 resilience adapter on BUILD plan.js", app_root: path.basename(ROOT), total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"), checks }, null, 1) + "\n");
for (const c of checks) if (c.verdict !== "PASS") console.log(`${c.verdict} ${c.id} ${c.name} -> ${JSON.stringify(c.observed).slice(0, 400)}`);
console.log(`PASS ${by("PASS")} · FAIL ${by("FAIL")} · TEST_INCOMPATIBLE ${by("TEST_INCOMPATIBLE")} of ${checks.length}`);
process.exitCode = by("FAIL") || by("TEST_INCOMPATIBLE") ? 1 : 0;
