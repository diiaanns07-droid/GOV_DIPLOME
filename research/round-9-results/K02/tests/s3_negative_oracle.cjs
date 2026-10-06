// K02 r9 этап 3: независимый Python-оракул устойчивости + негативные fixtures. node tests/s3_negative_oracle.cjs --app-root <app>
const fs = require("fs"), path = require("path");
const { F, PL, R, RF, r8, ctxFor, resFixture, resSolve, test, finish, code, HERE } = require("./res_common.cjs");
const clone = (x) => JSON.parse(JSON.stringify(x));
const fid = (b, p) => `${b.city}/${b.scenario}/${p}`;

for (const n of ["res_shymkent_school", "res_astana_clinic", "res_synthetic_infeasible", "res_synthetic_tie"]) {
  test(`O_${n}`, "результат = Python-оракул (обычный/устойчивый/худшие векторы/все худшие случаи/по случаям/цена/ручной)", () => {
    const e = JSON.parse(fs.readFileSync(path.join(HERE, "expected", n + ".json"), "utf8")), s = resSolve(n), mism = [];
    const eq = (k, a, b) => { if (JSON.stringify(a) !== JSON.stringify(b)) mism.push({ k, js: a, oracle: b }); };
    const cmpPlan = (k, js, o) => { eq(k + ".ids", js.selected_ids, o.selected_ids); eq(k + ".W", [js.worst_vector.unknown_count, js.worst_vector.weighted_sum_mm, js.worst_vector.max_mm], o.worst_vector);
      eq(k + ".worst_ids", js.worst_case_ids, o.worst_case_ids);
      for (const pc of js.per_case) for (const m of ["unknown_count", "weighted_sum_mm", "weighted_mean_mm", "max_mm", "covered_weight", "cost"]) eq(`${k}.${pc.case_id}.${m}`, pc.metrics[m], o.per_case[pc.case_id][m]); };
    eq("status", s.opt.status, e.status); eq("feasible_count", s.opt.feasible_count, e.feasible_count); eq("price", s.opt.price_of_robustness_m, e.price_m);
    if (e.status === "optimal") { cmpPlan("nominal", s.opt.nominal, e.nominal); cmpPlan("robust", s.opt.robust, e.robust); }
    cmpPlan("manual", s.man, e.manual); eq("manual.feasible", s.man.feasible, e.manual.feasible);
    return { pass: mism.length === 0, observed: mism.slice(0, 4) };
  });
}

