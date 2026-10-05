/* Этап 2: три objective и Парето против наивного независимого перебора (через evaluatePlan + свой компаратор),
 * статусы optimal/infeasible/incomplete, progress, cancel (sync/async), чувствительность, защита от старого ответа.
 *   node tests/test_stage2.cjs --app-root <checkout>/prototypes/city-evidence [--json OUT]
 */
"use strict";
const assert = require("node:assert/strict");
const H = require("./helpers.cjs");
const { PL } = H;
const R = H.runner(), t = R.t;
const APP = H.arg("--app-root");
if (!APP) { console.error("нужен --app-root"); process.exit(2); }
const B = H.loadBuild(APP);

// ---------- наивный эталон: все подмножества через evaluatePlan, свой компаратор ----------
function subsets(ids) {
  const out = [];
  for (let m = 0; m < 1 << ids.length; m++) out.push(ids.filter((_, j) => m & (1 << j)));
  return out;
}
function naive(ctx, s) {
  const ids = s.candidates.map((c) => c.id).sort();
  const feas = subsets(ids).map((sub) => PL.evaluatePlan(ctx, s, sub)).filter((e) => e.feasibility.feasible);
  const big = (x) => (x === null ? Number.MAX_VALUE : x);
  const cmp = (a, b) => { for (let i = 0; i < a.length; i++) { const x = a[i], y = b[i];
    if (Array.isArray(x)) { const sx = x.join("\u0000"), sy = y.join("\u0000");
      // лексикографически по элементам, короче раньше
      for (let k = 0; k < Math.min(x.length, y.length); k++) if (x[k] !== y[k]) return x[k] < y[k] ? -1 : 1;
      if (x.length !== y.length) return x.length - y.length; void sx; void sy; continue; }
    if (x !== y) return x < y ? -1 : 1; } return 0; };
  const key = {
    mean: (e) => [e.metrics.unknown_count, e.metrics.weighted_sum_mm, big(e.metrics.max_mm), e.cost, e.plan_ids],
    minimax: (e) => [e.metrics.unknown_count, big(e.metrics.max_mm), e.metrics.weighted_sum_mm, e.cost, e.plan_ids],
    coverage: (e) => [-e.metrics.covered_weight, e.metrics.unknown_count, e.metrics.weighted_sum_mm, big(e.metrics.max_mm), e.cost, e.plan_ids],
  };
  const best = {};
  for (const o of Object.keys(key)) best[o] = feas.slice().sort((a, b) => cmp(key[o](a), key[o](b)))[0] || null;
  // Парето O(N²) по определению: недоминируемые среди полностью известных; равные пары — один с меньшими ids
  const known = feas.filter((e) => e.metrics.unknown_count === 0);
  const dom = (a, b) => a.cost <= b.cost && a.metrics.weighted_sum_mm <= b.metrics.weighted_sum_mm
    && (a.cost < b.cost || a.metrics.weighted_sum_mm < b.metrics.weighted_sum_mm);
  const nd = known.filter((b) => !known.some((a) => dom(a, b)));
  const groups = new Map();
  for (const e of nd) { const k = `${e.cost}|${e.metrics.weighted_sum_mm}`; const g = groups.get(k); if (!g || cmp([e.plan_ids], [g.plan_ids]) < 0) groups.set(k, e); }
  const pareto = Array.from(groups.values()).sort((a, b) => a.cost - b.cost);
  return { feasible_count: feas.length, best, pareto, known: known.length };
}
const V = (s, ctx) => { const v = PL.validatePlanScenario(s, ctx); if (!v.ok) throw new Error(JSON.stringify(v.error)); return v.scenario; };

const CASES = [];
for (const city of ["shymkent", "astana"]) for (const cat of ["school", "outpatient_clinic"]) for (const seed of [1, 2, 3])
  CASES.push({ city, cat, seed, nCand: 7 + seed, budget: 150 + 100 * seed, maxSel: 1 + seed, radius: 200 + 150 * seed,
    required: seed === 3 ? ["syn_c02"] : [], excluded: seed === 2 ? ["syn_c01"] : [] });

