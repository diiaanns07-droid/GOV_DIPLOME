/* K05 r9 этап 3: gold-примеры, свойства, собственный перебор через PL.evaluatePlan (независимо от lossOf модуля), benchmark.
 *   node tests/test_stage3.cjs --app-root <checkout>/prototypes/city-evidence [--json OUT] [--bench OUT]
 * Тест модуля K05 на API сборки, не тест интегрированной функции BUILD.
 */
"use strict";
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm"), os = require("node:os");
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
const Lv = (w) => [w.unknown_count, w.weighted_sum_mm, w.max_mm === null ? Infinity : w.max_mm];
const cmpL = (a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] === b[2] ? 0 : a[2] < b[2] ? -1 : 1);

// ---------- gold: экватор, ручной расчёт (d = R·Δλ) ----------
const RAD = Math.PI / 180, mm = (d) => Math.round(6371008.8 * Math.abs(d) * RAD * 1000);
function eqCtx(places) {
  return PL.makeContext({ cities: { "synthetic-eq": { bbox: [0, -0.01, 0.1, 0.01], release: "synthetic", files: {}, places } } }, "synthetic-eq", F);
}
const P = (id, lon) => ({ id, group: "school", lon, lat: 0, name: null });
const C = (id, lon, cost = 1) => ({ id, lon, lat: 0, category: "school", kind: "hypothetical", cost });
function eqEnv(ctx, plan, cases) {
  return { schema_version: RS.SCHEMA, plan: { schema_version: PL.SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, category: "school",
    required_ids: [], excluded_ids: [], selected_ids: [], coverage_radius_m: 100, ...plan }, cases };
}
t("gold 1: обычный (A) ≠ устойчивый (B); W, worst_case_ids и цена — замкнутые формулы", () => {
  // источники s0@0, s1@0.051; точки p1@0.05 (вес 3), p2@0.1 (вес 1); кандидаты A@0.1, B@0.05; бюджет 1, ≤1; случай x: без s1.
  // base: A → p1 d(0.001), p2 0 → сумма 3·d001; B → p1 0, p2 d(0.049) (s1 ближе B) → d049. nominal = A.
  // x: A → p1 min(s0 0.05, A 0.05) = d05 (ничья, источник), p2 0 → (0, 3·d05, d05); B → p1 0, p2 min(s0 0.1, B 0.05) = d05 → (0, d05, d05).
  // худший у обоих — x; W(B) < W(A) → robust = B. Цена = (d049/4 − 3·d001/4)/1000 м (сумма весов 4).
  const ctx = eqCtx([P("s0", 0), P("s1", 0.051)]);
  const env = RS.validateResilience(eqEnv(ctx, { control_points: [{ id: "p1", lon: 0.05, lat: 0, weight: 3 }, { id: "p2", lon: 0.1, lat: 0, weight: 1 }],
    candidates: [C("A", 0.1), C("B", 0.05)], budget: 1, max_selected: 1 }, [{ id: "x", label: "SYNTHETIC: без s1", disabled_source_ids: ["s1"] }]), ctx);
  const r = RS.optimizeResilience(ctx, env);
  assert.equal(r.status, "optimal"); assert.equal(r.feasible_count, 3);
  assert.deepEqual(r.nominal.selected_ids, ["A"]); assert.deepEqual(r.robust.selected_ids, ["B"]); assert.equal(r.same_plan, false);
  assert.deepEqual(Lv(r.nominal.worst_vector), [0, 3 * mm(0.05), mm(0.05)]);
  assert.deepEqual(Lv(r.robust.worst_vector), [0, mm(0.05), mm(0.05)]);
  assert.deepEqual(r.robust.worst_case_ids, ["x"]); assert.deepEqual(r.nominal.worst_case_ids, ["x"]);
  assert.equal(r.price_of_resilience_m, (mm(0.049) / 4 - 3 * mm(0.001) / 4) / 1000);
});
t("gold 2: исключены все записи → unknown в случае; пустой план худший, устойчивый выбирает объект", () => {
  const ctx = eqCtx([P("s0", 0)]);
  const env = RS.validateResilience(eqEnv(ctx, { control_points: [{ id: "p1", lon: 0.02, lat: 0, weight: 2 }],
    candidates: [C("A", 0.03)], budget: 1, max_selected: 1 }, [{ id: "none", label: "SYNTHETIC: все записи", disabled_source_ids: ["s0"] }]), ctx);
  const e0 = RS.evaluateResilience(ctx, env, []);
  assert.deepEqual(e0.worst_vector, { unknown_count: 1, weighted_sum_mm: 0, max_mm: null }); assert.deepEqual(e0.worst_case_ids, ["none"]);
  assert.equal(e0.per_case[1].metrics.weighted_mean_mm, null); assert.equal(e0.per_case[1].rows[0].delta_mm, null);
  const r = RS.optimizeResilience(ctx, env);
  assert.deepEqual(r.robust.selected_ids, ["A"]);
  // W(A) = max(base: d(0.01)·2 → ближе s0 (0.02) чем A (0.01)? A ближе: d(0.01); none: d(0.01)) — равные L → оба худшие
  assert.deepEqual(r.robust.worst_case_ids, ["base", "none"]);
});
t("gold 3: 0 кандидатов → один план (пустой), nominal = robust, цена 0", () => {
  const ctx = eqCtx([P("s0", 0), P("s1", 0.05)]);
  const env = RS.validateResilience(eqEnv(ctx, { control_points: [{ id: "p1", lon: 0.04, lat: 0, weight: 1 }], candidates: [], budget: 0, max_selected: 0 },
    [{ id: "x", label: "SYNTHETIC", disabled_source_ids: ["s1"] }]), ctx);
  const r = RS.optimizeResilience(ctx, env);
  assert.equal(r.total_subsets, 1); assert.deepEqual(r.robust.selected_ids, []); assert.equal(r.same_plan, true); assert.equal(r.price_of_resilience_m, 0);
});
t("gold 4: required невыполним → infeasible; required выполним → он в обоих планах", () => {
  const ctx = eqCtx([P("s0", 0)]);
  const base = { control_points: [{ id: "p1", lon: 0.04, lat: 0, weight: 1 }], candidates: [C("A", 0.04, 5), C("B", 0.03, 1)], max_selected: 1 };
  const cases = [{ id: "x", label: "SYNTHETIC", disabled_source_ids: ["s0"] }];
  const r1 = RS.optimizeResilience(ctx, RS.validateResilience(eqEnv(ctx, { ...base, budget: 4, required_ids: ["A"] }, cases), ctx));
  assert.equal(r1.status, "infeasible"); assert.equal(r1.robust, null);
  const r2 = RS.optimizeResilience(ctx, RS.validateResilience(eqEnv(ctx, { ...base, budget: 5, required_ids: ["A"] }, cases), ctx));
  assert.deepEqual(r2.robust.selected_ids, ["A"]); assert.deepEqual(r2.nominal.selected_ids, ["A"]);
});

