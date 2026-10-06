/* K05 r9 этап 2: resilience.js поверх НАСТОЯЩЕГО web/plan.js сборки.
 *   node tests/test_resilience.cjs --app-root <checkout>/prototypes/city-evidence [--json OUT]
 * Это тест модуля K05 на API сборки, НЕ тест интегрированной функции BUILD (resilience.js в сборку не встроен).
 */
"use strict";
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const assert = require("node:assert/strict");
const argv = process.argv.slice(2), arg = (k) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : null);
const APP = arg("--app-root");
if (!APP) { console.error("нужен --app-root"); process.exit(2); }
const W = path.join(APP, "web");
const sb = {}; vm.createContext(sb); sb.window = sb;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), sb);
const F = require(path.join(W, "facts.js")), X = require(path.join(W, "whatif.js")), PL = require(path.join(W, "plan.js"));
const RS = require(path.join(__dirname, "..", "resilience.js")).bind(PL, F, X);
const D = sb.CITY_EVIDENCE;
const results = [];
const t = (name, fn) => {
  try { fn(); results.push({ name, status: "PASS" }); console.log("PASS", name); }
  catch (e) { results.push({ name, status: "FAIL", error: String(e.stack || e).slice(0, 800) }); console.log("FAIL", name, "—", String(e.message || e).slice(0, 300)); }
};
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || e.message; } };

// ---------- фикстуры: реальный срез + SYNTHETIC кандидаты/точки/случаи ----------
function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let x = a; x = Math.imul(x ^ (x >>> 15), x | 1); x ^= x + Math.imul(x ^ (x >>> 7), x | 61); return ((x ^ (x >>> 14)) >>> 0) / 4294967296; }; }
const ctxOf = (city) => PL.makeContext(D, city, F);
function planOf(ctx, cat, { seed = 1, nP = 10, nC = 6, budget = 400, maxSel = 3, radius = 400, req = [], exc = [], sel = [] } = {}) {
  const r = rng(seed), b = ctx.bbox, at = () => [b[0] + (b[2] - b[0]) * r(), b[1] + (b[3] - b[1]) * r()];
  return { schema_version: PL.SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, category: cat,
    control_points: Array.from({ length: nP }, (_, i) => { const [lon, lat] = at(); return { id: `syn_p${i}`, lon, lat, weight: 1 + Math.floor(r() * 5) }; }),
    candidates: Array.from({ length: nC }, (_, i) => { const [lon, lat] = at(); return { id: `syn_c${String(i).padStart(2, "0")}`, lon, lat, category: cat, kind: "hypothetical", cost: 50 + Math.floor(r() * 150) }; }),
    budget, max_selected: maxSel, coverage_radius_m: radius, required_ids: req, excluded_ids: exc, selected_ids: sel };
}
const srcIds = (ctx, cat) => ctx.places.filter((p) => p.group === cat).map((p) => p.id).sort();
function envOf(ctx, cat, opt = {}, cases) {
  const s = srcIds(ctx, cat);
  return { schema_version: RS.SCHEMA, plan: planOf(ctx, cat, opt),
    cases: cases || [{ id: "c_first", label: "SYNTHETIC: первые 2 записи не учитываются", disabled_source_ids: s.slice(0, 2) },
      { id: "c_last", label: "SYNTHETIC: последние 3 записи", disabled_source_ids: s.slice(-3) }] };
}