for (const c of CASES) {
  t(`${c.city}/${c.cat}/seed${c.seed}: objectives и Парето = наивный перебор`, () => {
    const ctx = H.buildContext(B, c.city);
    const s = V(H.syntheticScenario(ctx, c.cat, { seed: c.seed * 101 + c.city.length, nPoints: 12, nCand: c.nCand, budget: c.budget,
      maxSel: c.maxSel, radius: c.radius, required: c.required, excluded: c.excluded }), ctx);
    const r = PL.optimizePlans(ctx, s);
    const n = naive(ctx, s);
    assert.equal(r.status, "optimal");
    assert.equal(r.feasible_count, n.feasible_count);
    for (const o of ["mean", "minimax", "coverage"]) {
      assert.deepEqual(r.objectives[o].ids, n.best[o].plan_ids, o);
      assert.deepEqual(r.objectives[o].metrics, n.best[o].metrics, o);
    }
    assert.deepEqual(r.pareto.map((p) => [p.cost, p.weighted_sum_mm, p.ids]), n.pareto.map((e) => [e.cost, e.metrics.weighted_sum_mm, e.plan_ids]));
    assert.equal(r.pareto_excluded_partial, n.feasible_count - n.known);
  });
}

// ---------- Парето: свёртка равных пар, доминирование, unknown ----------
const eqCtx = { city_id: "astana", bbox: [0, -0.01, 0.1, 0.01], source_snapshot: "SYNTHETIC-eq", records: [{ id: "s", lon: 0, lat: 0, group: "school" }] };
const eqS = (over) => V({ schema_version: PL.SCHEMA, city_id: "astana", source_snapshot: "SYNTHETIC-eq", category: "school",
  control_points: [{ id: "p1", lon: 0.03, lat: 0, weight: 1 }],
  candidates: [{ id: "b", lon: 0.03, lat: 0, category: "school", kind: "hypothetical", cost: 10 },
    { id: "a", lon: 0.03, lat: 0, category: "school", kind: "hypothetical", cost: 10 },
    { id: "x", lon: 0.02, lat: 0, category: "school", kind: "hypothetical", cost: 5 }],
  budget: 100, max_selected: 2, coverage_radius_m: 100, required_ids: [], excluded_ids: [], selected_ids: [], ...over }, eqCtx);
t("Парето: равные (cost, sum) свёрнуты к меньшим ids; доминируемые убраны; отсортировано по cost", () => {
  const r = PL.optimizePlans(eqCtx, eqS());
  // {}: cost0 sum=3336 м; {x}: 5, 1112 м; {a}/{b}: 10, 0 → представитель ["a"]
  assert.deepEqual(r.pareto.map((p) => p.ids), [[], ["x"], ["a"]]);
  assert.ok(r.pareto.every((p, i) => i === 0 || p.cost > r.pareto[i - 1].cost));
  assert.ok(r.pareto.every((p, i) => i === 0 || p.weighted_sum_mm < r.pareto[i - 1].weighted_sum_mm));
});
t("Парето: при пустом baseline пустой план (unknown) не попадает, сумма по partial не сравнивается", () => {
  const ctx0 = { ...eqCtx, records: [] };
  const r = PL.optimizePlans(ctx0, V({ ...eqS(), source_snapshot: "SYNTHETIC-eq" }, ctx0));
  assert.ok(r.pareto.every((p) => p.metrics.unknown_count === 0 && p.ids.length > 0));
  assert.equal(r.pareto_excluded_partial, 1);
  assert.equal(r.objectives.mean.metrics.unknown_count, 0);
});
t("одинаковые планы разных целей помечены same_plan_as", () => {
  const r = PL.optimizePlans(eqCtx, eqS());
  assert.deepEqual(r.objectives.mean.ids, ["a"]);
  assert.deepEqual(r.same_plan_as.mean.sort(), ["coverage", "minimax"]);
});

