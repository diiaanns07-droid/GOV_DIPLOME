/* K05 r9 этап 1: адаптер задач r8 (research/round-8-results/K05) к НАСТОЯЩЕМУ web/plan.js сборки.
 * Не новый движок: вызывает только API сборки (makeContext, validatePlanScenario, optimizePlans, sensitivity, evaluatePlan).
 *
 *   node adapter_r8_vs_build.cjs --app-root <checkout>/prototypes/city-evidence --cases <r8 cases_dump.json>
 *        [--json OUT] [--oracle-dump OUT2]
 * --oracle-dump пишет ответы СБОРКИ в формате r8 oracle.py (context/scenario/result) для независимой проверки Python-оракулом.
 */
"use strict";
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const assert = require("node:assert/strict");
const argv = process.argv.slice(2), arg = (k) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : null);
const APP = arg("--app-root"), CASES = arg("--cases");
if (!APP || !CASES) { console.error("нужны --app-root и --cases"); process.exit(2); }
const W = path.join(APP, "web");
const sb = {}; vm.createContext(sb); sb.window = sb;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), sb, { filename: f });
const F = require(path.join(W, "facts.js"));
const PL = require(path.join(W, "plan.js"));
const D = sb.CITY_EVIDENCE;

const results = [];
const check = (name, fn) => {
  try { fn(); results.push({ name, status: "PASS" }); console.log("PASS", name); }
  catch (e) { results.push({ name, status: "FAIL", error: String(e.message || e).slice(0, 600) }); console.log("FAIL", name, "—", String(e.message || e).slice(0, 300)); }
};

// ---------- контекст сборки для задачи r8 ----------
function buildCtx(c) {
  const city = c.context.city_id;
  const real = D.cities[city] && c.context.bbox.join() === D.cities[city].bbox.join() && !/^SYNTHETIC/.test(c.context.source_snapshot);
  if (real) {
    const ctx = PL.makeContext(D, city, F);
    // записи категории в сборке должны совпасть с записями задачи r8 (id, lon, lat)
    const k = (arr) => arr.filter((p) => p.group === c.scenario.category).map((p) => [p.id, p.lon, p.lat]).sort().join("|");
    assert.equal(k(ctx.places), k(c.context.records), "записи среза сборки ≠ записи задачи r8");
    return { ctx, kind: "real" };
  }
  const name = "synthetic-" + c.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  const data = { cities: { [name]: { bbox: c.context.bbox, release: "synthetic", files: {},
    places: c.context.records.map((r) => ({ id: r.id, group: r.group, lon: r.lon, lat: r.lat, name: null })) } } };
  return { ctx: PL.makeContext(data, name, F), kind: "synthetic" };
}
function buildScenario(c, ctx, perm) {
  const s = c.scenario;
  const order = (a) => (perm ? a.slice().reverse() : a.slice());
  return PL.validatePlanScenario({ schema_version: PL.SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, category: s.category,
    control_points: order(s.control_points), candidates: order(s.candidates), budget: s.budget, max_selected: s.max_selected,
    coverage_radius_m: s.coverage_radius_m, required_ids: order(s.required_ids), excluded_ids: order(s.excluded_ids), selected_ids: order(s.selected_ids) }, ctx);
}
// ответ сборки → формат r8 (для сравнения и для oracle.py)
function toR8(r, sens) {
  const status = r.status;
  const obj = r.objectives ? Object.fromEntries(Object.entries(r.objectives).map(([k, o]) => [k, { ids: o.ids, cost: o.cost,
    metrics: { unknown_count: o.unknown_count, weighted_sum_mm: o.weighted_sum_mm, max_mm: o.max_mm, covered_weight: o.covered_weight, cost: o.cost } }])) : null;
  return { status, feasible_count: r.feasible_count, objectives: obj, pareto: (r.pareto || []).map((p) => ({ ids: p.ids, cost: p.cost, weighted_sum_mm: p.weighted_sum_mm })),
    pareto_excluded_partial: r.status === "optimal" ? r.pareto_excluded_unknown : null,
    sensitivity: sens ? sens.map((x) => ({ budget: x.budget, status: x.status, objectives: x.objectives ? Object.fromEntries(Object.entries(x.objectives).map(([k, o]) => [k, { ids: o.ids }])) : null })) : null };
}

