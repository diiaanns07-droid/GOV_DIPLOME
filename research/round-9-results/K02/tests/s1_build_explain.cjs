// K02 r9 этап 1: проверка ДЕЙСТВУЮЩИХ explainPlans/reportHtml/optimizePlans сборки.
//   node tests/s1_build_explain.cjs --app-root <prototypes/city-evidence @ d865dd4> [--json out.json]
const { F, PL, r8, r8exp, variants, solve, test, finish, code } = require("./common.cjs");
const tw = (sc) => sc.control_points.reduce((t, p) => t + p.weight, 0);

// B0: числа BUILD против независимого Python-оракула K02 r8 (тот же срез, те же входы).
for (const v of variants()) {
  test(`B0_${v.fixture}__${v.name}`, "optimizePlans/evaluatePlan/sensitivity = оракул r8", () => {
    const s = solve(r8(v.fixture), v.patch), e = r8exp(`${v.fixture}__${v.name}`).facts, W = tw(s.sc), mism = [];
    const eq = (k, got) => { if (k in e && JSON.stringify(e[k]) !== JSON.stringify(got)) mism.push({ k, build: got, oracle: e[k] }); };
    const plan = (role, ids, m) => { eq(`plan.${role}.selection`, ids.join(", ")); eq(`plan.${role}.cost`, m.cost); eq(`plan.${role}.unknown_count`, m.unknown_count);
      eq(`plan.${role}.max`, m.max_mm); eq(`plan.${role}.covered_weight`, m.covered_weight); eq(`plan.${role}.weighted_mean`, m.unknown_count ? null : m.weighted_sum_mm / W); };
    plan("manual", s.man.selected_ids, s.man.metrics); plan("baseline", [], { ...s.man.baseline, cost: 0 });
    eq("plan.manual.feasible", s.man.feasibility.feasible ? 1 : 0);
    eq("constraint.feasible_count", s.res.feasible_count);
    if (s.res.status === "optimal") for (const k of ["mean", "minimax", "coverage"]) plan(k, s.res.objectives[k].ids, s.res.objectives[k]);
    if ((s.res.status === "optimal" ? "optimal" : "infeasible") !== r8exp(`${v.fixture}__${v.name}`).status) mism.push({ k: "status", build: s.res.status });
    s.res.pareto.forEach((p, i) => { eq(`pareto.p${i + 1}.cost`, p.cost); eq(`pareto.p${i + 1}.selection`, p.ids.join(", ")); eq(`pareto.p${i + 1}.weighted_mean`, p.weighted_sum_mm / W); });
    if (`pareto.p${s.res.pareto.length + 1}.cost` in e) mism.push({ k: "pareto_length", build: s.res.pareto.length });
    s.sens.forEach((x, i) => { eq(`sensitivity.s${i + 1}.budget`, x.budget); eq(`sensitivity.s${i + 1}.status`, x.status);
      const m = x.objectives && x.objectives.mean; eq(`sensitivity.s${i + 1}.mean_cost`, m ? m.cost : null); eq(`sensitivity.s${i + 1}.mean_weighted_mean`, m ? (m.unknown_count ? null : m.weighted_sum_mm / W) : null); });
    return { pass: mism.length === 0, observed: mism.slice(0, 5) };
  });
}

