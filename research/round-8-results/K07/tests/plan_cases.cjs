// K07 round 8: shared city-plan-v2 test cases (plain JSON scenarios, engine-independent).
// Used by plan_calc.test.cjs (K07 calculator) and build_engine_crosscheck.cjs (BUILD plan.js); both compare with
// the independent Python oracle tests/oracle_plan.py.
// - EQ_DATA: a SYNTHETIC "equator" test city (not city data): 0.001° of longitude at lat 0 ≈ 111.195 m.
// - eqCases(snapshot): hand cases on it (ties, infeasible, zero budget, no candidates, no baseline, Pareto equal pairs, coverage).
// - realScenarios(C, D, F, DEMO): both slices × both categories × 8 parameter variants + 16×25 per city (SYNTHETIC
//   points/sites/costs inside the real bbox; real city_id, bbox and source_snapshot).
// - REJ: invalid scenario mutations that every CORE_SPEC validator must refuse.
const EQ_DATA = { cities: { synthetic_eq: { bbox: [0, -0.01, 0.02, 0.01], release: "synthetic", files: {}, places: [
  { id: "s-a", lon: 0.0, lat: 0, group: "school" }, { id: "s-b", lon: 0.02, lat: 0, group: "school" }] } } };
const eqCand = (id, lon, cost, cat = "school") => ({ id, lon, lat: 0, category: cat, kind: "hypothetical", cost });
function eqScenario(snapshot, over = {}) {
  return { schema_version: "city-plan-v2", city_id: "synthetic_eq", source_snapshot: snapshot, category: "school",
    control_points: [{ id: "p1", lon: 0.005, lat: 0, weight: 1 }, { id: "p2", lon: 0.01, lat: 0, weight: 1 }, { id: "p3", lon: 0.015, lat: 0, weight: 1 }],
    candidates: [eqCand("c1", 0.005, 10), eqCand("c2", 0.01, 10), eqCand("c3", 0.015, 10)],
    budget: 20, max_selected: 2, coverage_radius_m: 100, required_ids: [], excluded_ids: [], selected_ids: [], ...over };
}
function eqCases(snapshot) {
  const S = (o) => eqScenario(snapshot, o), base = S();
  return [
    ["eq/ties", S()],
    ["eq/required_over_budget", S({ required_ids: ["c1", "c2"], budget: 15 })],
    ["eq/required_over_count", S({ required_ids: ["c1", "c2", "c3"], budget: 100, max_selected: 2 })],
    ["eq/zero_budget", S({ budget: 0 })],
    ["eq/no_candidates", S({ candidates: [] })],
    ["eq/no_baseline", S({ category: "outpatient_clinic", candidates: base.candidates.map((c) => ({ ...c, category: "outpatient_clinic" })), selected_ids: ["c2"] })],
    ["eq/dominated", S({ candidates: base.candidates.concat(eqCand("c4", 0.0101, 15)), budget: 30, max_selected: 3, selected_ids: ["c1", "c4"] })],
    ["eq/coverage", S({ control_points: [{ id: "p1", lon: 0.005, lat: 0, weight: 1 }, { id: "p2", lon: 0.0102, lat: 0, weight: 5 }, { id: "p3", lon: 0.015, lat: 0, weight: 1 }], max_selected: 1, budget: 10 })],
    ["eq/pareto_equal_pairs", S({ candidates: [base.candidates[0], base.candidates[2]], max_selected: 1, budget: 10, selected_ids: ["c3"] })],
    ["eq/source_tie", S({ candidates: [eqCand("c0", 0, 1)], selected_ids: ["c0"], control_points: [{ id: "p1", lon: 0, lat: 0, weight: 1 }] })],
    ["eq/excluded_required", S({ excluded_ids: ["c2"], required_ids: ["c3"], selected_ids: ["c3"] })],
  ].map(([name, scenario]) => ({ name, scenario }));
}
function realScenarios(C, D, F, DEMO) {
  const out = [];
  for (const city of ["shymkent", "astana"]) {
    const ctx = C.makeContext(D, city, F);
    for (const cat of ["school", "outpatient_clinic"]) {
      const demo = DEMO.syntheticDemo(ctx.bbox, cat);
      const base = { schema_version: "city-plan-v2", city_id: city, source_snapshot: ctx.source_snapshot, category: cat,
        control_points: demo.control_points, candidates: demo.candidates, budget: demo.budget, max_selected: demo.max_selected,
        coverage_radius_m: demo.coverage_radius_m, required_ids: [], excluded_ids: [], selected_ids: ["site-2", "site-4"] };
      const vars = [["demo", {}], ["budget0", { budget: 0 }], ["budget150", { budget: 150 }], ["max5_b1000", { max_selected: 5, budget: 1000 }],
        ["req_exc", { required_ids: ["site-5"], excluded_ids: ["site-4"], selected_ids: ["site-5"], budget: 300 }], ["radius100", { coverage_radius_m: 100 }],
        ["radius5000", { coverage_radius_m: 5000 }], ["infeasible", { required_ids: ["site-5", "site-3"], budget: 300 }]];
      for (const [name, over] of vars) out.push({ name: `${city}/${cat}/${name}`, scenario: { ...base, ...over } });
    }
    const bb = ctx.bbox, g = (u, v) => [Math.round((bb[0] + (bb[2] - bb[0]) * u) * 1e6) / 1e6, Math.round((bb[1] + (bb[3] - bb[1]) * v) * 1e6) / 1e6];
    const pts = Array.from({ length: 25 }, (_, i) => { const [lon, lat] = g(0.08 + 0.21 * (i % 5), 0.08 + 0.21 * Math.floor(i / 5)); return { id: `cp-${i + 1}`, lon, lat, weight: 1 + (i * 7) % 10 }; });
    const sites = Array.from({ length: 16 }, (_, i) => { const [lon, lat] = g(0.12 + 0.25 * (i % 4), 0.12 + 0.25 * Math.floor(i / 4)); return { id: `site-${String(i + 1).padStart(2, "0")}`, lon, lat, category: "school", kind: "hypothetical", cost: 50 + (i * 37) % 120 }; });
    out.push({ name: `${city}/school/max_16x25`, scenario: { schema_version: "city-plan-v2", city_id: city, source_snapshot: ctx.source_snapshot, category: "school",
      control_points: pts, candidates: sites, budget: 400, max_selected: 5, coverage_radius_m: 300, required_ids: [], excluded_ids: [], selected_ids: ["site-01", "site-16"] } });
  }
  return out;
}
const REJ = [
  ["schema", (o) => { o.schema_version = "city-plan-v3"; }, "bad_schema"], ["city", (o) => { o.city_id = "astana"; }, "bad_city"],
  ["snapshot", (o) => { o.source_snapshot = "sha256:00"; }, "bad_snapshot"], ["unknown field", (o) => { o.url = "https://example.com/x.js"; }, "unknown_field"],
  ["point extra field", (o) => { o.control_points[0].population = 5000; }, "unknown_field"], ["duplicate point id", (o) => { o.control_points[1].id = "p1"; }, "duplicate_id"],
  ["outside bbox", (o) => { o.control_points[0].lon = 0.5; }, "outside_bbox"], ["NaN lat", (o) => { o.candidates[0].lat = NaN; }, "bad_coordinate"],
  ["weight 0", (o) => { o.control_points[0].weight = 0; }, "out_of_range"], ["weight 1.5", (o) => { o.control_points[0].weight = 1.5; }, "not_integer"],
  ["cost 0", (o) => { o.candidates[0].cost = 0; }, "out_of_range"], ["cost negative", (o) => { o.candidates[0].cost = -5; }, "out_of_range"],
  ["budget too big", (o) => { o.budget = 1000001; }, "out_of_range"], ["max_selected 6", (o) => { o.max_selected = 6; }, "out_of_range"],
  ["radius 50", (o) => { o.coverage_radius_m = 50; }, "out_of_range"], ["required∩excluded", (o) => { o.required_ids = ["c1"]; o.excluded_ids = ["c1"]; }, "required_excluded_overlap"],
  ["unknown reference", (o) => { o.selected_ids = ["c9"]; }, "unknown_reference"], ["duplicate in required", (o) => { o.required_ids = ["c1", "c1"]; }, "duplicate_id"],
  ["candidate kind", (o) => { o.candidates[0].kind = "observed"; }, "bad_kind"], ["candidate category", (o) => { o.candidates[0].category = "outpatient_clinic"; }, "bad_category"],
  ["26 points", (o) => { o.control_points = Array.from({ length: 26 }, (_, i) => ({ id: "q" + i, lon: 0.001, lat: 0, weight: 1 })); }, "bad_count"],
  ["17 candidates", (o) => { o.candidates = Array.from({ length: 17 }, (_, i) => ({ id: "k" + i, lon: 0.001, lat: 0, category: "school", kind: "hypothetical", cost: 1 })); o.selected_ids = []; }, "bad_count"],
  ["id 65 chars", (o) => { o.control_points[0].id = "x".repeat(65); }, "bad_id"], ["id with markup", (o) => { o.candidates[0].id = "<b>"; }, "bad_id"],
  ["0 points", (o) => { o.control_points = []; }, "bad_count"], ["missing field", (o) => { delete o.budget; }, "missing_field"],
  ["Infinity budget", (o) => { o.budget = Infinity; }, "not_integer"], ["string weight", (o) => { o.control_points[0].weight = "2"; }, "not_integer"],
];
module.exports = { EQ_DATA, eqScenario, eqCases, realScenarios, REJ };
