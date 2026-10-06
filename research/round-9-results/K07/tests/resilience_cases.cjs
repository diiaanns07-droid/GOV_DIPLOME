// K07 round 9: shared city-resilience-v1 envelopes (plain JSON, engine-independent).
// Used by resilience_k07.test.cjs (K07 adapter) and build_resilience_crosscheck.cjs (BUILD web/resilience.js); both are
// compared with the independent Python oracle tests/oracle_resilience.py.
// - eqPlan(ctxEq, over): SYNTHETIC equator test city of r8 (sources s-a at lon 0, s-b at lon 0.02; 0.005° ≈ 555 975 mm).
// - handEnvelopes(ctxEq): hand cases with values worked out in the comments (resilience_k07.test.cjs H01–H06).
// - realEnvelopes(PL, D, F, R8): both slices × both categories with the K07 r8 SYNTHETIC fixtures and cases built from
//   real source IDs, plus 12×25×8 per city. Points/sites/costs are SYNTHETIC; city_id, bbox, snapshot and record IDs real.
const fs = require("fs"), path = require("path");
const env = (plan, cases) => ({ schema_version: "city-resilience-v1", plan, cases });
const eqPlan = (ctxEq, over = {}) => ({ schema_version: "city-plan-v2", city_id: "synthetic_eq", source_snapshot: ctxEq.source_snapshot, category: "school",
  control_points: [{ id: "p1", lon: 0.005, lat: 0, weight: 1 }, { id: "p2", lon: 0.01, lat: 0, weight: 1 }, { id: "p3", lon: 0.015, lat: 0, weight: 1 }],
  candidates: ["c1", "c2", "c3"].map((id, i) => ({ id, lon: 0.005 * (i + 1), lat: 0, category: "school", kind: "hypothetical", cost: 10 })),
  budget: 10, max_selected: 1, coverage_radius_m: 100, required_ids: [], excluded_ids: [], selected_ids: [], ...over });