const neg = JSON.parse(fs.readFileSync(path.join(HERE, "fixtures/negative.json"), "utf8")).cases, exp = Object.fromEntries(neg.map((c) => [c.id, c.expect]));
const deps = { F };
const base = () => resSolve("res_shymkent_school");
const run = {
  N01_tampered_fact_value: () => { const s = base(); s.built.catalog.get(fid(s.built, "price.robustness")).value = 1.5; return code(() => s.text()); },
  N02_tampered_fact_name: () => { const s = base(); s.built.catalog.get(fid(s.built, "case.c1.excluded_ids")).names[0] = "Школа закрыта"; return code(() => s.text()); },
  N03_tampered_case_exclusion: () => { const s = base(), s2 = resSolve("res_shymkent_school", (env) => { env.cases[0].disabled_source_ids = env.cases[1].disabled_source_ids; });
    return code(() => RF.explain(s.built, "ru", deps, s2.req)); },
  N04_digest_swap: () => { const s = base(), o = resSolve("res_shymkent_school", (env) => { env.plan.coverage_radius_m = 600; }); return code(() => RF.explain(s.built, "ru", deps, o.req)); },
  N05_old_selector_plan: () => { const s = base(), s2 = resSolve("res_shymkent_school", (env) => { env.plan.selected_ids = ["c-sev"]; });
    const plan = RF.StubSelector.select(RF.view(s.built), s.built.digest); return code(() => F.validatePlan(plan, s2.built)); },
  N06_duplicate_fact_in_plan: () => { const s = base(), id = fid(s.built, "plan.nominal.worst.max");
    return code(() => F.validatePlan({ sections: [{ type: "summary", fact_ids: [id] }, { type: "risks", fact_ids: [id] }], catalog_digest: s.built.digest }, s.built)); },
  N07_engine_case_order: () => { const s = base(), o = clone(s.opt); o.robust.per_case.reverse(); return code(() => RF.buildResilienceCatalog(s.norm, s.man, o, s.names, deps, s.req)); },
  N08_engine_unknown_worst_case: () => { const s = base(), o = clone(s.opt); o.nominal.worst_case_ids = ["закрыто-всё"]; return code(() => RF.buildResilienceCatalog(s.norm, s.man, o, s.names, deps, s.req)); },
  N09_same_plans_nonzero_price: () => { const s = resSolve("res_astana_clinic"), o = clone(s.opt); o.price_of_robustness_m = 5; return code(() => RF.buildResilienceCatalog(s.norm, s.man, o, s.names, deps, s.req)); },
  N10_price_inconsistent: () => { const s = base(), o = clone(s.opt); o.price_of_robustness_m += 10; return code(() => RF.buildResilienceCatalog(s.norm, s.man, o, s.names, deps, s.req)); },
  N11_incomplete_claims_optimal_plans: () => { const s = base(), o = clone(s.opt); o.status = "incomplete"; o.price_of_robustness_m = null; return code(() => RF.buildResilienceCatalog(s.norm, s.man, o, s.names, deps, s.req)); },
  N12_incomplete_honest: () => { const s = base(), o = { ...clone(s.opt), status: "incomplete", nominal: null, robust: null, price_of_robustness_m: null, price_reason: undefined };
    const b = RF.buildResilienceCatalog(s.norm, s.man, o, s.names, deps, s.req), t = RF.explain(b, "ru", deps, s.req).text;
    return /статус incomplete/.test(t) && /нет данных \(поиск не завершён — оптимум не заявляется\)/.test(t) && !/Обычный план/.test(t) ? "accepted: «поиск не завершён», цена «нет данных (поиск не завершён…)»" : "wrong: " + t.slice(0, 200); },
  N13_manual_other_selection: () => { const s = base(), other = R.evaluateResilience(s.ctx, s.norm, ["c-sev"], PL); return code(() => RF.buildResilienceCatalog(s.norm, other, s.opt, s.names, deps, s.req)); },
  N14_case_id_base_reserved: () => code(() => resSolve("res_shymkent_school", (env) => { env.cases[0].id = "base"; })),
  N15_duplicate_case_id: () => code(() => resSolve("res_shymkent_school", (env) => { env.cases[1].id = env.cases[0].id; })),
  N16_candidate_id_as_source: () => code(() => resSolve("res_shymkent_school", (env) => { env.cases[0].disabled_source_ids = ["c-sev"]; })),
  N17_unknown_baseline_no_sources: () => { const fx = r8("synthetic_empty_sources"), ctx = ctxFor(fx);
    const env = { schema_version: "city-resilience-v1", plan: { ...fx.scenario, source_snapshot: ctx.source_snapshot }, cases: [{ id: "x", label: "нечего исключать", disabled_source_ids: [] }] };
    return code(() => R.normaliseEnvelope(env, ctx, PL)); },
  N18_too_many_candidates: () => code(() => resSolve("res_shymkent_school", (env, ctx) => {
    const c0 = env.plan.candidates[0]; for (let i = env.plan.candidates.length; i < 13; i++) env.plan.candidates.push({ ...c0, id: "extra-" + i }); })),
};
for (const c of neg) test(c.id, `${c.mutation} → ${c.expect}`, () => { const got = run[c.id](); return { pass: got === exp[c.id], observed: got }; });
finish("s3_negative_oracle", { note: "движок устойчивости в BUILD отсутствует; проверяются адаптер K02 и генератор resilience_ref поверх plan.js сборки" });