// ---------- реальные срезы: синтетические точки/кандидаты/случаи ----------
function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let x = a; x = Math.imul(x ^ (x >>> 15), x | 1); x ^= x + Math.imul(x ^ (x >>> 7), x | 61); return ((x ^ (x >>> 14)) >>> 0) / 4294967296; }; }
function realEnv(city, cat, seed, { nP = 10, nC = 8, nCases = 3, maxSel = 3, budget = 400 } = {}) {
  const ctx = PL.makeContext(D, city, F), r = rng(seed), b = ctx.bbox, at = () => [b[0] + (b[2] - b[0]) * r(), b[1] + (b[3] - b[1]) * r()];
  const src = ctx.places.filter((p) => p.group === cat).map((p) => p.id).sort();
  const cases = Array.from({ length: nCases }, (_, k) => {
    const n = 1 + Math.floor(r() * Math.min(4, src.length)), pick = new Set();
    while (pick.size < n) pick.add(src[Math.floor(r() * src.length)]);
    return { id: `syn_case${k}`, label: `SYNTHETIC исключение ${k}`, disabled_source_ids: [...pick] };
  });
  const plan = { schema_version: PL.SCHEMA, city_id: city, source_snapshot: ctx.source_snapshot, category: cat,
    control_points: Array.from({ length: nP }, (_, i) => { const [lon, lat] = at(); return { id: `syn_p${i}`, lon, lat, weight: 1 + Math.floor(r() * 5) }; }),
    candidates: Array.from({ length: nC }, (_, i) => { const [lon, lat] = at(); return { id: `syn_c${String(i).padStart(2, "0")}`, lon, lat, category: cat, kind: "hypothetical", cost: 50 + Math.floor(r() * 150) }; }),
    budget, max_selected: maxSel, coverage_radius_m: 400, required_ids: [], excluded_ids: [], selected_ids: [] };
  return { ctx, raw: { schema_version: RS.SCHEMA, plan, cases } };
}
// собственный перебор: W плана через PL.evaluatePlan на отфильтрованных контекстах (не через lossOf модуля)
function bruteRobust(ctx, env) {
  const sc = env.plan, all = [{ id: "base", d: [] }, ...env.cases.map((c) => ({ id: c.id, d: c.disabled_source_ids }))];
  const ctxs = all.map((c) => ({ ...ctx, places: ctx.places.filter((p) => !c.d.includes(p.id)) }));
  const ids = sc.candidates.map((c) => c.id).sort();
  let best = null;
  for (let m = 0; m < 1 << ids.length; m++) {
    const sel = ids.filter((_, j) => m & (1 << j));
    if (!PL.feasibility(sc, sel).feasible) continue;
    const Ls = ctxs.map((cc) => { const e = PL.evaluatePlan(cc, sc, sel); return [e.metrics.unknown_count, e.metrics.weighted_sum_mm, e.metrics.max_mm === null ? Infinity : e.metrics.max_mm]; });
    const Wv = Ls.reduce((a, x) => (cmpL(x, a) > 0 ? x : a));
    const cost = PL.feasibility(sc, sel).cost;
    const key = [Wv, Ls[0], cost, sel];
    const lt = (a, b) => { let c = cmpL(a[0], b[0]); if (c) return c < 0; c = cmpL(a[1], b[1]); if (c) return c < 0; if (a[2] !== b[2]) return a[2] < b[2];
      for (let i = 0; i < Math.min(a[3].length, b[3].length); i++) if (a[3][i] !== b[3][i]) return a[3][i] < b[3][i]; return a[3].length < b[3].length; };
    if (!best || lt(key, best)) best = key;
  }
  return best;
}
let caseNo = 0;
for (const city of ["shymkent", "astana"]) for (const cat of ["school", "outpatient_clinic"]) for (const seed of [11, 12]) {
  t(`${city}/${cat}/seed${seed}: robust = собственный перебор через PL.evaluatePlan; evaluate(robust).W = W`, () => {
    const { ctx, raw } = realEnv(city, cat, seed + caseNo++);
    const env = RS.validateResilience(raw, ctx), r = RS.optimizeResilience(ctx, env), b = bruteRobust(ctx, env);
    assert.deepEqual(r.robust.selected_ids, b[3]); assert.deepEqual(Lv(r.robust.worst_vector), b[0]);
    assert.deepEqual(RS.evaluateResilience(ctx, env, r.robust.selected_ids).worst_vector, r.robust.worst_vector);
  });
}

