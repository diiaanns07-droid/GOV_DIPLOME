// Этап 2: рендерер ru/kk, stale problem digest, duplicate IDs. node tests/stage2_render.cjs --app-root <app>
const { fixture, solve, P, E, F, deps, test, finish, attempt } = require("./common.cjs");
const ex = (s, lang, pd) => P.explain(s.built, lang, deps, { problem_digest: pd === undefined ? s.opt.problem_digest : pd });

test("R1_stale_problem_digest", "объяснение для старой задачи отклоняется (stale_problem), в т.ч. результат worker от другой задачи", () => {
  const fx = fixture("real_shymkent_school"), a = solve(fx), b = solve(fx, { coverage_radius_m: 600 });
  const r1 = attempt(() => ex(b, "ru", a.opt.problem_digest)).status;
  const r2 = attempt(() => P.buildPlanCatalog(b.ctx, b.sc, b.man, b.base, a.opt, deps, { problem_digest: b.opt.problem_digest })).status;
  return { pass: r1 === "stale_problem" && r2 === "stale_problem" && a.opt.problem_digest !== b.opt.problem_digest, observed: [r1, r2] };
});
test("R2_stale_catalog_plan", "план селектора по старому каталогу (смена весов/required/ручного набора) отклоняется stale_catalog", () => {
  const fx = fixture("real_shymkent_school"), a = solve(fx), plan = P.StubSelector.select(P.view(a.built), a.built.digest);
  const w = fx.scenario.control_points.map((p, i) => (i === 0 ? { ...p, weight: 9 } : p));
  const variants = [solve(fx, { control_points: w }), solve(fx, { required_ids: ["c-park"] }), solve(fx, { selected_ids: ["c-sev"] })];
  const codes = variants.map((v) => attempt(() => F.validatePlan(plan, v.built)).status);
  return { pass: codes.every((c) => c === "stale_catalog"), observed: codes };
});
test("R3_duplicate_ids", "дубликаты: точки, кандидаты, selected/required и факт в двух секциях — отказ duplicate_id", () => {
  const fx = fixture("real_shymkent_school"), sc = fx.scenario, codes = [];
  codes.push(attempt(() => E.validatePlanScenario({ ...sc, control_points: [sc.control_points[0], { ...sc.control_points[1], id: sc.control_points[0].id }] }, fx.context)).status);
  codes.push(attempt(() => E.validatePlanScenario({ ...sc, candidates: [sc.candidates[0], { ...sc.candidates[1], id: sc.candidates[0].id }] }, fx.context)).status);
  codes.push(attempt(() => E.validatePlanScenario({ ...sc, selected_ids: ["c-sev", "c-sev"] }, fx.context)).status);
  codes.push(attempt(() => E.validatePlanScenario({ ...sc, required_ids: ["c-yug", "c-yug"] }, fx.context)).status);
  const s = solve(fx), id = `${s.built.city}/${s.built.scenario}/plan.mean.cost`;
  codes.push(attempt(() => F.validatePlan({ sections: [{ type: "summary", fact_ids: [id] }, { type: "risks", fact_ids: [id] }], catalog_digest: s.built.digest }, s.built)).status);
  return { pass: codes.every((c) => c === "duplicate_id"), observed: codes };
});
test("R4_coincident_winners", "совпавшие победители названы одним набором (не три разных решения); различающиеся — компромисс с разностями", () => {
  const ast = ex(solve(fixture("real_astana_clinic")), "ru").text, shy = ex(solve(fixture("real_shymkent_school")), "ru").text;
  const ok = /Совпадают по набору объектов: Оптимум по среднему расстоянию = Оптимум по худшей точке = Оптимум по охвату радиуса \(k-c, k-d\)/.test(ast)
    && !/План по худшей точке сокращает/.test(ast) && /План по худшей точке сокращает расстояние для худшей точки на \d/.test(shy)
    && /Оптимум по среднему расстоянию = Оптимум по охвату радиуса/.test(shy);
  return { pass: ok, observed: shy.split("\n").filter((l) => /Совпад|сокращает/.test(l)) };
});
test("R5_infeasible_explained", "infeasible: причины задачи и ручного плана, ограничения не сняты молча; нет строк оптимумов", () => {
  const t = ex(solve(fixture("synthetic_infeasible_required")), "ru").text;
  const ok = /Задача: стоимость 500 больше бюджета 100\. Ограничения не снимаются молча/.test(t) && /не выбраны обязательные кандидаты: big/.test(t)
    && !/^Оптимум по/m.test(t) && /Ручной план \(недопустим\)/.test(t);
  return { pass: ok, observed: t.split("\n").slice(2, 6) };
});
test("R6_no_social_claims", "нет утверждений о жителях/времени/экономии/улучшении услуг вне блока ограничений (ru и kk)", () => {
  const bad = [];
  for (const n of ["real_shymkent_school", "real_astana_clinic", "synthetic_empty_sources"]) for (const lang of ["ru", "kk"]) {
    const body = ex(solve(fixture(n)), lang).text.split(lang === "ru" ? "**Ограничения**" : "**Шектеулер**")[0];
    for (const re of [/жител|население|насел/i, /минут|мин\b|пешком|walk/i, /эконом|сбереж|тенге/i, /улучш|здоров|качество жизни/i, /тұрғын|минут|үнем|денсаулық/i])
      if (re.test(body)) bad.push(`${n}/${lang}: ${re}`);
  }
  return { pass: bad.length === 0, observed: bad };
});
test("R7_numbers_from_catalog", "каждое число в тексте (кроме id сценария) — запись значения факта каталога; ru и kk содержат одинаковые числа", () => {
  const out = {}; let ok = true;
  for (const n of ["real_shymkent_school", "real_astana_clinic", "synthetic_empty_sources", "synthetic_infeasible_required"]) {
    const s = solve(fixture(n)), allowed = new Set();
    for (const f of s.built.catalog.values()) if (typeof f.value === "number") {
      allowed.add(F.formatValue(f.value)); allowed.add(F.formatValue(Math.abs(f.value))); allowed.add(F.formatValue(Math.round(f.value / 100) / 10)); allowed.add(F.formatValue(Math.round(Math.abs(f.value) / 100) / 10)); allowed.add(F.formatValue(Math.round(f.value * 1000) / 1000)); }
    for (const r of s.built.meta.infeasible_reasons.concat(s.built.meta.manual_reasons)) for (const v of [r.cost, r.budget, r.count, r.max_selected]) if (v !== undefined) allowed.add(String(v));
    const nums = (lang) => ex(s, lang).text.split("\n").slice(1).join("\n").replace(/\(\w+(?:[-,\s]+\w+)*\)$/gm, "")
      .match(/\d+(?:,\d+)?/g).filter((x) => !allowed.has(x));
    const ru = nums("ru"), kk = nums("kk"); out[n] = { ru, kk }; ok = ok && ru.length === 0 && kk.length === 0;
  }
  return { pass: ok, observed: out };
});
test("R8_selector_is_stub_not_llm", "селектор — детерминированная заглушка, помечен «не LLM»; повторный вызов даёт тот же текст", () => {
  const s = solve(fixture("real_shymkent_school")), a = ex(s, "ru"), b = ex(s, "ru");
  return { pass: /не LLM/.test(a.selector) && a.text === b.text, observed: a.selector };
});
finish("stage2_render");
