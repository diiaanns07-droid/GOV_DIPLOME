/* PROPOSAL by K10 (round 9), not part of the BUILD: city-resilience-v1 as a small layer over the existing web/plan.js.
 * Intended place: prototypes/city-evidence/web/resilience.js (loaded after whatif.js and plan.js). Only BUILD may add it.
 * Re-uses plan.js validation, precompute (haversine-mm-v1, once per case), evaluatePlan and feasibility; adds only the
 * envelope checks, per-case baselines, the worst vector and the robust search (research/round-9/CORE_SPEC.txt).
 * A case means "compute as if these source records were not in the slice"; it does not claim a closure.
 * Tested headless against the K10 resilience packs by research/round-9-results/K10/tests/run_res_adapter.cjs.
 */
(function (root) {
  "use strict";
  const node = typeof module !== "undefined" && module.exports;
  const PL = node ? require("./plan.js") : root.CITY_PLAN;
  const SCHEMA = "city-resilience-v1", OBJECTIVE = "worst-lex-v1", METRIC = PL.METRIC;
  const LIMITS = { candidates: 12, user_cases: 7, label: 120 };
  const ID_CHARS = /^[\p{L}\p{N}_.-]+$/u;
  const idOk = (v) => typeof v === "string" && v.normalize("NFC") === v && [...v].length >= 1 && [...v].length <= 64 && ID_CHARS.test(v);
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const cmpLex = (a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) { if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; } return a.length - b.length; };
  const cmpIds = (a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = cmpStr(a[i], b[i]); if (c) return c; } return a.length - b.length; };
  const deepFreeze = (o) => { if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.freeze(o); for (const v of Object.values(o)) deepFreeze(v); } return o; };
  class ResilienceError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const fail = (code, d) => { throw new ResilienceError(code, d); };
  const VALID = new WeakSet();  // envelopes returned by validateResilience (deep-frozen, so they cannot be changed later)

  // ---------- validation of the whole envelope before any computation ----------
  function validateResilience(input, ctx) {
    if (!input || typeof input !== "object" || Array.isArray(input)) fail("bad_shape", "ожидается объект");
    const keys = Object.keys(input).sort().join(",");
    if (keys !== "cases,plan,schema_version") fail("bad_shape", `поля ${keys.slice(0, 80)} ≠ schema_version, plan, cases`);
    if (input.schema_version !== SCHEMA) fail("bad_version", String(input.schema_version).slice(0, 40));
    const plan = input.plan;
    if (plan && typeof plan === "object" && Object.prototype.hasOwnProperty.call(plan, "derived_results"))
      fail("derived_not_allowed", "в city-resilience-v1 производные поля не принимаются");
    const sc = PL.validatePlanScenario(plan, ctx);  // all city-plan-v2 rules of the BUILD (throws PlanError)
    if (sc.candidates.length > LIMITS.candidates)
      fail("too_many_candidates", `анализ устойчивости: не больше ${LIMITS.candidates} кандидатов, получено ${sc.candidates.length}`);
    const cases = input.cases;
    if (!Array.isArray(cases) || cases.length < 1 || cases.length > LIMITS.user_cases) fail("bad_cases", `случаев 1..${LIMITS.user_cases} (base добавляется сам)`);
    const sources = new Set(ctx.places.filter((p) => p.group === sc.category).map((p) => p.id));
    const candIds = new Set(sc.candidates.map((c) => c.id));
    const seen = new Set(), out = [];
    cases.forEach((c, k) => {
      if (!c || typeof c !== "object" || Array.isArray(c) || Object.keys(c).sort().join(",") !== "disabled_source_ids,id,label") fail("bad_shape", `cases[${k}]`);
      if (!idOk(c.id)) fail("bad_id", `cases[${k}].id`);
      if (c.id === "base") fail("reserved_case_id", "base добавляется автоматически");
      if (seen.has(c.id)) fail("duplicate_case_id", c.id);
      seen.add(c.id);
      const lab = c.label;
      if (typeof lab !== "string" || !lab.trim() || [...lab].length > LIMITS.label || /\p{Cc}/u.test(lab)) fail("bad_label", `cases[${k}].label`);
      const ds = c.disabled_source_ids;
      if (!Array.isArray(ds) || ds.length < 1) fail("bad_disabled", `cases[${k}]: хотя бы одна исходная запись`);
      if (!ds.every((x) => typeof x === "string")) fail("bad_id", `cases[${k}].disabled_source_ids`);
      if (new Set(ds).size !== ds.length) fail("duplicate_id", `cases[${k}].disabled_source_ids`);
      for (const x of ds) if (!sources.has(x)) fail(candIds.has(x) ? "candidate_id_not_source" : "unknown_source_id", `cases[${k}]: ${String(x).slice(0, 40)}`);
      out.push({ id: c.id, label: lab, disabled_source_ids: ds.slice().sort(cmpStr) });
    });
    out.sort((a, b) => cmpStr(a.id, b.id));
    const env = deepFreeze({ schema_version: SCHEMA, plan: sc, cases: [{ id: "base", label: "base", disabled_source_ids: [] }, ...out] });
    VALID.add(env);
    return env;
  }
  const checked = (ctx, env) => (VALID.has(env) ? env : validateResilience(env, ctx));

  // ---------- digests (order of cases/ids does not matter; selected_ids only in the scenario digest) ----------
  const canonCases = (env) => env.cases.map((c) => [c.id, c.label, c.disabled_source_ids.slice().sort(cmpStr)]).sort((a, b) => cmpStr(a[0], b[0]));
  const resilienceProblemDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, METRIC, OBJECTIVE, PL.problemDigest(env.plan, F), canonCases(env)]));
  const resilienceScenarioDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([resilienceProblemDigest(env, F), env.plan.selected_ids.slice().sort(cmpStr)]));
  const exclusionsDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify(canonCases(env).map((c) => [c[0], c[2]])));

  // ---------- per case: the slice without the left-out records (the context itself is never changed) ----------
  function prepare(ctx, env) {
    return env.cases.map((c) => {
      const off = new Set(c.disabled_source_ids);
      const cctx = { city_id: ctx.city_id, bbox: ctx.bbox, source_snapshot: ctx.source_snapshot, places: ctx.places.filter((p) => !off.has(p.id)) };
      const P = PL.precompute(cctx, env.plan);
      return { id: c.id, label: c.label, disabled_source_ids: c.disabled_source_ids, ctx: cctx, P, records: P.src.length };
    });
  }
  const lossOf = (m) => [m.unknown_count, m.weighted_sum_mm, m.max_mm === null ? Infinity : m.max_mm];
  const lossOut = (l) => [l[0], l[1], l[2] === Infinity ? null : l[2]];
  function worstOf(losses, ids) {
    let w = losses[0];
    for (const l of losses) if (cmpLex(l, w) > 0) w = l;
    return { w, ids: ids.filter((_, k) => cmpLex(losses[k], w) === 0).sort(cmpStr) };
  }

  /* evaluateResilience(ctx, envelope, selectedIds) -> { selected_ids, cost, per_case[], worst_vector, worst_case_ids, feasibility } */
  function evaluateResilience(ctx, envIn, selectedIds, prep) {
    const env = checked(ctx, envIn), C = prep || prepare(ctx, env);
    const per = C.map((c) => {
      const e = PL.evaluatePlan(c.ctx, env.plan, selectedIds, c.P);
      return { case_id: c.id, label: c.label, disabled_source_ids: c.disabled_source_ids, baseline_records: c.records, metrics: e.metrics, rows: e.rows };
    });
    const losses = per.map((p) => lossOf(p.metrics)), wo = worstOf(losses, per.map((p) => p.case_id));
    const ids = [...new Set(selectedIds)].sort(cmpStr), f = PL.feasibility(env.plan, ids);
    per.forEach((p, k) => { p.loss = lossOut(losses[k]); });
    return { selected_ids: ids, cost: f.cost, per_case: per, worst_vector: lossOut(wo.w), worst_case_ids: wo.ids,
      feasibility: { feasible: f.feasible, reasons: f.reasons } };
  }

  /* createResilienceSearch(ctx, envelope, {F, request_id}) -> { total, examined, step(n) -> done, cancel(), result() }
   * Exact enumeration of at most 2^12 sets; distances come from the per-case precompute, no haversine inside the loop. */
  function createResilienceSearch(ctx, envIn, opts) {
    const env = checked(ctx, envIn), sc = env.plan, F = opts && opts.F, request_id = opts && opts.request_id !== undefined ? opts.request_id : null;
    const C = prepare(ctx, env), P0 = C[0].P, nP = P0.pts.length, nC = P0.cands.length;
    const weights = P0.pts.map((p) => p.weight), radiusMm = sc.coverage_radius_m * 1000;
    const req = sc.required_ids.map((id) => P0.candIndex.get(id)), exc = new Set(sc.excluded_ids.map((id) => P0.candIndex.get(id)));
    const free = []; for (let i = 0; i < nC; i++) if (!req.includes(i) && !exc.has(i)) free.push(i);
    const reqCost = req.reduce((s, i) => s + P0.cands[i].cost, 0), slots = sc.max_selected - req.length;
    const reasons = [];
    if (req.length > sc.max_selected) reasons.push({ code: "required_exceeds_max_selected", text: `обязательных ${req.length} > ${sc.max_selected}` });
    if (reqCost > sc.budget) reasons.push({ code: "required_cost_exceeds_budget", text: `обязательные стоят ${reqCost} > бюджета ${sc.budget}` });
    const total = reasons.length ? 0 : 2 ** free.length;
    const baseMm = C.map((c) => c.P.base.map((b) => (b ? b.mm : Infinity)));
    const dist = P0.dist.map((row) => row.map((d) => d.mm));
    const idsOf = (m) => { const ids = req.map((i) => P0.cands[i].id); free.forEach((i, k) => { if (m & (1 << k)) ids.push(P0.cands[i].id); }); return ids.sort(cmpStr); };
    let mask = 0, examined = 0, feasible = 0, cancelled = false, nominal = null, robust = null;
    const after = new Float64Array(nP);
    function lossFor(k, sel) {
      after.set(baseMm[k]);
      for (const i of sel) { const d = dist[i]; for (let j = 0; j < nP; j++) if (d[j] < after[j]) after[j] = d[j]; }
      let unknown = 0, wsum = 0, max = 0;
      for (let j = 0; j < nP; j++) { const a = after[j]; if (a === Infinity) { unknown++; continue; } wsum += weights[j] * a; if (a > max) max = a; }
      return [unknown, wsum, unknown ? Infinity : max];
    }
    function step(n) {
      if (cancelled || reasons.length) return true;
      const end = Math.min(total, mask + n);
      for (; mask < end; mask++) {
        examined++;
        let cnt = 0, cost = reqCost;
        const sel = req.slice();
        free.forEach((i, k) => { if (mask & (1 << k)) { cnt++; cost += P0.cands[i].cost; sel.push(i); } });
        if (cnt > slots || cost > sc.budget) continue;
        feasible++;
        const losses = C.map((_, k) => lossFor(k, sel));
        let w = losses[0]; for (const l of losses) if (cmpLex(l, w) > 0) w = l;
        const nk = [...losses[0], cost], rk = [...w, ...losses[0], cost];
        if (!nominal || cmpLex(nk, nominal.k) < 0 || (cmpLex(nk, nominal.k) === 0 && cmpIds(idsOf(mask), idsOf(nominal.mask)) < 0)) nominal = { k: nk, mask };
        if (!robust || cmpLex(rk, robust.k) < 0 || (cmpLex(rk, robust.k) === 0 && cmpIds(idsOf(mask), idsOf(robust.mask)) < 0)) robust = { k: rk, mask };
      }
      return mask >= total;
    }
    function result() {
      const head = { schema_version: SCHEMA, metric_version: METRIC, objective_version: OBJECTIVE, request_id, source_snapshot: sc.source_snapshot,
        resilience_problem_digest: F ? resilienceProblemDigest(env, F) : null, resilience_scenario_digest: F ? resilienceScenarioDigest(env, F) : null,
        exclusions_digest: F ? exclusionsDigest(env, F) : null, case_ids: env.cases.map((c) => c.id), evaluated: examined, total_subsets: total,
        feasible_count: feasible, manual: evaluateResilience(ctx, env, sc.selected_ids, C) };
      if (reasons.length || (mask >= total && !feasible && !cancelled))
        return { ...head, status: "infeasible", reasons: reasons.length ? reasons : [{ code: "no_feasible_set", text: "нет допустимых наборов" }],
          nominal: null, robust: null, plans_identical: null, price_of_robustness_m: null, price_reason: "нет допустимого плана" };
      if (cancelled || mask < total)
        return { ...head, status: cancelled ? "cancelled" : "incomplete", reasons: [], nominal: null, robust: null, plans_identical: null,
          price_of_robustness_m: null, price_reason: "поиск не завершён" };
      const nom = evaluateResilience(ctx, env, idsOf(nominal.mask), C), rob = evaluateResilience(ctx, env, idsOf(robust.mask), C);
      const a = rob.per_case[0].metrics.weighted_mean_mm, b = nom.per_case[0].metrics.weighted_mean_mm;
      return { ...head, status: "optimal", reasons: [], nominal: nom, robust: rob, plans_identical: cmpIds(nom.selected_ids, rob.selected_ids) === 0,
        price_of_robustness_m: a === null || b === null ? null : (a - b) / 1000,
        price_reason: a === null || b === null ? "среднее на base неизвестно для обычного или устойчивого плана" : null };
    }
    return { get total() { return total; }, get examined() { return examined; }, step, cancel: () => { cancelled = true; }, result, request_id };
  }
  function optimizeResilience(ctx, env, opts) { const s = createResilienceSearch(ctx, env, opts); while (!s.step(1 << 12)); return s.result(); }

  const api = { SCHEMA, OBJECTIVE, METRIC, LIMITS, ResilienceError, validateResilience, evaluateResilience, createResilienceSearch,
    optimizeResilience, resilienceProblemDigest, resilienceScenarioDigest, exclusionsDigest };
  if (node) module.exports = api; else root.CITY_RESILIENCE = api;
})(typeof window !== "undefined" ? window : globalThis);
