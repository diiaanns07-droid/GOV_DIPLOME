/* Этап 1: validate/evaluate/optimize, полный перебор, ограничения, ничьи, независимость от порядка.
 *   node tests/test_stage1.cjs --app-root <checkout>/prototypes/city-evidence [--json OUT]
 */
"use strict";
const assert = require("node:assert/strict");
const H = require("./helpers.cjs");
const { PL } = H;
const R = H.runner(), t = R.t;
const APP = H.arg("--app-root");
if (!APP) { console.error("нужен --app-root"); process.exit(2); }
const B = H.loadBuild(APP);

// ---------- ручной пример на экваторе (synthetic): d = R·Δλ точно ----------
const RAD = Math.PI / 180;
const eqMm = (dlonDeg) => Math.round(PL.R_EARTH_M * Math.abs(dlonDeg) * RAD * 1000);
const eqCtx = { city_id: "shymkent", bbox: [0, -0.01, 0.1, 0.01], source_snapshot: "SYNTHETIC-equator",
  records: [{ id: "src_a", lon: 0.000, lat: 0, group: "school" }] };
function eqScenario(over) {
  return { schema_version: PL.SCHEMA, city_id: "shymkent", source_snapshot: "SYNTHETIC-equator", category: "school",
    control_points: [{ id: "p1", lon: 0.010, lat: 0, weight: 1 }, { id: "p2", lon: 0.020, lat: 0, weight: 2 }, { id: "p3", lon: 0.050, lat: 0, weight: 1 }],
    candidates: [
      { id: "c_near2", lon: 0.021, lat: 0, category: "school", kind: "hypothetical", cost: 100 },
      { id: "c_far", lon: 0.050, lat: 0, category: "school", kind: "hypothetical", cost: 300 },
      { id: "c_mid", lon: 0.035, lat: 0, category: "school", kind: "hypothetical", cost: 150 }],
    budget: 300, max_selected: 2, coverage_radius_m: 1500, required_ids: [], excluded_ids: [], selected_ids: [], ...over };
}
const V = (s, ctx = eqCtx) => { const v = PL.validatePlanScenario(s, ctx); if (!v.ok) throw new Error(JSON.stringify(v.error)); return v.scenario; };