// E1: каждое число текста — из сценария/результата (отпечаток исключён).
function allowedNumbers(s) {
  const A = new Set(), add = (v) => { if (v !== null && v !== undefined) A.add(String(v)); };
  const mt = (mm) => { if (mm === null || mm === undefined) return; if (mm >= 1e6) A.add((mm / 1e6).toFixed(2).replace(".", ",")); else A.add(String(Math.round(mm / 1000))); };
  const W = tw(s.sc); [s.sc.budget, s.sc.max_selected, s.sc.coverage_radius_m, W, s.sc.control_points.length, s.sc.candidates.length].forEach(add);
  const m = s.man.metrics; [m.cost, m.covered_weight, m.total_weight, m.unknown_count].forEach(add); mt(m.weighted_mean_mm); mt(m.max_mm);
  if (s.res.status === "optimal") { [s.res.evaluated, s.res.feasible_count, s.res.pareto.length, s.res.pareto_excluded_unknown].forEach(add);
    for (const o of Object.values(s.res.objectives)) { [o.cost, o.covered_weight].forEach(add); mt(o.max_mm); mt(o.unknown_count ? null : o.weighted_sum_mm / W); }
    s.res.pareto.forEach((p) => add(p.cost)); }
  for (const x of s.sens || []) { add(x.budget); if (x.objectives) { const o = x.objectives.mean; mt(o.unknown_count ? null : o.weighted_sum_mm / W); } }
  for (const r of (s.man.feasibility.reasons || []).concat(s.res.reasons || [])) for (const n of String(r.text).match(/\d+/g) || []) A.add(n);
  return A;
}
test("E1_numbers_from_result", "все числа explainPlans — значения сценария/результата (6 фикстур)", () => {
  const bad = {};
  for (const n of ["real_shymkent_school", "real_astana_clinic", "synthetic_empty_sources", "synthetic_infeasible_required", "synthetic_tie_same_winners", "synthetic_radius_boundary"]) {
    const s = solve(r8(n)), A = allowedNumbers(s);
    const nums = s.text().replace(/Отпечаток [0-9a-f]+\./, "").replace(/[\p{L}_.-]*\d[\p{L}\d_.-]*-[\p{L}\d_.-]*/gu, "").match(/\d+(?:,\d+)?/g) || [];
    const extra = nums.filter((x) => !A.has(x)); if (extra.length) bad[n] = extra;
  }
  return { pass: Object.keys(bad).length === 0, observed: bad };
});
test("E2_unknown_not_zero", "пустой срез: среднее/худшая = «нет данных», сказано «неизвестно, а не равно нулю», нет «0 м»", () => {
  const t = solve(r8("synthetic_empty_sources")).text();
  return { pass: /взвешенное среднее нет данных, худшая точка нет данных/.test(t) && /неизвестно, а не равно нулю/.test(t) && !/ 0 м/.test(t), observed: t.split("\n").slice(1, 3) };
});
test("E3_coincident_labelled", "совпавшие стратегии подписаны: Астана — одна для всех целей; Шымкент — «Охват» = «Среднее», minimax отличается", () => {
  const a = solve(r8("real_astana_clinic")).text(), sh = solve(r8("real_shymkent_school")).text(), t = solve(r8("synthetic_tie_same_winners")).text();
  const ok = /Все три цели выбрали один и тот же план/.test(a) && /«Охват» совпал со «Средним»/.test(sh) && /Почему планы разные: «Худшая точка»/.test(sh) && /Все три цели выбрали один и тот же план/.test(t);
  return { pass: ok, observed: sh.split("\n").filter((l) => /совпал|разные|Все три/.test(l)) };
});
test("E4_old_digest_rejected", "старый digest: смена бюджета/выбора/подмена числа результата → stale_explanation", () => {
  const s = solve(r8("real_shymkent_school"));
  const tampered = JSON.parse(JSON.stringify(s.res)); tampered.objectives.mean.max_mm += 1000;
  const codes = [code(() => PL.explainPlans({ ...s.sc, budget: s.sc.budget - 1 }, s.man, s.res, s.sens, s.digest, F)),
    code(() => PL.explainPlans({ ...s.sc, selected_ids: [] }, s.man, s.res, s.sens, s.digest, F)),
    code(() => PL.explainPlans(s.sc, s.man, tampered, s.sens, s.digest, F))];
  return { pass: codes.every((c) => c === "stale_explanation"), observed: codes };
});
test("E5_result_of_other_problem", "результат оптимизации ДРУГОЙ задачи с пересчитанным digest отклоняется самим explainPlans", () => {
  const a = solve(r8("real_shymkent_school")), b = solve(r8("real_shymkent_school"), { coverage_radius_m: 600, budget: 130 });
  const d = PL.explanationDigest(b.sc, b.man, a.res, b.sens, F);
  const c = code(() => PL.explainPlans(b.sc, b.man, a.res, b.sens, d, F));
  return { pass: c !== "accepted", observed: { code: c, result_problem_digest_matches: a.res.problem_digest === PL.problemDigest(b.sc, F) } };
});
test("E6_manual_of_other_selection", "оценка ручного плана для другого selected_ids с пересчитанным digest отклоняется самим explainPlans", () => {
  const s = solve(r8("real_shymkent_school")), other = PL.evaluatePlan(s.ctx, s.sc, ["c-sev"]);
  const d = PL.explanationDigest(s.sc, other, s.res, s.sens, F);
  const c = code(() => PL.explainPlans(s.sc, other, s.res, s.sens, d, F));
  return { pass: c !== "accepted", observed: { code: c, sc_selected: s.sc.selected_ids, manual_selected: other.selected_ids } };
});
test("E7_infeasible_explained", "infeasible: «Допустимых планов нет … Ограничения не снимались автоматически»", () => {
  const t = solve(r8("synthetic_infeasible_required")).text();
  return { pass: /Допустимых планов нет: .+\. Ограничения не снимались автоматически\./.test(t), observed: t.split("\n").filter((l) => /Допустим/.test(l)) };
});
test("E8_report_html", "reportHtml: null → «нет данных», экранирование, без скриптов/внешних ссылок, объяснение помечено шаблоном", () => {
  const s = solve(r8("synthetic_empty_sources")), evil = `<img src=x onerror=alert(1)>"'&`;
  const html = PL.reportHtml({ scenario: s.sc, city_label: evil, release: "synthetic", problem_digest: "p", scenario_digest: "s", generated: "t",
    manual: s.man, result: s.res, sens: s.sens, explanation: s.text(), names: {}, attribution: evil, demo: true });
  const ok = !/<img|<script|onerror=|https?:\/\//i.test(html.replace(/&lt;img src=x onerror=alert\(1\)&gt;/g, "")) && /&lt;img/.test(html)
    && /Взвешенное среднее<\/td><td>нет данных/.test(html) && /Объяснение \(шаблон, не LLM\)/.test(html);
  return { pass: ok, observed: (html.match(/Взвешенное среднее<\/td><td>[^<]*/) || [""])[0] };
});
finish("s1_build_explain", { build_sha: "d865dd4a124291e10dd0b7bb1d9eada20d34c268" });
