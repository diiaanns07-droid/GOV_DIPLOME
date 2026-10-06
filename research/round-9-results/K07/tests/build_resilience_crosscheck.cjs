// K07 round 9: independent check of the BUILD engine web/resilience.js (city-resilience-v1) against the K07 Python oracle.
// Usage: node build_resilience_crosscheck.cjs --app-root <BUILD extraction with web/resilience.js> [--out <dir>]
// The BUILD module was read first (pure functions on plan.js, no I/O) and is only loaded and called. Adapter: BUILD gives
// worst_vector as {unknown_count, weighted_sum_mm, max_mm}; the oracle as [u, sum, max]. Only mathematics is compared
// (plan IDs, vectors, metrics, price, status), never internal digests. Refusals: only "refused" is compared (codes differ).
// Envelopes: tests/resilience_cases.cjs — 6 hand envelopes on the SYNTHETIC equator city, 10 on the real slices.
const fs = require("fs"), path = require("path"), vm = require("vm"), { spawnSync } = require("child_process");
const HERE = __dirname, K = path.join(HERE, ".."), R8 = path.join(K, "..", "..", "round-8-results", "K07");
const argv = process.argv.slice(2), arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const ROOT = path.resolve(arg("--app-root", "")), W = fs.existsSync(path.join(ROOT, "web")) ? path.join(ROOT, "web") : ROOT;
const OUT = path.resolve(arg("--out", path.join(K, "results", "build_resilience")));
fs.mkdirSync(OUT, { recursive: true });
const checks = [];
function check(id, name, ok, observed, pre) { checks.push({ id, name, verdict: pre === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL", observed: ok ? undefined : observed }); }
function finish() {
  const by = (v) => checks.filter((c) => c.verdict === v).length;
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify({ kind: "K07 r9 cross-check of BUILD web/resilience.js vs K07 oracle", app_root: path.basename(ROOT), total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"), checks }, null, 1) + "\n");
  for (const c of checks) if (c.verdict !== "PASS") console.log(`${c.verdict} ${c.id} ${c.name} -> ${JSON.stringify(c.observed).slice(0, 400)}`);
  console.log(`PASS ${by("PASS")} · FAIL ${by("FAIL")} · TEST_INCOMPATIBLE ${by("TEST_INCOMPATIBLE")} of ${checks.length}`);
  process.exitCode = by("FAIL") || by("TEST_INCOMPATIBLE") ? 1 : 0;
}
if (!fs.existsSync(path.join(W, "resilience.js"))) { check("X00", "BUILD web/resilience.js present", false, W, false); finish(); return; }
const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js")), RS = require(path.join(W, "resilience.js"));
const { EQ_DATA } = require(path.join(R8, "tests", "plan_cases.cjs"));
const { env, eqPlan, handEnvelopes, realEnvelopes, REJ } = require(path.join(HERE, "resilience_cases.cjs"));
const box = {}; vm.createContext(box); box.window = box;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), box);
const D = box.CITY_EVIDENCE;
const ctxEq = PL.makeContext(EQ_DATA, "synthetic_eq", F), ctxs = { synthetic_eq: ctxEq };
const ctxOf = (city) => ctxs[city] || (ctxs[city] = PL.makeContext(D, city, F));
const refused = (fn) => { try { fn(); return null; } catch (e) { return e.code || e.message; } };

// refusals (CORE_SPEC r9): every mutation must be refused by BUILD too
for (const [name, mut] of REJ) {
  const e = env(eqPlan(ctxEq), [{ id: "Y", label: "без s-b", disabled_source_ids: ["s-b"] }]); e.__ctx = ctxEq; mut(e); delete e.__ctx;
  const code = refused(() => RS.validateResilience(e, ctxEq));
  check("XV-" + name, `BUILD refuses: ${name}`, code !== null, { code });
}
{
  // public entries validate an unverified object: a validated envelope mutated to 13 candidates must still be refused
  const ok = env(eqPlan(ctxEq, { candidates: Array.from({ length: 12 }, (_, i) => ({ id: "k" + i, lon: 0.001 * (i + 1), lat: 0, category: "school", kind: "hypothetical", cost: 1 })) }), [{ id: "Y", label: "без s-b", disabled_source_ids: ["s-b"] }]);
  const v = RS.validateResilience(ok, ctxEq);
  v.plan.candidates.push({ id: "k12", lon: 0.0005, lat: 0, category: "school", kind: "hypothetical", cost: 1 });
  check("XV-mutated", "BUILD createResilienceSearch refuses an envelope mutated to 13 candidates after validation", refused(() => RS.createResilienceSearch(ctxEq, v, { F })) !== null, null);
  const real = ctxOf("shymkent"), clinicPlan = JSON.parse(fs.readFileSync(path.join(R8, "fixtures", "synthetic_demo_shymkent_outpatient_clinic.json"), "utf8"));
  const school = real.places.find((p) => p.group === "school").id;
  check("XV-other-category", "BUILD refuses a real school record ID in a clinic envelope", refused(() => RS.validateResilience(env(clinicPlan, [{ id: "C1", label: "школа", disabled_source_ids: [school] }]), real)) !== null, { school });
}
function compare(items, dataFile, tag) {
  fs.writeFileSync(path.join(OUT, `cases${tag}.json`), JSON.stringify(items.map((c) => ({ name: c.name, envelope: c.envelope })), null, 1) + "\n");
  const py = spawnSync("python3", [path.join(HERE, "oracle_resilience.py"), "--data", dataFile, "--cases", path.join(OUT, `cases${tag}.json`), "--out", path.join(OUT, `oracle${tag}.json`)], { encoding: "utf8" });
  if (py.status !== 0) { check("XO00" + tag, "Python oracle ran", false, (py.stderr || String(py.error)).slice(0, 300), false); return; }
  const orc = JSON.parse(fs.readFileSync(path.join(OUT, `oracle${tag}.json`), "utf8"));
  const vec = (w) => (Array.isArray(w) ? w : [w.unknown_count, w.weighted_sum_mm, w.max_mm === undefined ? null : w.max_mm]);
  const pick = (x) => x && { selected_ids: x.selected_ids, cost: x.cost, worst_case_ids: x.worst_case_ids.slice().sort(), worst_vector: vec(x.worst_vector),
    per_case: x.per_case.map((c) => { const m = c.metrics || c; return { case_id: c.case_id, unknown_count: m.unknown_count, weighted_sum_mm: m.weighted_sum_mm, max_mm: m.max_mm, covered_weight: m.covered_weight }; }) };
  items.forEach((c, i) => {
    const ctx = ctxOf(c.envelope.plan.city_id), o = orc[i];
    let r, m, v2;
    try { r = RS.optimizeResilience(ctx, c.envelope, { F }); } catch (e) { check("XO-" + c.name, `BUILD optimizeResilience runs: ${c.name}`, false, e.code || e.message); return; }
    const a = JSON.stringify({ status: r.status, feasible: r.status === "optimal" ? r.feasible_count : 0, nominal: pick(r.nominal), robust: pick(r.robust), price: r.price_of_robustness_m });
    const b = JSON.stringify({ status: o.status, feasible: o.feasible_count, nominal: o.nominal && pick(o.nominal), robust: o.robust && pick(o.robust), price: o.price_of_robustness_m });
    check("XO-" + c.name, `BUILD resilience = K07 oracle (status, feasible count, nominal and robust plans, W, worst cases, per-case metrics, price): ${c.name}`, a === b, { build: a.slice(0, 600), oracle: b.slice(0, 600) });
    if (o.status !== "optimal") return;
    m = RS.evaluateResilience(ctx, c.envelope, c.envelope.plan.selected_ids);
    check("XE-" + c.name, `BUILD evaluateResilience (manual plan) = oracle: ${c.name}`, JSON.stringify(pick(m)) === JSON.stringify(pick(o.manual)), { build: pick(m), oracle: o.manual });
    v2 = PL.optimizePlans(ctx, PL.validatePlanScenario(c.envelope.plan, ctx), { F });
    check("XN-" + c.name, `BUILD nominal = BUILD v2 mean optimum: ${c.name}`, r.nominal.selected_ids.join() === v2.objectives.mean.ids.join(), { nominal: r.nominal.selected_ids, v2: v2.objectives.mean.ids });
  });
}
compare(realEnvelopes(PL, D, F, R8), path.join(W, "data.js"), "");
const eqFile = path.join(OUT, "synthetic_eq_data.js");
fs.writeFileSync(eqFile, "// SYNTHETIC equator test city (K07 tests), not city data\nwindow.CITY_EVIDENCE = " + JSON.stringify(EQ_DATA) + ";\n");
compare(handEnvelopes(ctxEq), eqFile, "_eq");
{
  // order independence and immutability on a real slice
  const it = realEnvelopes(PL, D, F, R8).find((c) => c.name === "astana/school/max_12x25x8"), ctx = ctxOf("astana");
  const b = JSON.parse(JSON.stringify(it.envelope)); b.cases.reverse(); b.plan.candidates.reverse(); b.plan.control_points.reverse();
  const before = JSON.stringify(ctx.places);
  const ra = RS.optimizeResilience(ctx, it.envelope, { F }), rb = RS.optimizeResilience(ctx, b, { F });
  check("XP-order", "BUILD: order of cases, candidates and points changes neither plans nor resilience_problem_digest", ra.resilience_problem_digest === rb.resilience_problem_digest && ra.robust.selected_ids.join() === rb.robust.selected_ids.join() && ra.nominal.selected_ids.join() === rb.nominal.selected_ids.join(), { a: ra.robust.selected_ids, b: rb.robust.selected_ids });
  check("XP-immutable", "BUILD: the source context is not mutated by a run", JSON.stringify(ctx.places) === before, null);
  const s = RS.createResilienceSearch(ctx, it.envelope, { F }); s.step(10); s.cancel();
  const rc = s.result();
  check("XP-cancel", "BUILD: a cancelled search is not «optimal» and has no plans", rc.status !== "optimal" && !rc.robust && !rc.nominal, { status: rc.status });
}
finish();