t("экватор: расстояние в мм = round(R·Δλ·1000) (независимая формула)", () => {
  assert.equal(PL.distMm(0, 0, 0.01, 0), eqMm(0.01));
  assert.equal(PL.distMm(0.02, 0, 0.021, 0), eqMm(0.001));
});
t("экватор: пустой план — baseline; delta=0; метрики по формулам", () => {
  const s = V(eqScenario());
  const e = PL.evaluatePlan(eqCtx, s, []);
  const b = [eqMm(0.01), eqMm(0.02), eqMm(0.05)];
  assert.deepEqual(e.rows.map((r) => r.after_mm), b);
  assert.deepEqual(e.rows.map((r) => r.delta_mm), [0, 0, 0]);
  assert.equal(e.metrics.weighted_sum_mm, b[0] + 2 * b[1] + b[2]);
  assert.equal(e.metrics.max_mm, b[2]);
  assert.equal(e.metrics.covered_weight, b.filter((x) => x <= 1500000).length ? 1 : 0); // только p1 (1112 м) в 1500 м
  assert.equal(e.metrics.cost, 0);
  assert.equal(e.feasibility.feasible, true);
});
t("экватор: ручной оптимум (бюджет 300, ≤2): mean → c_mid+c_near2; minimax → c_mid+c_near2; coverage → тот же", () => {
  const s = V(eqScenario());
  const r = PL.optimizePlans(eqCtx, s);
  assert.equal(r.status, "optimal");
  assert.equal(r.total, 8); assert.equal(r.evaluated, 8);
  // допустимы: {}, {near2}, {far}, {mid}, {near2,mid}(250). {near2,far}=400, {far,mid}=450 > 300
  assert.equal(r.feasible_count, 5);
  // p1: base 1112 м; p2: near2 → 111 м; p3: mid → 1668 м (vs base 5560); far одна даёт p3=0, но p2 остаётся 2224
  const near2mid = 1 * eqMm(0.01) + 2 * eqMm(0.001) + 1 * eqMm(0.015);
  const farOnly = 1 * eqMm(0.01) + 2 * eqMm(0.02) + 0;
  assert.ok(near2mid < farOnly);
  assert.deepEqual(r.objectives.mean.ids, ["c_mid", "c_near2"]);
  assert.equal(r.objectives.mean.metrics.weighted_sum_mm, near2mid);
  assert.deepEqual(r.objectives.minimax.ids, ["c_mid", "c_near2"]);
  assert.equal(r.objectives.minimax.metrics.max_mm, eqMm(0.015));
  assert.deepEqual(r.same_plan_as.mean.sort(), ["coverage", "minimax"].filter((o) => r.objectives[o].ids.join() === "c_mid,c_near2"));
});
t("экватор: required/excluded/бюджет/max_selected соблюдаются", () => {
  const r1 = PL.optimizePlans(eqCtx, V(eqScenario({ required_ids: ["c_far"] })));
  for (const o of ["mean", "minimax", "coverage"]) assert.ok(r1.objectives[o].ids.includes("c_far"));
  assert.ok(r1.objectives.mean.cost <= 300);
  const r2 = PL.optimizePlans(eqCtx, V(eqScenario({ excluded_ids: ["c_mid"] })));
  for (const o of ["mean", "minimax", "coverage"]) assert.ok(!r2.objectives[o].ids.includes("c_mid"));
  const r3 = PL.optimizePlans(eqCtx, V(eqScenario({ max_selected: 0 })));
  assert.deepEqual(r3.objectives.mean.ids, []); assert.equal(r3.feasible_count, 1);
  const r4 = PL.optimizePlans(eqCtx, V(eqScenario({ budget: 0 })));
  assert.deepEqual(r4.objectives.mean.ids, []);
});
t("экватор: required невыполним → infeasible с причиной, ограничения не снимаются", () => {
  const r = PL.optimizePlans(eqCtx, V(eqScenario({ required_ids: ["c_far", "c_mid"] })));
  assert.equal(r.status, "infeasible");
  assert.ok(r.reasons.some((x) => /бюджет/.test(x)), r.reasons.join());
  const r2 = PL.optimizePlans(eqCtx, V(eqScenario({ required_ids: ["c_near2", "c_mid", "c_far"], budget: 1000 })));
  assert.equal(r2.status, "infeasible");
  assert.ok(r2.reasons.some((x) => /max_selected/.test(x)));
  assert.equal(r2.objectives, null);
});
t("ничья: источник выигрывает у кандидата на том же расстоянии; среди кандидатов — меньший id", () => {
  const s = V(eqScenario({ candidates: [
    { id: "zz", lon: 0.000, lat: 0, category: "school", kind: "hypothetical", cost: 1 },
    { id: "aa", lon: 0.000, lat: 0, category: "school", kind: "hypothetical", cost: 1 }], budget: 10 }));
  const e = PL.evaluatePlan(eqCtx, s, ["zz", "aa"]);
  assert.equal(e.rows[0].after_ref.ns, "source"); // p1: src_a и кандидаты на одной точке → source
  const s2 = V({ ...eqScenario(), candidates: [
    { id: "zz", lon: 0.020, lat: 0, category: "school", kind: "hypothetical", cost: 1 },
    { id: "aa", lon: 0.020, lat: 0, category: "school", kind: "hypothetical", cost: 1 }], budget: 10 });
  const e2 = PL.evaluatePlan(eqCtx, s2, ["zz", "aa"]);
  const p2 = e2.rows.find((r) => r.point_id === "p2");
  assert.deepEqual(p2.after_ref, { ns: "candidate", id: "aa", kind: "hypothetical" });
  // оптимизатор: при равных ключах — меньший sorted IDs, короче раньше
  const r = PL.optimizePlans(eqCtx, s2);
  assert.deepEqual(r.objectives.mean.ids, ["aa"]);
});
t("пустой baseline и пустой план: after=null, unknown_count, max/mean=null", () => {
  const ctx0 = { ...eqCtx, records: [] };
  const s = V(eqScenario(), ctx0);
  const e = PL.evaluatePlan(ctx0, s, []);
  assert.equal(e.metrics.unknown_count, 3); assert.equal(e.metrics.max_mm, null); assert.equal(e.metrics.weighted_mean_mm, null);
  assert.ok(e.rows.every((r) => r.after_mm === null && r.delta_mm === null));
  const e2 = PL.evaluatePlan(ctx0, s, ["c_mid"]);
  assert.ok(e2.rows.every((r) => r.before_mm === null && r.after_mm !== null && r.delta_mm === null));
  const r = PL.optimizePlans(ctx0, s);
  assert.equal(r.objectives.mean.metrics.unknown_count, 0); // любой непустой план лучше пустого по unknown_count
  assert.notDeepEqual(r.objectives.mean.ids, []);
});