const cases = JSON.parse(fs.readFileSync(CASES, "utf8"));
const oracleDump = [];
for (const c of cases) {
  check(`r8→BUILD ${c.name}: статус, допустимые, 3 оптимума, Парето, чувствительность`, () => {
    const { ctx, kind } = buildCtx(c);
    const sc = buildScenario(c, ctx, false);
    const r = PL.optimizePlans(ctx, sc, { F });
    const sens = PL.sensitivity(ctx, sc, { F });
    const got = toR8(r, sens), want = c.result;
    assert.equal(got.status, want.status, "status");
    if (want.status === "optimal") {
      assert.equal(got.feasible_count, want.feasible_count, "feasible_count");
      for (const o of ["mean", "minimax", "coverage"]) {
        assert.deepEqual(got.objectives[o].ids, want.objectives[o].ids, `${o}.ids`);
        for (const m of ["unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost"])
          assert.equal(got.objectives[o].metrics[m], want.objectives[o].metrics[m], `${o}.${m}`);
      }
      assert.deepEqual(got.pareto.map((p) => [p.cost, p.weighted_sum_mm, p.ids]), want.pareto.map((p) => [p.cost, p.weighted_sum_mm, p.ids]), "pareto");
      assert.equal(got.pareto_excluded_partial, want.pareto_excluded_partial, "pareto_excluded");
      assert.deepEqual(got.sensitivity.map((x) => [x.budget, x.status, x.objectives && x.objectives.mean.ids]),
        want.sensitivity.map((x) => [x.budget, x.status, x.objectives && x.objectives.mean.ids]), "sensitivity");
    }
    // перестановка входных массивов не меняет ответ сборки
    const r2 = PL.optimizePlans(ctx, buildScenario(c, ctx, true), { F });
    assert.deepEqual(toR8(r2, null).objectives, got.objectives, "перестановка");
    assert.equal(r2.problem_digest, r.problem_digest, "problem_digest от порядка");
    oracleDump.push({ name: `BUILD:${c.name}`, kind, context: { city_id: ctx.city_id, bbox: ctx.bbox, source_snapshot: ctx.source_snapshot,
      records: ctx.places.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, group: p.group })) }, scenario: sc, result: got });
  });
}

