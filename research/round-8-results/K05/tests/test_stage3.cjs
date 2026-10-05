/* Этап 3: краевые случаи city-plan-v2.
 *   node tests/test_stage3.cjs --app-root <checkout>/prototypes/city-evidence [--json OUT]
 */
"use strict";
const assert = require("node:assert/strict");
const H = require("./helpers.cjs");
const { PL } = H;
const R = H.runner(), t = R.t;
const APP = H.arg("--app-root");
if (!APP) { console.error("нужен --app-root"); process.exit(2); }
const B = H.loadBuild(APP);

const RAD = Math.PI / 180, eqMm = (d) => Math.round(PL.R_EARTH_M * Math.abs(d) * RAD * 1000);
const ctxEq = { city_id: "shymkent", bbox: [0, -0.01, 0.1, 0.01], source_snapshot: "SYNTHETIC-eq3",
  records: [{ id: "dup_id", lon: 0, lat: 0, group: "school" }, { id: "clinic0", lon: 0.1, lat: 0, group: "outpatient_clinic" }] };
const base = (over) => ({ schema_version: PL.SCHEMA, city_id: "shymkent", source_snapshot: "SYNTHETIC-eq3", category: "school",
  control_points: [{ id: "p1", lon: 0.01, lat: 0, weight: 1 }], candidates: [], budget: 0, max_selected: 0, coverage_radius_m: 100,
  required_ids: [], excluded_ids: [], selected_ids: [], ...over });
const V = (s, ctx = ctxEq) => { const v = PL.validatePlanScenario(s, ctx); if (!v.ok) throw new Error(JSON.stringify(v.error)); return v.scenario; };
const C = (id, lon, cost, extra = {}) => ({ id, lon, lat: 0, category: "school", kind: "hypothetical", cost, ...extra });