// ---------- валидация ----------
const sh = ctxOf("shymkent");
t("валидный конверт: deep-frozen копия, cases отсортированы по исключениям", () => {
  const env = RS.validateResilience(envOf(sh, "school"), sh);
  assert.ok(Object.isFrozen(env) && Object.isFrozen(env.plan) && Object.isFrozen(env.cases[0].disabled_source_ids));
  assert.throws(() => { env.plan.candidates.push({}); });
});
t("коды ошибок конверта", () => {
  const e = () => envOf(sh, "school");
  const v = (mut) => { const x = e(); mut(x); return code(() => RS.validateResilience(x, sh)); };
  assert.equal(v((x) => { x.schema_version = "city-resilience-v2"; }), "bad_version");
  assert.equal(v((x) => { x.result = {}; }), "unknown_field");
  assert.equal(v((x) => { x.plan.derived_results = {}; }), "unknown_field");
  assert.equal(v((x) => { x.cases = []; }), "bad_cases");
  assert.equal(v((x) => { x.cases = Array.from({ length: 8 }, (_, i) => ({ id: "c" + i, label: "x", disabled_source_ids: [srcIds(sh, "school")[0]] })); }), "bad_cases");
  assert.equal(v((x) => { x.cases[0].id = "base"; }), "reserved_id");
  assert.equal(v((x) => { x.cases[1].id = x.cases[0].id; }), "duplicate_id");
  assert.equal(v((x) => { x.cases[0].label = "  "; }), "bad_label");
  assert.equal(v((x) => { x.cases[0].label = "я".repeat(121); }), "bad_label");
  assert.equal(v((x) => { x.cases[0].label = "a\u0007b"; }), "bad_label");
  assert.equal(v((x) => { x.cases[0].label = "я".repeat(120); }), "accepted");
  assert.equal(v((x) => { x.cases[0].disabled_source_ids = []; }), "bad_exclusions");
  assert.equal(v((x) => { x.cases[0].disabled_source_ids = srcIds(sh, "school").concat(["extra"]); }), "bad_exclusions");
  assert.equal(v((x) => { x.cases[0].disabled_source_ids = ["syn_c01"]; }), "candidate_not_source");
  assert.equal(v((x) => { x.cases[0].disabled_source_ids = ["nope"]; }), "unknown_source");
  const otherCat = srcIds(sh, "outpatient_clinic")[0];
  assert.equal(v((x) => { x.cases[0].disabled_source_ids = [otherCat]; }), "unknown_source");
  assert.equal(v((x) => { x.cases[0].disabled_source_ids = [srcIds(sh, "school")[0], srcIds(sh, "school")[0]]; }), "duplicate_id");
  assert.equal(v((x) => { x.cases[0].extra = 1; }), "unknown_field");
  assert.equal(v((x) => { x.plan.source_snapshot = "sha256:other"; }), "foreign_snapshot");
  assert.equal(v((x) => { x.cases[0].label = 5; }), "bad_label");
});
t("13 кандидатов → too_many_candidates до проверки plan (даже если plan иначе ошибочен); 12 проходит", () => {
  const x = envOf(sh, "school", { nC: 13 });
  x.plan.budget = -1;  // иначе ошибка v2 — но размер проверяется раньше
  assert.equal(code(() => RS.validateResilience(x, sh)), "too_many_candidates");
  assert.equal(code(() => RS.validateResilience(envOf(sh, "school", { nC: 12 }), sh)), "accepted");
  // прямой вызов публичного API с непроверенным объектом тоже проходит проверку
  assert.equal(code(() => RS.createResilienceSearch(sh, envOf(sh, "school", { nC: 16 }))), "too_many_candidates");
  assert.equal(code(() => RS.evaluateResilience(sh, envOf(sh, "school", { nC: 14 }), [])), "too_many_candidates");
});
t("строгий импорт: NaN, 1e999, повтор ключа, >256 KiB; экспорт→импорт → тот же конверт и digest", () => {
  const env = RS.validateResilience(envOf(sh, "school"), sh);
  const txt = RS.exportResilience(env);
  const back = RS.importResilience(txt, sh);
  assert.deepEqual(back, env);
  assert.equal(RS.digests(back).resilience_scenario_digest, RS.digests(env).resilience_scenario_digest);
  for (const bad of [txt.replace('"budget":400', '"budget":NaN'), txt.replace('"budget":400', '"budget":1e999'), txt.replace('"budget":400', '"budget":400,"budget":1')])
    assert.equal(code(() => RS.importResilience(bad, sh)), "bad_json");
  assert.equal(code(() => RS.importResilience(" ".repeat(256 * 1024) + txt, sh)), "too_large");
  assert.ok(!/derived|result|worst/.test(txt));
});