// ---------- ручные проверки: три оптимума, tie-break, пустой план (synthetic экватор, как r8 stage1) ----------
const RAD = Math.PI / 180, eqMm = (d) => Math.round(6371008.8 * Math.abs(d) * RAD * 1000);
function eqCtx(places) {
  return PL.makeContext({ cities: { "synthetic-eq": { bbox: [0, -0.01, 0.1, 0.01], release: "synthetic", files: {}, places } } }, "synthetic-eq", F);
}
const eqPlaces = [{ id: "src_a", group: "school", lon: 0, lat: 0, name: null }];
function eqSc(ctx, over) {
  return PL.validatePlanScenario({ schema_version: PL.SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, category: "school",
    control_points: [{ id: "p1", lon: 0.010, lat: 0, weight: 1 }, { id: "p2", lon: 0.020, lat: 0, weight: 2 }, { id: "p3", lon: 0.050, lat: 0, weight: 1 }],
    candidates: [{ id: "c_near2", lon: 0.021, lat: 0, category: "school", kind: "hypothetical", cost: 100 },
      { id: "c_far", lon: 0.050, lat: 0, category: "school", kind: "hypothetical", cost: 300 },
      { id: "c_mid", lon: 0.035, lat: 0, category: "school", kind: "hypothetical", cost: 150 }],
    budget: 300, max_selected: 2, coverage_radius_m: 1500, required_ids: [], excluded_ids: [], selected_ids: [], ...over }, ctx);
}
check("экватор: три оптимума = ручной расчёт r8 (c_mid+c_near2; feasible 5 из 8)", () => {
  const ctx = eqCtx(eqPlaces), r = PL.optimizePlans(ctx, eqSc(ctx), { F });
  assert.equal(r.status, "optimal"); assert.equal(r.total_subsets, 8); assert.equal(r.feasible_count, 5);
  assert.deepEqual(r.objectives.mean.ids, ["c_mid", "c_near2"]);
  assert.equal(r.objectives.mean.weighted_sum_mm, eqMm(0.01) + 2 * eqMm(0.001) + eqMm(0.015));
  assert.deepEqual(r.objectives.minimax.ids, ["c_mid", "c_near2"]); assert.equal(r.objectives.minimax.max_mm, eqMm(0.015));
});
check("tie-break: источник выигрывает у кандидата на том же расстоянии; среди кандидатов — меньший id; оптимизатор → [aa]", () => {
  const ctx = eqCtx(eqPlaces);
  const same0 = eqSc(ctx, { candidates: [{ id: "zz", lon: 0, lat: 0, category: "school", kind: "hypothetical", cost: 1 },
    { id: "aa", lon: 0, lat: 0, category: "school", kind: "hypothetical", cost: 1 }], budget: 10 });
  const e0 = PL.evaluatePlan(ctx, same0, ["zz", "aa"]);
  assert.deepEqual(e0.rows[0].nearest_after, { kind: "source", id: "src_a" });
  const s2 = eqSc(ctx, { candidates: [{ id: "zz", lon: 0.02, lat: 0, category: "school", kind: "hypothetical", cost: 1 },
    { id: "aa", lon: 0.02, lat: 0, category: "school", kind: "hypothetical", cost: 1 }], budget: 10 });
  assert.deepEqual(PL.evaluatePlan(ctx, s2, ["zz", "aa"]).rows[1].nearest_after, { kind: "hypothetical", id: "aa" });
  assert.deepEqual(PL.optimizePlans(ctx, s2, { F }).objectives.mean.ids, ["aa"]);
});
check("пустой план: при max_selected=0 и budget=0 единственный допустимый; при пустом baseline unknown=все точки и не выбирается", () => {
  const ctx = eqCtx(eqPlaces);
  const r0 = PL.optimizePlans(ctx, eqSc(ctx, { max_selected: 0 }), { F });
  assert.deepEqual(r0.objectives.mean.ids, []); assert.equal(r0.feasible_count, 1);
  const rb = PL.optimizePlans(ctx, eqSc(ctx, { budget: 0 }), { F });
  assert.deepEqual(rb.objectives.coverage.ids, []);
  const ctxE = eqCtx([]);
  const sE = eqSc(ctxE);
  const ev = PL.evaluatePlan(ctxE, sE, []);
  assert.equal(ev.metrics.unknown_count, 3); assert.equal(ev.metrics.max_mm, null); assert.equal(ev.metrics.weighted_mean_mm, null);
  assert.ok(ev.rows.every((x) => x.after_mm === null && x.delta_mm === null));
  const rE = PL.optimizePlans(ctxE, sE, { F });
  assert.notDeepEqual(rE.objectives.mean.ids, []); assert.equal(rE.objectives.mean.unknown_count, 0);
  assert.equal(rE.pareto_excluded_unknown, 1);
});

const pass = results.filter((x) => x.status === "PASS").length, fail = results.length - pass;
console.log(`\n${pass} passed, ${fail} failed`);
if (arg("--json")) fs.writeFileSync(arg("--json"), JSON.stringify({ app_root: APP, cases: CASES, pass, fail, results }, null, 1) + "\n");
if (arg("--oracle-dump")) fs.writeFileSync(arg("--oracle-dump"), JSON.stringify(oracleDump) + "\n");
process.exit(fail ? 1 : 0);