t("0 кандидатов: total=1, единственный план — пустой, Парето из одного пустого", () => {
  const r = PL.optimizePlans(ctxEq, V(base()));
  assert.equal(r.status, "optimal"); assert.equal(r.total, 1); assert.equal(r.feasible_count, 1);
  assert.deepEqual(r.objectives.mean.ids, []); assert.deepEqual(r.pareto.map((p) => p.ids), [[]]);
});
t("max_selected=0 при непустом required → infeasible", () => {
  const r = PL.optimizePlans(ctxEq, V(base({ candidates: [C("a", 0.02, 1)], required_ids: ["a"], budget: 10 })));
  assert.equal(r.status, "infeasible"); assert.ok(r.reasons[0].includes("max_selected"));
});
t("все кандидаты excluded → только пустой план", () => {
  const r = PL.optimizePlans(ctxEq, V(base({ candidates: [C("a", 0.01, 1), C("b", 0.02, 1)], excluded_ids: ["a", "b"], budget: 10, max_selected: 2 })));
  assert.equal(r.feasible_count, 1); assert.deepEqual(r.objectives.coverage.ids, []);
});
t("id кандидата совпадает с id исходной записи: пространства source/candidate различаются", () => {
  const s = V(base({ candidates: [C("dup_id", 0.01, 1)], budget: 1, max_selected: 1 }));
  const e0 = PL.evaluatePlan(ctxEq, s, []), e1 = PL.evaluatePlan(ctxEq, s, ["dup_id"]);
  assert.deepEqual(e0.rows[0].after_ref, { ns: "source", id: "dup_id", kind: "observed_secondary" });
  assert.deepEqual(e1.rows[0].after_ref, { ns: "candidate", id: "dup_id", kind: "hypothetical" });
  assert.equal(e1.rows[0].after_mm, 0); assert.equal(e1.rows[0].covered, true);
});
t("точки и кандидаты на границе bbox принимаются (включительно)", () => {
  const s = base({ control_points: [{ id: "edge", lon: 0, lat: -0.01, weight: 1 }, { id: "edge2", lon: 0.1, lat: 0.01, weight: 1 }],
    candidates: [C("c", 0.1, 1, { lat: -0.01 })], budget: 1, max_selected: 1 });
  assert.equal(PL.validatePlanScenario(s, ctxEq).ok, true);
});
t("покрытие: covered ⇔ after_mm ≤ radius·1000 для всех строк (свойство на реальном срезе)", () => {
  const ctx = H.buildContext(B, "astana");
  for (const radius of [100, 250, 1000, 5000]) {
    const s = V(H.syntheticScenario(ctx, "school", { seed: radius, nPoints: 25, nCand: 8, budget: 500, maxSel: 4, radius }), ctx);
    const r = PL.optimizePlans(ctx, s, { sensitivity: false });
    for (const o of ["mean", "minimax", "coverage"]) {
      const e = PL.evaluatePlan(ctx, s, r.objectives[o].ids);
      for (const row of e.rows) assert.equal(row.covered, row.after_mm !== null && row.after_mm <= radius * 1000);
      assert.equal(e.metrics.covered_weight, e.rows.filter((x) => x.covered).reduce((a, x) => a + x.weight, 0));
    }
  }
});
t("mean и minimax различаются на ручном примере; same_plan_as пуст для них", () => {
  // p_heavy (вес 10) у 0.02, p_far (вес 1) у 0.09; база в 0. Один кандидат: A у 0.02 (сумма) или F у 0.09 (максимум).
  const s = V(base({ control_points: [{ id: "p_heavy", lon: 0.02, lat: 0, weight: 10 }, { id: "p_far", lon: 0.09, lat: 0, weight: 1 }],
    candidates: [C("A", 0.02, 1), C("F", 0.09, 1)], budget: 1, max_selected: 1, coverage_radius_m: 100 }));
  const r = PL.optimizePlans(ctxEq, s);
  // A: сумма = 0 + 1·d(0.09) ; F: сумма = 10·d(0.02) + 0 → A меньше сумма; максимум A = d(0.09) > максимум F = d(0.02)
  assert.ok(eqMm(0.09) < 10 * eqMm(0.02));
  assert.deepEqual(r.objectives.mean.ids, ["A"]); assert.deepEqual(r.objectives.minimax.ids, ["F"]);
  assert.ok(!r.same_plan_as.mean.includes("minimax"));
});
t("coverage предпочитает больший покрытый вес даже при большей сумме расстояний", () => {
  // радиус 100 м: A стоит на точке веса 3 (у 0.05); B — в центре группы из четырёх точек веса 1 (у 0.0021..0.0025),
  // которые ближе всего к базе в 0 (≈230–280 м, вне радиуса). B покрывает вес 4, A — 3; но сумма у A меньше.
  const s = V(base({ control_points: [{ id: "w3", lon: 0.05, lat: 0, weight: 3 }, { id: "a1", lon: 0.0021, lat: 0, weight: 1 },
    { id: "a2", lon: 0.0022, lat: 0, weight: 1 }, { id: "a3", lon: 0.0024, lat: 0, weight: 1 }, { id: "a4", lon: 0.0025, lat: 0, weight: 1 }],
  candidates: [C("A", 0.05, 1), C("B", 0.0023, 1)], budget: 1, max_selected: 1, coverage_radius_m: 100 }));
  const r = PL.optimizePlans(ctxEq, s);
  const eA = PL.evaluatePlan(ctxEq, s, ["A"]), eB = PL.evaluatePlan(ctxEq, s, ["B"]);
  assert.ok(eB.metrics.covered_weight > eA.metrics.covered_weight, `${eB.metrics.covered_weight} vs ${eA.metrics.covered_weight}`);
  assert.ok(eB.metrics.weighted_sum_mm > eA.metrics.weighted_sum_mm);
  assert.deepEqual(r.objectives.coverage.ids, ["B"]); assert.deepEqual(r.objectives.mean.ids, ["A"]);
});
t("пределы: 25 точек ×100, стоимость/бюджет 1e6 — целые, строгий JSON", () => {
  const ctx = H.buildContext(B, "shymkent");
  const s = H.syntheticScenario(ctx, "outpatient_clinic", { seed: 3, nPoints: 25, nCand: 16, budget: 1000000, maxSel: 5, radius: 5000 });
  s.control_points.forEach((p) => { p.weight = 100; }); s.candidates.forEach((c) => { c.cost = 1000000; });
  const r = PL.optimizePlans(ctx, V(s, ctx), { sensitivity: false });
  assert.equal(r.feasible_count, 17); // пустой + 16 по одному (два стоят 2e6 > бюджета)
  assert.ok(Number.isSafeInteger(r.objectives.mean.metrics.weighted_sum_mm));
  JSON.parse(PL.toStrictJSON(r));
  assert.throws(() => PL.toStrictJSON({ x: Infinity }), (e) => e.code === "nonfinite");
});
t("ручной план с нарушениями: feasibility.reasons перечисляет все", () => {
  const s = V(base({ candidates: [C("a", 0.01, 5), C("b", 0.02, 5), C("c", 0.03, 5)], budget: 6, max_selected: 1,
    required_ids: ["c"], excluded_ids: ["b"] }));
  const e = PL.evaluatePlan(ctxEq, s, ["a", "b"]);
  assert.equal(e.feasibility.feasible, false);
  assert.deepEqual(e.feasibility.reasons.sort(), ["includes_excluded", "missing_required", "over_budget", "too_many_selected"]);
  assert.throws(() => PL.evaluatePlan(ctxEq, s, ["zzz"]), (x) => x.code === "unknown_candidate");
});
t("weighted_mean = sum / сумма всех весов; null при unknown", () => {
  const s = V(base({ control_points: [{ id: "p1", lon: 0.01, lat: 0, weight: 3 }, { id: "p2", lon: 0.02, lat: 0, weight: 1 }] }));
  const e = PL.evaluatePlan(ctxEq, s, []);
  assert.equal(e.metrics.weighted_mean_mm, (3 * eqMm(0.01) + eqMm(0.02)) / 4);
});
t("валидация не меняет вход (замороженный объект), derived_results не попадает в результат", () => {
  const deepFreeze = (o) => { Object.values(o).forEach((v) => v && typeof v === "object" && deepFreeze(v)); return Object.freeze(o); };
  const raw = deepFreeze(base({ candidates: [C("b", 0.02, 1), C("a", 0.03, 1)], budget: 2, max_selected: 2, derived_results: { weighted_sum_mm: -1 } }));
  const v = PL.validatePlanScenario(raw, ctxEq);
  assert.equal(v.ok, true); assert.equal("derived_results" in v.scenario, false);
  const r = PL.optimizePlans(ctxEq, v.scenario);
  assert.ok(!JSON.stringify(r).includes("derived_results"));
});
t("selected_ids не влияет на оптимизацию и problem_digest", () => {
  const s1 = V(base({ candidates: [C("a", 0.01, 1), C("b", 0.02, 1)], budget: 2, max_selected: 2, selected_ids: [] }));
  const s2 = V(base({ candidates: [C("a", 0.01, 1), C("b", 0.02, 1)], budget: 2, max_selected: 2, selected_ids: ["b"] }));
  const a = PL.optimizePlans(ctxEq, s1), b = PL.optimizePlans(ctxEq, s2);
  assert.deepEqual(a, b);
});
t("категория outpatient_clinic: база только из записей своей категории", () => {
  const s = V(base({ category: "outpatient_clinic" }));
  const e = PL.evaluatePlan(ctxEq, s, []);
  assert.equal(e.n_source_records, 1); assert.equal(e.rows[0].before_ref.id, "clinic0");
});
t("JSON-раундтрип: сценарий → текст → parsePlanJSON → тот же результат", () => {
  const ctx = H.buildContext(B, "shymkent");
  const s = V(H.syntheticScenario(ctx, "school", { seed: 44, nPoints: 10, nCand: 9 }), ctx);
  const s2 = V(PL.parsePlanJSON(JSON.stringify(s)), ctx);
  assert.deepEqual(PL.optimizePlans(ctx, s2), PL.optimizePlans(ctx, s));
});

process.exit(R.done(H.arg("--json")));