// ---------- расчёт ----------
t("контекст не мутирован; base = PL.evaluatePlan на полном срезе", () => {
  const before = JSON.stringify(sh);
  const env = RS.validateResilience(envOf(sh, "school"), sh);
  const ev = RS.evaluateResilience(sh, env, ["syn_c01", "syn_c03"]);
  assert.equal(JSON.stringify(sh), before);
  const ref = PL.evaluatePlan(sh, env.plan, ["syn_c01", "syn_c03"]);
  assert.equal(ev.per_case[0].case_id, "base");
  assert.deepEqual(ev.per_case[0].rows, ref.rows);
  assert.equal(ev.per_case[0].metrics.weighted_mean_mm, ref.metrics.weighted_mean_mm);
});
t("исключение ближайшей записи меняет before только там, где она была ближайшей; кандидаты не меняются", () => {
  const env0 = envOf(sh, "school", { nP: 8 });
  const ref = PL.evaluatePlan(sh, PL.validatePlanScenario(env0.plan, sh), []);
  const nb = ref.rows[0].nearest_before.id;
  const env = RS.validateResilience({ ...env0, cases: [{ id: "drop_nb", label: "SYNTHETIC: без ближайшей к syn_p0", disabled_source_ids: [nb] }] }, sh);
  const ev = RS.evaluateResilience(sh, env, ["syn_c02"]);
  const c = ev.per_case.find((x) => x.case_id === "drop_nb");
  for (let i = 0; i < ref.rows.length; i++) {
    const r0 = ev.per_case[0].rows[i], r1 = c.rows[i];
    if (ref.rows[i].nearest_before.id === nb) assert.ok(r1.before_mm === null || r1.before_mm >= r0.before_mm);
    else assert.equal(r1.before_mm, r0.before_mm);
    assert.notEqual(r1.nearest_before && r1.nearest_before.id, nb);
  }
  assert.equal(c.n_source_records, ev.per_case[0].n_source_records - 1);
});
t("W = лексикографический максимум L по случаям; worst_case_ids — все случаи с W; дубли помечены", () => {
  const s = srcIds(sh, "school");
  const env = RS.validateResilience(envOf(sh, "school", {}, [
    { id: "a", label: "SYNTHETIC a", disabled_source_ids: s.slice(0, 4) }, { id: "b", label: "SYNTHETIC b (= a)", disabled_source_ids: s.slice(0, 4).reverse() },
    { id: "c", label: "SYNTHETIC c", disabled_source_ids: [s[5]] }]), sh);
  const ev = RS.evaluateResilience(sh, env, []);
  const L = (x) => [x.loss.unknown_count, x.loss.weighted_sum_mm, x.loss.max_mm === null ? Infinity : x.loss.max_mm];
  const cmp = (a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
  const Wv = ev.per_case.map(L).reduce((m, x) => (cmp(x, m) > 0 ? x : m));
  assert.deepEqual([ev.worst_vector.unknown_count, ev.worst_vector.weighted_sum_mm, ev.worst_vector.max_mm ?? Infinity], Wv);
  assert.deepEqual(ev.worst_case_ids, ev.per_case.filter((x) => cmp(L(x), Wv) === 0).map((x) => x.case_id).sort());
  assert.deepEqual(ev.per_case.find((x) => x.case_id === "a").same_exclusions_as, ["b"]);
  assert.deepEqual(ev.per_case.find((x) => x.case_id === "a").loss, ev.per_case.find((x) => x.case_id === "b").loss);
});
for (const city of ["shymkent", "astana"]) for (const cat of ["school", "outpatient_clinic"]) {
  t(`${city}/${cat}: nominal = mean-оптимум PL; robust W ≤ nominal W; цена ≥ 0 или null с причиной`, () => {
    const ctx = ctxOf(city);
    const env = RS.validateResilience(envOf(ctx, cat, { seed: city.length + cat.length, nP: 12, nC: 10, budget: 500, maxSel: 3 }), ctx);
    const r = RS.optimizeResilience(ctx, env, { request_id: "q1" });
    assert.equal(r.status, "optimal"); assert.equal(r.total_subsets, 1024); assert.equal(r.evaluated, 1024);
    const nom = PL.optimizePlans(ctx, env.plan, { F });
    assert.deepEqual(r.nominal.selected_ids, nom.objectives.mean.ids);
    const L = (w) => [w.unknown_count, w.weighted_sum_mm, w.max_mm === null ? Infinity : w.max_mm];
    const cmp = (a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
    assert.ok(cmp(L(r.robust.worst_vector), L(r.nominal.worst_vector)) <= 0);
    assert.ok(r.robust.feasible && r.nominal.feasible);
    if (r.price_of_resilience_m !== null) assert.ok(r.price_of_resilience_m >= 0, String(r.price_of_resilience_m));
    else assert.ok(r.price_reason);
    assert.equal(r.same_plan, r.robust.selected_ids.join() === r.nominal.selected_ids.join());
    assert.equal(r.cases[0].id, "base");
    JSON.parse(JSON.stringify(r));  // без Infinity: строгий JSON
    assert.ok(!JSON.stringify(r).includes("Infinity"));
  });
}
t("ручной недопустимый план помечен feasible=false с причинами", () => {
  const env = RS.validateResilience(envOf(sh, "school", { budget: 60, maxSel: 1 }), sh);
  const ev = RS.evaluateResilience(sh, env, ["syn_c00", "syn_c01"]);
  assert.equal(ev.feasible, false);
  assert.ok(ev.reasons.map((x) => x.code).includes("too_many"));
});
t("infeasible required: status infeasible, robust/nominal/price null; ограничения не снимаются", () => {
  const env = RS.validateResilience(envOf(sh, "school", { budget: 10, req: ["syn_c00"] }), sh);
  const r = RS.optimizeResilience(sh, env);
  assert.equal(r.status, "infeasible"); assert.equal(r.robust, null); assert.equal(r.price_of_resilience_m, null);
  assert.equal(r.reasons[0].code, "required_cost_exceeds_budget");
});
t("cancel/неполный поиск: не optimal, robust=null", () => {
  const env = RS.validateResilience(envOf(sh, "school", { nC: 12, budget: 1000, maxSel: 5 }), sh);
  const s = RS.createResilienceSearch(sh, env); s.step(100);
  assert.equal(s.result().status, "incomplete"); assert.equal(s.result().robust, null);
  s.cancel(); assert.equal(s.result().status, "cancelled");
});
t("digest: не зависит от порядка cases/исключений/массивов plan; label меняет, selected_ids — только scenario digest", () => {
  const a = envOf(sh, "school");
  const b = { ...a, plan: { ...a.plan, control_points: a.plan.control_points.slice().reverse(), candidates: a.plan.candidates.slice().reverse() },
    cases: a.cases.slice().reverse().map((c) => ({ ...c, disabled_source_ids: c.disabled_source_ids.slice().reverse() })) };
  const da = RS.digests(RS.validateResilience(a, sh)), db = RS.digests(RS.validateResilience(b, sh));
  assert.equal(da.resilience_problem_digest, db.resilience_problem_digest);
  assert.equal(da.exclusions_digest, db.exclusions_digest);
  const ra = RS.optimizeResilience(sh, RS.validateResilience(a, sh)), rb = RS.optimizeResilience(sh, RS.validateResilience(b, sh));
  assert.deepEqual(ra.robust.selected_ids, rb.robust.selected_ids); assert.deepEqual(ra.robust.worst_vector, rb.robust.worst_vector);
  const c = { ...a, cases: [{ ...a.cases[0], label: "другая подпись" }, a.cases[1]] };
  assert.notEqual(RS.digests(RS.validateResilience(c, sh)).resilience_problem_digest, da.resilience_problem_digest);
  const d = { ...a, plan: { ...a.plan, selected_ids: ["syn_c02"] } };
  const dd = RS.digests(RS.validateResilience(d, sh));
  assert.equal(dd.resilience_problem_digest, da.resilience_problem_digest); assert.notEqual(dd.resilience_scenario_digest, da.resilience_scenario_digest);
});

async function asyncTests() {
  const tA = async (name, fn) => { try { await fn(); t(name, () => {}); } catch (e) { t(name, () => { throw e; }); } };
  await tA("async = sync; event loop уступается; isCurrent", async () => {
    const env = RS.validateResilience(envOf(sh, "school", { nC: 12, budget: 1000, maxSel: 5 }), sh);
    let ticks = 0; const iv = setInterval(() => ticks++, 0);
    const a = await RS.optimizeResilienceAsync(sh, env, { chunk: 128, request_id: 9 });
    clearInterval(iv);
    assert.deepEqual(a, RS.optimizeResilience(sh, env, { request_id: 9 }));
    assert.ok(ticks > 3, String(ticks));
    assert.equal(RS.isCurrent(a, RS.digests(env).resilience_problem_digest, 9), true);
    assert.equal(RS.isCurrent(a, RS.digests(env).resilience_problem_digest, 10), false);
  });
  await tA("async: AbortController → cancelled, robust=null", async () => {
    const env = RS.validateResilience(envOf(sh, "school", { nC: 12, budget: 1000, maxSel: 5 }), sh);
    const ac = new AbortController();
    const r = await RS.optimizeResilienceAsync(sh, env, { chunk: 64, signal: ac.signal, onProgress: (p) => { if (p.examined >= 256) ac.abort(); } });
    assert.equal(r.status, "cancelled"); assert.equal(r.robust, null);
  });
}
asyncTests().then(() => {
  const pass = results.filter((x) => x.status === "PASS").length, fail = results.length - pass;
  console.log(`\n${pass} passed, ${fail} failed`);
  if (arg("--json")) fs.writeFileSync(arg("--json"), JSON.stringify({ app_root: APP, pass, fail, results }, null, 1) + "\n");
  process.exit(fail ? 1 : 0);
});