function handEnvelopes(ctxEq) {
  const Y = [{ id: "Y", label: "без записи s-b", disabled_source_ids: ["s-b"] }];
  return [
    { name: "eq/robust_differs_zero_price", envelope: env(eqPlan(ctxEq), Y) },                      // nominal {c1}, robust {c2}, price 0
    { name: "eq/all_excluded_budget0", envelope: env(eqPlan(ctxEq, { budget: 0 }), [{ id: "Z", label: "все записи исключены", disabled_source_ids: ["s-a", "s-b"] }]) },
    { name: "eq/duplicate_cases", envelope: env(eqPlan(ctxEq, { budget: 20, max_selected: 2 }), [...Y, { id: "Y2", label: "то же, другой ID", disabled_source_ids: ["s-b"] }]) },
    { name: "eq/required_over_budget", envelope: env(eqPlan(ctxEq, { required_ids: ["c1", "c2"], budget: 15, max_selected: 2 }), Y) },
    { name: "eq/manual_c1", envelope: env(eqPlan(ctxEq, { selected_ids: ["c1"] }), Y) },
    { name: "eq/two_cases_both_sides", envelope: env(eqPlan(ctxEq, { budget: 20, max_selected: 2 }), [...Y, { id: "X", label: "без s-a", disabled_source_ids: ["s-a"] }]) },
  ];
}
function realEnvelopes(PL, D, F, R8) {
  const out = [];
  const src = (ctx, cat) => ctx.places.filter((p) => p.group === cat).map((p) => p.id).sort();
  for (const city of ["shymkent", "astana"]) {
    const ctx = PL.makeContext(D, city, F);
    for (const cat of ["school", "outpatient_clinic"]) {
      const plan = JSON.parse(fs.readFileSync(path.join(R8, "fixtures", `synthetic_demo_${city}_${cat}.json`), "utf8"));
      const s = src(ctx, cat);
      const cases = [{ id: "C1", label: "две записи под вопросом", disabled_source_ids: s.slice(0, 2) },
        { id: "C2", label: "пять записей", disabled_source_ids: s.slice(0, 5) },
        { id: "C3", label: "то же, что C1", disabled_source_ids: s.slice(0, 2) },
        { id: "C4", label: "все записи категории", disabled_source_ids: s.slice() }];
      out.push({ name: `${city}/${cat}/demo`, city, envelope: env({ ...plan, selected_ids: ["site-2"] }, cases) });
      out.push({ name: `${city}/${cat}/budget300_max3`, city, envelope: env({ ...plan, budget: 300, max_selected: 3, selected_ids: ["site-2", "site-4"] }, cases.slice(0, 2)) });
    }
    const bb = ctx.bbox, g = (u, v) => [Math.round((bb[0] + (bb[2] - bb[0]) * u) * 1e6) / 1e6, Math.round((bb[1] + (bb[3] - bb[1]) * v) * 1e6) / 1e6];
    const s = src(ctx, "school");
    const plan = { schema_version: "city-plan-v2", city_id: city, source_snapshot: ctx.source_snapshot, category: "school",
      control_points: Array.from({ length: 25 }, (_, i) => { const [lon, lat] = g(0.08 + 0.21 * (i % 5), 0.08 + 0.21 * Math.floor(i / 5)); return { id: `cp-${i + 1}`, lon, lat, weight: 1 + (i * 7) % 10 }; }),
      candidates: Array.from({ length: 12 }, (_, i) => { const [lon, lat] = g(0.12 + 0.25 * (i % 4), 0.12 + 0.37 * Math.floor(i / 4)); return { id: `site-${String(i + 1).padStart(2, "0")}`, lon, lat, category: "school", kind: "hypothetical", cost: 50 + (i * 37) % 120 }; }),
      budget: 400, max_selected: 5, coverage_radius_m: 300, required_ids: [], excluded_ids: [], selected_ids: ["site-01"] };
    const cases = Array.from({ length: 7 }, (_, k) => ({ id: `K${k + 1}`, label: `случай ${k + 1}`, disabled_source_ids: s.filter((_, i) => (i + k) % (k + 2) === 0).slice(0, Math.max(1, Math.min(s.length, k + 1))) }));
    out.push({ name: `${city}/school/max_12x25x8`, city, envelope: env(plan, cases) });
  }
  return out;
}
// envelope mutations every CORE_SPEC r9 validator must refuse (e.__ctx: the test city context); expected codes are the K07
// adapter's — BUILD may use its own codes, the cross-check only requires a refusal
const REJ = [
  ["unknown top field (derived)", (e) => { e.derived_results = { robust: ["c3"] }; }, "unknown_field"], ["schema", (e) => { e.schema_version = "city-resilience-v2"; }, "bad_schema"],
  ["no cases", (e) => { e.cases = []; }, "bad_count"], ["8 user cases", (e) => { e.cases = Array.from({ length: 8 }, (_, i) => ({ id: "c" + i, label: "x", disabled_source_ids: ["s-a"] })); }, "bad_count"],
  ["case id base", (e) => { e.cases[0].id = "base"; }, "reserved_id"], ["duplicate case id", (e) => { e.cases.push({ ...e.cases[0] }); }, "duplicate_id"],
  ["case id with markup", (e) => { e.cases[0].id = "<b>"; }, "bad_id"], ["empty label", (e) => { e.cases[0].label = "  "; }, "bad_label"],
  ["label 121 chars", (e) => { e.cases[0].label = "я".repeat(121); }, "bad_label"], ["label with control char", (e) => { e.cases[0].label = "a\u0007b"; }, "bad_label"],
  ["no exclusions", (e) => { e.cases[0].disabled_source_ids = []; }, "bad_exclusions"], ["duplicate exclusion", (e) => { e.cases[0].disabled_source_ids = ["s-b", "s-b"]; }, "duplicate_id"],
  ["candidate ID as exclusion", (e) => { e.cases[0].disabled_source_ids = ["c1"]; }, "candidate_not_source"], ["unknown source", (e) => { e.cases[0].disabled_source_ids = ["s-z"]; }, "unknown_source"],
  ["source of another category (no clinic records here)", (e) => { e.plan = eqPlan(e.__ctx, { category: "outpatient_clinic", candidates: eqPlan(e.__ctx).candidates.map((c) => ({ ...c, category: "outpatient_clinic" })) }); }, null],
  ["extra case field", (e) => { e.cases[0].weight = 5; }, "unknown_field"], ["bad plan (v2 rule)", (e) => { e.plan.budget = -1; }, null],
  ["13 candidates", (e) => { e.plan.candidates = Array.from({ length: 13 }, (_, i) => ({ id: "k" + i, lon: 0.001 * (i + 1), lat: 0, category: "school", kind: "hypothetical", cost: 1 })); }, "too_many_candidates"],
];
module.exports = { env, eqPlan, handEnvelopes, realEnvelopes, REJ };