// ---------- валидация ----------
const bad = (over, code, ctx = eqCtx) => {
  const v = PL.validatePlanScenario({ ...eqScenario(), ...over }, ctx);
  assert.equal(v.ok, false, `ожидалась ошибка ${code}`); assert.equal(v.error.code, code, JSON.stringify(v.error));
};
t("валидация: поля, версии, город, срез, категория", () => {
  bad({ schema_version: "city-plan-v1" }, "bad_version");
  bad({ city_id: "almaty" }, "bad_city");
  bad({ city_id: "astana" }, "foreign_city");
  bad({ source_snapshot: "other" }, "foreign_snapshot");
  bad({ category: "hospital" }, "bad_category");
  bad({ extra: 1 }, "unknown_field");
  const s = eqScenario(); delete s.selected_ids;
  assert.equal(PL.validatePlanScenario(s, eqCtx).error.code, "missing_field");
  assert.equal(PL.validatePlanScenario({ ...eqScenario(), derived_results: { anything: 1 } }, eqCtx).ok, true);
});
t("валидация: числа, пределы, координаты, bbox", () => {
  bad({ budget: 1.5 }, "bad_number"); bad({ budget: -1 }, "bad_number"); bad({ budget: 1000001 }, "bad_number");
  bad({ max_selected: 6 }, "bad_number"); bad({ coverage_radius_m: 99 }, "bad_number"); bad({ coverage_radius_m: 5001 }, "bad_number");
  bad({ control_points: [] }, "bad_count");
  bad({ control_points: Array.from({ length: 26 }, (_, i) => ({ id: "p" + i, lon: 0.01, lat: 0, weight: 1 })) }, "bad_count");
  bad({ control_points: [{ id: "p", lon: 0.01, lat: 0, weight: 0 }] }, "bad_number");
  bad({ control_points: [{ id: "p", lon: 0.01, lat: 0, weight: 101 }] }, "bad_number");
  bad({ control_points: [{ id: "p", lon: 0.2, lat: 0, weight: 1 }] }, "outside_bbox");
  bad({ control_points: [{ id: "p", lon: NaN, lat: 0, weight: 1 }] }, "bad_coord");
  bad({ candidates: Array.from({ length: 17 }, (_, i) => ({ id: "c" + i, lon: 0.01, lat: 0, category: "school", kind: "hypothetical", cost: 1 })) }, "bad_count");
  bad({ candidates: [{ id: "c", lon: 0.01, lat: 0, category: "school", kind: "hypothetical", cost: 0 }] }, "bad_number");
  bad({ candidates: [{ id: "c", lon: 0.01, lat: 0, category: "outpatient_clinic", kind: "hypothetical", cost: 1 }] }, "category_mismatch");
  bad({ candidates: [{ id: "c", lon: 0.01, lat: 0, category: "school", kind: "observed", cost: 1 }] }, "bad_kind");
});
t("валидация: ID, ссылки, required∩excluded", () => {
  bad({ control_points: [{ id: "x".repeat(65), lon: 0.01, lat: 0, weight: 1 }] }, "bad_id");
  bad({ control_points: [{ id: "a", lon: 0.01, lat: 0, weight: 1 }, { id: "a", lon: 0.02, lat: 0, weight: 1 }] }, "duplicate_id");
  bad({ required_ids: ["nope"] }, "unknown_candidate");
  bad({ selected_ids: ["c_mid", "c_mid"] }, "duplicate_id");
  bad({ required_ids: ["c_mid"], excluded_ids: ["c_mid"] }, "required_excluded_overlap");
  bad({ control_points: [{ id: "https://x", lon: 0.01, lat: 0, weight: 1 }] }, "bad_id");
});
t("строгий JSON: NaN, Infinity, 1e999, повтор ключа, лишние данные, >256 KiB", () => {
  const ok = JSON.stringify(eqScenario());
  assert.equal(PL.validatePlanScenario(PL.parsePlanJSON(ok), eqCtx).ok, true);
  for (const bt of [ok.replace('"budget":300', '"budget":NaN'), ok.replace('"budget":300', '"budget":Infinity'),
    ok.replace('"budget":300', '"budget":1e999'), ok.replace('"budget":300', '"budget":300,"budget":1'), ok + "x"]) {
    assert.throws(() => PL.parsePlanJSON(bt), (e) => e.code === "bad_json");
  }
  assert.throws(() => PL.parsePlanJSON(" ".repeat(PL.LIM.bytes) + ok), (e) => e.code === "too_large");
});

