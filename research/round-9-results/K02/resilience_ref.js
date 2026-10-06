/* K02 r9: генератор РЕЗУЛЬТАТОВ устойчивости для фикстур (city-resilience-v1, CORE_SPEC r9) поверх движка СБОРКИ.
 * Не второй движок: все расстояния/метрики/допустимость — PL.precompute/evaluatePlan/optimizePlans из web/plan.js;
 * здесь только фильтр исходных записей по случаю (копия ctx, исходный не мутируется), лексикографический W и выбор устойчивого.
 * Нужен потому, что в BUILD d865dd4 ещё нет web/resilience.js. Формат вывода = API CORE_SPEC (evaluateResilience/optimizeResilience).
 */
"use strict";
const SCHEMA = "city-resilience-v1", OBJECTIVE = "worst-lex-v1", MAX_CANDS = 12;
const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
class ResilienceError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
const bad = (c, d) => { throw new ResilienceError(c, d); };

// Минимальная проверка envelope для фикстур (полная validateResilience — задача BUILD).
function normaliseEnvelope(env, ctx, PL) {
  if (!env || env.schema_version !== SCHEMA) bad("bad_version", String(env && env.schema_version));
  const sc = PL.validatePlanScenario(env.plan, ctx);
  if (sc.candidates.length > MAX_CANDS) bad("too_many_candidates", `${sc.candidates.length} > ${MAX_CANDS}`);
  const src = new Set(ctx.places.filter((p) => p.group === sc.category).map((p) => p.id));
  if (!Array.isArray(env.cases) || env.cases.length < 1 || env.cases.length > 7) bad("bad_cases", "1..7 пользовательских случаев");
  const ids = new Set(["base"]), cases = [{ id: "base", label: "Все исходные записи", disabled_source_ids: [] }];
  for (const c of env.cases) {
    if (typeof c.id !== "string" || ids.has(c.id)) bad("duplicate_case", String(c.id));
    if (typeof c.label !== "string" || !c.label.length || [...c.label].length > 120 || /[\u0000-\u001f\u007f]/.test(c.label)) bad("bad_label", c.id);
    const d = c.disabled_source_ids;
    if (!Array.isArray(d) || d.length < 1 || d.length > src.size || new Set(d).size !== d.length) bad("bad_exclusion", c.id);
    for (const s of d) if (!src.has(s)) bad("unknown_source", `${c.id}: ${s}`);
    ids.add(c.id); cases.push({ id: c.id, label: c.label, disabled_source_ids: d.slice().sort(cmpStr) });
  }
  return { sc, cases };
}

const caseCtx = (ctx, c) => (c.disabled_source_ids.length ? { ...ctx, places: ctx.places.filter((p) => !c.disabled_source_ids.includes(p.id)) } : ctx);
const L = (m) => [m.unknown_count, m.weighted_sum_mm, m.max_mm === null ? Infinity : m.max_mm];
const cmpVec = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; return 0; };
const cmpIds = (a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = cmpStr(a[i], b[i]); if (c) return c; } return a.length - b.length; };

function evaluateResilience(ctx, norm, selectedIds, PL, pres) {
  const per_case = norm.cases.map((c, i) => {
    const cc = caseCtx(ctx, c), ev = PL.evaluatePlan(cc, norm.sc, selectedIds, pres ? pres[i] : undefined);
    return { case_id: c.id, metrics: { ...ev.metrics }, sources_in_case: ev.source_candidates };
  });
  let worst = null;
  for (const pc of per_case) { const v = L(pc.metrics); if (!worst || cmpVec(v, worst) > 0) worst = v; }
  const worst_case_ids = per_case.filter((pc) => cmpVec(L(pc.metrics), worst) === 0).map((pc) => pc.case_id).sort(cmpStr);
  const ev0 = PL.evaluatePlan(ctx, norm.sc, selectedIds);
  return { selected_ids: ev0.selected_ids, feasible: ev0.feasibility.feasible, infeasible_reasons: ev0.feasibility.reasons, per_case,
    worst_vector: { unknown_count: worst[0], weighted_sum_mm: worst[1], max_mm: worst[2] === Infinity ? null : worst[2] }, worst_case_ids };
}

function optimizeResilience(ctx, norm, PL, F) {
  const sc = norm.sc, pres = norm.cases.map((c) => PL.precompute(caseCtx(ctx, c), sc));
  const nominalRes = PL.optimizePlans(ctx, sc, { F });
  const digest = resilienceProblemDigest(norm, PL, F);
  const base = { resilience_problem_digest: digest, metric_version: PL.METRIC, objective_version: OBJECTIVE };
  if (nominalRes.status !== "optimal") return { ...base, status: nominalRes.status, reasons: nominalRes.reasons, nominal: null, robust: null, evaluated: 0, feasible_count: 0, price_of_robustness_m: null, price_reason: "infeasible" };
  const free = sc.candidates.map((c) => c.id).filter((id) => !sc.required_ids.includes(id) && !sc.excluded_ids.includes(id)).sort(cmpStr);
  let best = null, evaluated = 0, feasible = 0;
  for (let mask = 0; mask < 1 << free.length; mask++) {
    const ids = sc.required_ids.slice(); free.forEach((id, j) => { if (mask & (1 << j)) ids.push(id); }); ids.sort(cmpStr); evaluated++;
    if (!PL.feasibility(sc, ids).feasible) continue;
    feasible++;
    const r = evaluateResilience(ctx, norm, ids, PL, pres), W = L(r.worst_vector), Lb = L(r.per_case[0].metrics);
    const key = [...W, ...Lb, r.per_case[0].metrics.cost];
    if (!best || cmpVec(key, best.key) < 0 || (cmpVec(key, best.key) === 0 && cmpIds(ids, best.ids) < 0)) best = { key, ids, r };
  }
  const nominal = evaluateResilience(ctx, norm, nominalRes.objectives.mean.ids, PL, pres), robust = best.r;
  const nm = nominal.per_case[0].metrics.weighted_mean_mm, rm = robust.per_case[0].metrics.weighted_mean_mm;
  const price = nm === null || rm === null ? null : (rm - nm) / 1000;
  return { ...base, status: "optimal", reasons: [], nominal, robust, evaluated, feasible_count: feasible, price_of_robustness_m: price,
    price_reason: price === null ? "unknown_base_mean" : null };
}

function resilienceProblemDigest(norm, PL, F) {
  const cases = norm.cases.map((c) => [c.id, c.label, c.disabled_source_ids.slice().sort(cmpStr)]).sort((a, b) => cmpStr(a[0], b[0]));
  return "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, OBJECTIVE, PL.METRIC, PL.problemDigest(norm.sc, F), cases]));
}

module.exports = { SCHEMA, OBJECTIVE, ResilienceError, normaliseEnvelope, evaluateResilience, optimizeResilience, resilienceProblemDigest, caseCtx };