// ---------- свойства ----------
const { ctx: pc, raw: praw } = realEnv("shymkent", "school", 77, { nC: 9, nCases: 4 });
const penv = RS.validateResilience(praw, pc), pres = RS.optimizeResilience(pc, penv);
const core = (r) => ({ robust: r.robust.selected_ids, W: r.robust.worst_vector, worst: r.robust.worst_case_ids, nominal: r.nominal.selected_ids, price: r.price_of_resilience_m });
t("перестановка случаев, исключений, точек и кандидатов не меняет результат и digest", () => {
  const p2 = { ...praw, cases: praw.cases.slice().reverse().map((c) => ({ ...c, disabled_source_ids: c.disabled_source_ids.slice().reverse() })),
    plan: { ...praw.plan, control_points: praw.plan.control_points.slice().reverse(), candidates: praw.plan.candidates.slice().reverse() } };
  const e2 = RS.validateResilience(p2, pc), r2 = RS.optimizeResilience(pc, e2);
  assert.deepEqual(core(r2), core(pres)); assert.equal(r2.resilience_problem_digest, pres.resilience_problem_digest);
});
t("дубль случая не меняет выбор, W и цену; дубль попадает в worst_case_ids, только если оригинал худший", () => {
  const c0 = praw.cases[0];
  const e2 = RS.validateResilience({ ...praw, cases: [...praw.cases, { ...c0, id: "dup_of_0", label: "дубль" }] }, pc), r2 = RS.optimizeResilience(pc, e2);
  assert.deepEqual(r2.robust.selected_ids, pres.robust.selected_ids); assert.deepEqual(r2.robust.worst_vector, pres.robust.worst_vector);
  assert.equal(r2.price_of_resilience_m, pres.price_of_resilience_m);
  assert.equal(r2.robust.worst_case_ids.includes("dup_of_0"), pres.robust.worst_case_ids.includes(c0.id));
});
t("супермножество исключений: потери любого плана не меньше (лексикографически)", () => {
  const src = pc.places.filter((p) => p.group === "school").map((p) => p.id).sort();
  const env = RS.validateResilience({ ...praw, cases: [{ id: "sub", label: "SYNTHETIC sub", disabled_source_ids: src.slice(0, 2) },
    { id: "sup", label: "SYNTHETIC sup", disabled_source_ids: src.slice(0, 6) }] }, pc);
  const ids = env.plan.candidates.map((c) => c.id).sort();
  for (let m = 0; m < 1 << ids.length; m += 7) {
    const e = RS.evaluateResilience(pc, env, ids.filter((_, j) => m & (1 << j)));
    const L = Object.fromEntries(e.per_case.map((x) => [x.case_id, Lv(x.loss)]));
    assert.ok(cmpL(L.sup, L.sub) >= 0 && cmpL(L.sub, L.base) >= 0);
  }
});
t("добавление случая не улучшает минимальный W; nominal не меняется", () => {
  const e2 = RS.validateResilience({ ...praw, cases: praw.cases.slice(0, 2) }, pc), r2 = RS.optimizeResilience(pc, e2);
  assert.ok(cmpL(Lv(pres.robust.worst_vector), Lv(r2.robust.worst_vector)) >= 0);
  assert.deepEqual(pres.nominal.selected_ids, r2.nominal.selected_ids);
});
t("robust: W ≤ W(nominal), L_base ≥ L_base(nominal), цена ≥ 0", () => {
  assert.ok(cmpL(Lv(pres.robust.worst_vector), Lv(pres.nominal.worst_vector)) <= 0);
  assert.ok(cmpL(Lv(pres.robust.per_case[0].loss), Lv(pres.nominal.per_case[0].loss)) >= 0);
  assert.ok(pres.price_of_resilience_m >= 0);
});