// ---------- независимость от порядка и digest ----------
t("перестановка массивов не меняет план, метрики и problem_digest; selected_ids — только в scenario digest", () => {
  const s = V(eqScenario({ required_ids: [], excluded_ids: [] }));
  const s2 = V({ ...eqScenario(), control_points: H.shuffled(eqScenario().control_points, 7), candidates: H.shuffled(eqScenario().candidates, 9) });
  const a = PL.optimizePlans(eqCtx, s), b = PL.optimizePlans(eqCtx, s2);
  assert.equal(a.problem_digest, b.problem_digest);
  assert.deepEqual(a.objectives, b.objectives);
  assert.deepEqual(a.pareto, b.pareto);
  const s3 = V(eqScenario({ selected_ids: ["c_mid"] }));
  assert.equal(PL.problemDigest(s3), PL.problemDigest(s));
  assert.notEqual(PL.scenarioDigest(s3), PL.scenarioDigest(s));
  assert.notEqual(PL.problemDigest(V(eqScenario({ budget: 299 }))), PL.problemDigest(s));
  assert.notEqual(PL.problemDigest(V({ ...eqScenario(), control_points: eqScenario().control_points.map((p, i) => ({ ...p, weight: i ? p.weight : 3 })) })), PL.problemDigest(s));
});
t("гаверсинус только при подготовке: m·(src+n) вызовов, не в переборе", () => {
  const s = V(eqScenario());
  const r = PL.optimizePlans(eqCtx, s, { sensitivity: false });
  assert.equal(r.haversine_calls, 3 * (1 + 3));
});

// ---------- реальные срезы сборки (кандидаты SYNTHETIC) ----------
for (const city of ["shymkent", "astana"]) {
  for (const cat of ["school", "outpatient_clinic"]) {
    t(`${city}/${cat}: реальный срез + synthetic кандидаты — оптимизация, проверка допустимости победителей`, () => {
      const ctx = H.buildContext(B, city);
      assert.ok(ctx.source_snapshot && ctx.source_snapshot.length > 10, "snapshot сборки");
      const s = V(H.syntheticScenario(ctx, cat, { seed: city.length * 31 + cat.length, nCand: 10 }), ctx);
      const r = PL.optimizePlans(ctx, s);
      assert.equal(r.status, "optimal"); assert.equal(r.evaluated, 1024);
      for (const o of ["mean", "minimax", "coverage"]) {
        const e = PL.evaluatePlan(ctx, s, r.objectives[o].ids);
        assert.equal(e.feasibility.feasible, true);
        assert.deepEqual(e.metrics, r.objectives[o].metrics);
      }
      assert.equal(r.n_source_records, B.D.cities[city].places.filter((p) => p.group === cat).length);
      JSON.parse(PL.toStrictJSON(r));
    });
  }
}

process.exit(R.done(H.arg("--json")));
