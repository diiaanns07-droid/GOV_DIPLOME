// Этап 1: каталог фактов evaluatePlan/optimizePlans. node tests/stage1_catalog.cjs --app-root <app>
const { fixture, solve, test, finish } = require("./common.cjs");
const facts = (b) => [...b.catalog.values()];
const get = (b, p) => b.catalog.get(`${b.city}/${b.scenario}/${p}`);

test("S1_required_fields", "у каждого факта kind/unit/scope/hypothetical/label ru+kk без цифр", () => {
  const bad = [];
  for (const n of ["real_shymkent_school", "real_astana_clinic", "synthetic_empty_sources", "synthetic_infeasible_required", "synthetic_tie_same_winners"])
    for (const f of facts(solve(fixture(n)).built)) if (!f.kind || !f.unit || !f.scope || typeof f.hypothetical !== "boolean" || /\d/.test(f.label.ru + f.label.kk)) bad.push(f.id);
  return { pass: bad.length === 0, observed: bad.slice(0, 5) };
});
test("S1_values_from_engine", "значения фактов равны метрикам evaluatePlan/optimizePlans", () => {
  const s = solve(fixture("real_shymkent_school")), b = s.built, mism = [];
  const chk = (role, m) => { for (const [k, mk] of [["weighted_mean", "weighted_mean_mm"], ["max", "max_mm"], ["covered_weight", "covered_weight"], ["cost", "cost"], ["count", "count"], ["unknown_count", "unknown_count"], ["coverage_fraction", "coverage_fraction"]])
    if (get(b, `plan.${role}.${k}`).value !== m[mk]) mism.push(`${role}.${k}`); };
  chk("manual", s.man.metrics); chk("baseline", s.base.metrics);
  for (const k of ["mean", "minimax", "coverage"]) chk(k, s.opt.objectives[k].metrics);
  return { pass: mism.length === 0 && get(b, "constraint.evaluated").value === s.opt.evaluated, observed: mism };
});
test("S1_hypothetical_and_kinds", "planы с кандидатами hypothetical; без объектов — нет; бюджет/радиус — user_input, радиус analysis_parameter", () => {
  const b = solve(fixture("real_shymkent_school")).built;
  const ok = get(b, "plan.mean.weighted_mean").hypothetical === true && get(b, "plan.baseline.weighted_mean").hypothetical === false
    && get(b, "constraint.budget").kind === "user_input" && get(b, "constraint.budget").unit === "conditional_units"
    && get(b, "constraint.radius").scope === "analysis_parameter" && get(b, "plan.mean.weighted_mean").unit === "mm";
  return { pass: ok, observed: [get(b, "plan.mean.weighted_mean").hypothetical, get(b, "constraint.radius").scope] };
});
test("S1_unknown_is_null_not_zero", "пустой срез: baseline mean/max = null (unknown, unknown_points), unknown_count = 3, covered_weight = 0", () => {
  const b = solve(fixture("synthetic_empty_sources")).built;
  const m = get(b, "plan.baseline.weighted_mean"), x = get(b, "plan.baseline.max");
  const ok = m.value === null && m.kind === "unknown" && m.missing_reason === "unknown_points" && x.value === null
    && get(b, "plan.baseline.unknown_count").value === 3 && get(b, "plan.baseline.covered_weight").value === 0 && get(b, "constraint.sources").value === 0;
  return { pass: ok, observed: [m.value, m.kind, x.value] };
});
test("S1_infeasible_no_objective_facts", "infeasible: фактов победителей нет, статус и причины в meta; ручной план feasible=0 с причинами", () => {
  const b = solve(fixture("synthetic_infeasible_required")).built;
  const ok = !get(b, "plan.mean.cost") && b.meta.status === "infeasible" && b.meta.infeasible_reasons.some((r) => r.code === "over_budget")
    && get(b, "plan.manual.feasible").value === 0 && get(b, "plan.manual.feasible").reasons.some((r) => r.code === "missing_required");
  return { pass: ok, observed: b.meta };
});
test("S1_digest_changes", "digest каталога меняется при смене ручного набора, бюджета, радиуса; стабилен при перестановке массивов", () => {
  const fx = fixture("real_shymkent_school"), d0 = solve(fx).built.digest;
  const rev = { control_points: fx.scenario.control_points.slice().reverse(), candidates: fx.scenario.candidates.slice().reverse(), selected_ids: fx.scenario.selected_ids.slice().reverse() };
  const d = { sel: solve(fx, { selected_ids: ["c-sev"] }).built.digest, budget: solve(fx, { budget: 150 }).built.digest,
    radius: solve(fx, { coverage_radius_m: 600 }).built.digest, reordered: solve(fx, rev).built.digest };
  return { pass: d.sel !== d0 && d.budget !== d0 && d.radius !== d0 && d.reordered === d0, observed: d };
});
finish("stage1_catalog");