// ---------- статусы, счётчики, progress, cancel ----------
const big = (seed = 5) => {
  const ctx = H.buildContext(B, "shymkent");
  return { ctx, s: V(H.syntheticScenario(ctx, "school", { seed, nPoints: 25, nCand: 16, budget: 600, maxSel: 5, radius: 300 }), ctx) };
};
t("optimal: evaluated = total = 2^16; progress монотонный и доходит до total", () => {
  const { ctx, s } = big();
  const seen = [];
  const r = PL.optimizePlans(ctx, s, { chunk: 5000, onProgress: (p) => seen.push(p.evaluated), sensitivity: false });
  assert.equal(r.status, "optimal"); assert.equal(r.total, 65536); assert.equal(r.evaluated, 65536);
  assert.ok(seen.every((x, i) => i === 0 || x > seen[i - 1])); assert.equal(seen[seen.length - 1], 65536);
});
t("incomplete (maxEvaluations): status≠optimal, objectives=null, best_so_far помечен, Парето не строится", () => {
  const { ctx, s } = big();
  const r = PL.optimizePlans(ctx, s, { maxEvaluations: 1000, sensitivity: false });
  assert.equal(r.status, "incomplete"); assert.equal(r.objectives, null); assert.equal(r.pareto, null);
  assert.ok(r.evaluated < r.total && r.best_so_far && r.best_so_far.mean);
});
t("cancel (sync shouldCancel): incomplete, canceled=true", () => {
  const { ctx, s } = big();
  let calls = 0;
  const r = PL.optimizePlans(ctx, s, { chunk: 1000, shouldCancel: () => ++calls > 3, sensitivity: false });
  assert.equal(r.status, "incomplete"); assert.equal(r.canceled, true); assert.equal(r.evaluated, 3000);
});
t("infeasible: required дороже бюджета → reasons, evaluated=0, objectives=null", () => {
  const { ctx, s } = big();
  const r = PL.optimizePlans(ctx, { ...s, required_ids: s.candidates.slice(0, 5).map((c) => c.id).sort(), budget: 1 });
  assert.equal(r.status, "infeasible"); assert.equal(r.evaluated, 0); assert.ok(r.reasons.length);
});
t("чувствительность: бюджеты [0, floor(B/2), B] без дублей; кандидаты/веса не меняются", () => {
  assert.deepEqual(PL.budgetsFor(0), [0]); assert.deepEqual(PL.budgetsFor(1), [0, 1]); assert.deepEqual(PL.budgetsFor(301), [0, 150, 301]);
  const r = PL.optimizePlans(eqCtx, eqS({ budget: 10 }));
  assert.deepEqual(r.sensitivity.map((x) => x.budget), [0, 5, 10]);
  assert.deepEqual(r.sensitivity[0].objectives.mean.ids, []);
  assert.deepEqual(r.sensitivity[1].objectives.mean.ids, ["x"]);
  assert.deepEqual(r.sensitivity[2].objectives.mean.ids, ["a"]);
  const r2 = PL.optimizePlans(eqCtx, eqS({ budget: 10, required_ids: ["a"] }));
  assert.equal(r2.sensitivity[0].status, "infeasible"); assert.equal(r2.sensitivity[2].status, "optimal");
});

// ---------- async ----------
async function asyncTests() {
  const tA = async (name, fn) => { try { await fn(); R.t(name, () => {}); } catch (e) { R.t(name, () => { throw e; }); } };
  await tA("async: результат совпадает с синхронным (включая чувствительность)", async () => {
    const { ctx, s } = big(6);
    const a = await PL.optimizePlansAsync(ctx, s, { chunk: 4096, request_id: "r1" });
    const b = PL.optimizePlans(ctx, s, { request_id: "r1" });
    assert.deepEqual(JSON.parse(PL.toStrictJSON(a)), JSON.parse(PL.toStrictJSON(b)));
  });
  await tA("async: event loop не блокируется (таймер срабатывает во время поиска)", async () => {
    const { ctx, s } = big(7);
    let ticks = 0; const iv = setInterval(() => ticks++, 0);
    await PL.optimizePlansAsync(ctx, s, { chunk: 1024 });
    clearInterval(iv);
    assert.ok(ticks > 5, `таймер сработал ${ticks} раз`);
  });
  await tA("async: AbortController отменяет — incomplete, objectives=null", async () => {
    const { ctx, s } = big(8);
    const ac = new AbortController();
    const p = PL.optimizePlansAsync(ctx, s, { chunk: 512, signal: ac.signal, onProgress: (x) => { if (x.evaluated >= 2048) ac.abort(); } });
    const r = await p;
    assert.equal(r.status, "incomplete"); assert.equal(r.canceled, true); assert.equal(r.objectives, null);
  });
  await tA("isCurrent: старый ответ отвергается после смены задачи или request_id", async () => {
    const { ctx, s } = big(9);
    const r = await PL.optimizePlansAsync(ctx, s, { request_id: 7, sensitivity: false });
    assert.equal(PL.isCurrent(r, PL.problemDigest(s), 7), true);
    assert.equal(PL.isCurrent(r, PL.problemDigest(s), 8), false);
    assert.equal(PL.isCurrent(r, PL.problemDigest({ ...s, budget: s.budget - 1 }), 7), false);
  });
}

asyncTests().then(() => process.exit(R.done(H.arg("--json"))));