// ---------- benchmark: 12 кандидатов × 25 точек × 8 случаев, ≤5 ----------
async function bench() {
  const rows = [];
  for (const city of ["shymkent", "astana"]) for (const cat of ["school", "outpatient_clinic"]) {
    const { ctx, raw } = realEnv(city, cat, 2026, { nP: 25, nC: 12, nCases: 7, maxSel: 5, budget: 1000000 });
    const env = RS.validateResilience(raw, ctx);
    const times = [];
    let res;
    for (let i = 0; i < 5; i++) { const t0 = process.hrtime.bigint(); res = RS.optimizeResilience(ctx, env); times.push(Number(process.hrtime.bigint() - t0) / 1e6); }
    let last = process.hrtime.bigint(), maxGap = 0;
    const ar = await RS.optimizeResilienceAsync(ctx, env, { chunk: 256, onProgress: () => { const x = process.hrtime.bigint(); maxGap = Math.max(maxGap, Number(x - last) / 1e6); last = x; } });
    rows.push({ city, category: cat, candidates: 12, points: 25, cases_total: 8, max_selected: 5, total_subsets: res.total_subsets, feasible_count: res.feasible_count,
      sync_ms_median: +times.sort((a, b) => a - b)[2].toFixed(1), async_max_chunk_ms_256: +maxGap.toFixed(2), async_equals_sync: JSON.stringify(ar) === JSON.stringify(res) });
  }
  return { node: process.version, cpu: (os.cpus()[0] || {}).model, cores: os.cpus().length, rows };
}

bench().then((b) => {
  t("benchmark: 4 конфигурации завершены, async = sync", () => { assert.ok(b.rows.every((r) => r.async_equals_sync && r.total_subsets === 4096)); });
  console.log(JSON.stringify(b.rows.map((r) => [r.city, r.category, r.sync_ms_median, r.async_max_chunk_ms_256])));
  if (arg("--bench")) fs.writeFileSync(arg("--bench"), JSON.stringify(b, null, 1) + "\n");
  const pass = results.filter((x) => x.status === "PASS").length, fail = results.length - pass;
  console.log(`\n${pass} passed, ${fail} failed`);
  if (arg("--json")) fs.writeFileSync(arg("--json"), JSON.stringify({ app_root: APP, pass, fail, results }, null, 1) + "\n");
  process.exit(fail ? 1 : 0);
});
