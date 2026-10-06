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
const REJ = [
  ["unknown top field (derived)", (e) => { e.derived_results = { robust: ["c3"] }; }, "unknown_field"], ["schema", (e) => { e.schema_version = "city-resilience-v2"; }, "bad_schema"],
  ["no cases", (e) => { e.cases = []; }, "bad_count"], ["8 user cases", (e) => { e.cases = Array.from({ length: 8 }, (_, i) => ({ id: "c" + i, label: "x", disabled_source_ids: ["s-a"] })); }, "bad_count"],
  ["case id base", (e) => { e.cases[0].id = "base"; }, "reserved_id"], ["duplicate case id", (e) => { e.cases.push({ ...e.cases[0] }); }, "duplicate_id"],
  ["case id with markup", (e) => { e.cases[0].id = "<b>"; }, "bad_id"], ["empty label", (e) => { e.cases[0].label = "  "; }, "bad_label"],
  ["label 121 chars", (e) => { e.cases[0].label = "я".repeat(121); }, "bad_label"], ["label with control char", (e) => { e.cases[0].label = "a\u0007b"; }, "bad_label"],
  ["no exclusions", (e) => { e.cases[0].disabled_source_ids = []; }, "bad_exclusions"], ["duplicate exclusion", (e) => { e.cases[0].disabled_source_ids = ["s-b", "s-b"]; }, "duplicate_id"],
  ["candidate ID as exclusion", (e) => { e.cases[0].disabled_source_ids = ["c1"]; }, "candidate_not_source"], ["unknown source", (e) => { e.cases[0].disabled_source_ids = ["s-z"]; }, "unknown_source"],
  ["source of another category (no clinic records here)", (e) => { e.plan = eqPlan({ category: "outpatient_clinic", candidates: eqPlan().candidates.map((c) => ({ ...c, category: "outpatient_clinic" })) }); }, null],
  ["extra case field", (e) => { e.cases[0].weight = 5; }, "unknown_field"], ["bad plan (v2 rule)", (e) => { e.plan.budget = -1; }, null],
  ["13 candidates", (e) => { e.plan.candidates = Array.from({ length: 13 }, (_, i) => ({ id: "k" + i, lon: 0.001 * (i + 1), lat: 0, category: "school", kind: "hypothetical", cost: 1 })); }, "too_many_candidates"],
];
for (const [name, mut, want] of REJ) {
  const e = good(); mut(e);
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
// ---------- real slices vs the Python oracle ----------
const timing = [];
function realEnvelopes() {
  const out = [];
  for (const city of ["shymkent", "astana"]) {
    const ctx = PL.makeContext(D, city, F);
    for (const cat of ["school", "outpatient_clinic"]) {
      const plan = JSON.parse(fs.readFileSync(path.join(R8, "fixtures", `synthetic_demo_${city}_${cat}.json`), "utf8"));
      const src = RS.sourceIds(ctx, cat).sort();
      const cases = [{ id: "C1", label: "две записи под вопросом", disabled_source_ids: src.slice(0, 2) },
        { id: "C2", label: "пять записей", disabled_source_ids: src.slice(0, 5) },
        { id: "C3", label: "то же, что C1", disabled_source_ids: src.slice(0, 2) },
        { id: "C4", label: "все записи категории", disabled_source_ids: src.slice() }];
      out.push({ name: `${city}/${cat}/demo`, ctx, envelope: env({ ...plan, selected_ids: ["site-2"] }, cases) });
      out.push({ name: `${city}/${cat}/budget300_max3`, ctx, envelope: env({ ...plan, budget: 300, max_selected: 3, selected_ids: ["site-2", "site-4"] }, cases.slice(0, 2)) });
    }
    // 12 sites × 25 points × 8 cases (SYNTHETIC grid inside the real bbox)
    const bb = ctx.bbox, g = (u, v) => [Math.round((bb[0] + (bb[2] - bb[0]) * u) * 1e6) / 1e6, Math.round((bb[1] + (bb[3] - bb[1]) * v) * 1e6) / 1e6];
    const src = RS.sourceIds(ctx, "school").sort();
    const plan = { schema_version: "city-plan-v2", city_id: city, source_snapshot: ctx.source_snapshot, category: "school",
      control_points: Array.from({ length: 25 }, (_, i) => { const [lon, lat] = g(0.08 + 0.21 * (i % 5), 0.08 + 0.21 * Math.floor(i / 5)); return { id: `cp-${i + 1}`, lon, lat, weight: 1 + (i * 7) % 10 }; }),
      candidates: Array.from({ length: 12 }, (_, i) => { const [lon, lat] = g(0.12 + 0.25 * (i % 4), 0.12 + 0.37 * Math.floor(i / 4)); return { id: `site-${String(i + 1).padStart(2, "0")}`, lon, lat, category: "school", kind: "hypothetical", cost: 50 + (i * 37) % 120 }; }),
      budget: 400, max_selected: 5, coverage_radius_m: 300, required_ids: [], excluded_ids: [], selected_ids: ["site-01"] };
    const cases = Array.from({ length: 7 }, (_, k) => ({ id: `K${k + 1}`, label: `случай ${k + 1}`, disabled_source_ids: src.filter((_, i) => (i + k) % (k + 2) === 0).slice(0, Math.max(1, Math.min(src.length, k + 1))) }));
    out.push({ name: `${city}/school/max_12x25x8`, ctx, envelope: env(plan, cases) });
  }
  return out;
}
const items = realEnvelopes();
fs.writeFileSync(path.join(OUT, "cases.json"), JSON.stringify(items.map((c) => ({ name: c.name, envelope: c.envelope })), null, 1) + "\n");
const py = spawnSync("python3", [path.join(HERE, "oracle_resilience.py"), "--data", path.join(W, "data.js"), "--cases", path.join(OUT, "cases.json"), "--out", path.join(OUT, "oracle.json")], { encoding: "utf8" });
if (py.status !== 0) check("O00", "Python oracle ran", false, (py.stderr || String(py.error)).slice(0, 300), false);
else {
  const orc = JSON.parse(fs.readFileSync(path.join(OUT, "oracle.json"), "utf8"));
  const pick = (x) => x && { selected_ids: x.selected_ids, cost: x.cost, worst_case_ids: x.worst_case_ids, worst_vector: x.worst_vector,
    per_case: x.per_case.map((c) => ({ case_id: c.case_id, unknown_count: c.metrics ? c.metrics.unknown_count : c.unknown_count, weighted_sum_mm: c.metrics ? c.metrics.weighted_sum_mm : c.weighted_sum_mm, max_mm: c.metrics ? c.metrics.max_mm : c.max_mm, covered_weight: c.metrics ? c.metrics.covered_weight : c.covered_weight })) };
  items.forEach((c, i) => {
    const t0 = process.hrtime.bigint(), r = RS.optimizeResilience(c.ctx, c.envelope, { F }), ms = Number(process.hrtime.bigint() - t0) / 1e6, o = orc[i];
    timing.push({ name: c.name, ms: Math.round(ms * 10) / 10, subsets: r.total_subsets, feasible: r.feasible_count, cases: c.envelope.cases.length + 1 });
    const a = JSON.stringify({ status: r.status, feasible: r.feasible_count, nominal: pick(r.nominal), robust: pick(r.robust), price: r.price_of_robustness_m });
    const b = JSON.stringify({ status: o.status, feasible: o.feasible_count, nominal: o.nominal && pick(o.nominal), robust: o.robust && pick(o.robust), price: o.price_of_robustness_m });
    check("O-" + c.name, `adapter on BUILD plan.js = Python oracle (nominal, robust, W, worst cases, per-case metrics, price): ${c.name}`, a === b, { js: a.slice(0, 500), oracle: b.slice(0, 500) });
    const m = RS.evaluateResilience(c.ctx, c.envelope);
    check("E-" + c.name, `evaluateResilience of the manual plan = oracle: ${c.name}`, JSON.stringify(pick({ ...m })) === JSON.stringify(pick(o.manual)), { js: pick(m), oracle: o.manual });
    const v2 = PL.optimizePlans(c.ctx, PL.validatePlanScenario(c.envelope.plan, c.ctx), { F });
    check("N-" + c.name, `nominal plan = BUILD v2 mean optimum on the same plan: ${c.name}`, r.nominal && v2.objectives && r.nominal.selected_ids.join() === v2.objectives.mean.ids.join(), { resilience: r.nominal && r.nominal.selected_ids, v2: v2.objectives && v2.objectives.mean.ids });
  });
}
fs.writeFileSync(path.join(OUT, "timing.json"), JSON.stringify({ node: process.version, platform: `${process.platform} ${process.arch}`, cases: timing }, null, 1) + "\n");
const by = (v) => checks.filter((c) => c.verdict === v).length;
fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify({ kind: "K07 r9 resilience adapter on BUILD plan.js", app_root: path.basename(ROOT), total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"), checks }, null, 1) + "\n");
for (const c of checks) if (c.verdict !== "PASS") console.log(`${c.verdict} ${c.id} ${c.name} -> ${JSON.stringify(c.observed).slice(0, 400)}`);
console.log(`PASS ${by("PASS")} · FAIL ${by("FAIL")} · TEST_INCOMPATIBLE ${by("TEST_INCOMPATIBLE")} of ${checks.length}`);
process.exitCode = by("FAIL") || by("TEST_INCOMPATIBLE") ? 1 : 0;
