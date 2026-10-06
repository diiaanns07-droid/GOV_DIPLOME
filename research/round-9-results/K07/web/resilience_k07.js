/* K07 round 9 — small adapter «Устойчивость к допущениям» (city-resilience-v1, research/round-9/CORE_SPEC.txt) on top of
 * the BUILD module plan.js (d865dd4): validation, geometry, feasibility and metrics are BUILD's own functions
 * (validatePlanScenario, precompute, feasibility, metricsOf, problemDigest); this file only filters source records per case
 * and runs the worst-case (lexicographic) search. It is NOT a second plan.js. If BUILD ships web/resilience.js with the
 * CORE_SPEC API (window.CITY_RESILIENCE), the K07 panel uses that one instead.
 * Analysis of assumptions about the data: no probabilities, no risk, no closures, no population, no walking time.
 * Browser: window.CITY_RESILIENCE_K07 (needs plan.js, facts.js loaded first); Node: module.exports(PL).
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-resilience-v1", OBJECTIVE = "worst-lex-v1";
  const LIM = { candidates: 12, cases: 7, label: 120, subsets: 4096 };
  const ID_CHARS = /^[\p{L}\p{N}_.-]+$/u;  // the BUILD v2 ID rule (NFC, 1..64 code points)
  const okId = (v) => typeof v === "string" && v.normalize("NFC") === v && [...v].length >= 1 && [...v].length <= 64 && ID_CHARS.test(v);
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const INF = Number.POSITIVE_INFINITY;

  function make(PL) {
    class ResilienceError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
    const fail = (code, d) => { throw new ResilienceError(code, d); };
    const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
    const sourceIds = (ctx, category) => ctx.places.filter((p) => p.group === category).map((p) => p.id);

    // ---------- validation: the whole envelope before any computation ----------
    function validateResilience(input, ctx) {
      if (!isObj(input)) fail("bad_shape", "ожидается объект");
      for (const k of Object.keys(input)) if (!["schema_version", "plan", "cases"].includes(k)) fail("unknown_field", `поле ${JSON.stringify(k).slice(0, 40)} не допускается (производные поля в r9 не принимаются)`);
      if (input.schema_version !== SCHEMA) fail("bad_schema", String(input.schema_version).slice(0, 40));
      if (!isObj(input.plan)) fail("bad_shape", "plan: ожидается объект city-plan-v2");
      if (Array.isArray(input.plan.candidates) && input.plan.candidates.length > LIM.candidates)
        fail("too_many_candidates", `${input.plan.candidates.length} > ${LIM.candidates}: точный анализ устойчивости ограничен ${LIM.subsets} наборами; кандидаты не удаляются автоматически`);
      const plan = PL.validatePlanScenario(input.plan, ctx);  // BUILD's v2 rules (throws PlanError with its code)
      if (plan.candidates.length > LIM.candidates) fail("too_many_candidates", `${plan.candidates.length} > ${LIM.candidates}`);
      if (!Array.isArray(input.cases)) fail("bad_shape", "cases: ожидается массив");
      if (input.cases.length < 1 || input.cases.length > LIM.cases) fail("bad_count", `случаев ${input.cases.length}, нужно 1..${LIM.cases} (base добавляется автоматически)`);
      const src = new Set(sourceIds(ctx, plan.category)), cands = new Set(plan.candidates.map((c) => c.id)), seen = new Set();
      const cases = input.cases.map((c, i) => {
        const w = `cases[${i}]`;
        if (!isObj(c)) fail("bad_shape", `${w}: ожидается объект`);
        for (const k of Object.keys(c)) if (!["id", "label", "disabled_source_ids"].includes(k)) fail("unknown_field", `${w}.${String(k).slice(0, 30)}`);
        if (!okId(c.id)) fail("bad_id", `${w}.id`);
        if (c.id === "base") fail("reserved_id", `${w}.id: «base» зарезервирован`);
        if (seen.has(c.id)) fail("duplicate_id", `${w}.id: ${c.id}`);
        seen.add(c.id);
        if (typeof c.label !== "string" || !c.label.trim()) fail("bad_label", `${w}.label: пустая`);
        if ([...c.label].length > LIM.label) fail("bad_label", `${w}.label: больше ${LIM.label} символов`);
        if (/\p{Cc}/u.test(c.label)) fail("bad_label", `${w}.label: управляющие символы`);
        if (!Array.isArray(c.disabled_source_ids) || !c.disabled_source_ids.length) fail("bad_exclusions", `${w}: нужно хотя бы одно исключение`);
        if (c.disabled_source_ids.length > src.size) fail("bad_exclusions", `${w}: исключений больше, чем записей категории (${src.size})`);
        const ex = new Set();
        for (const id of c.disabled_source_ids) {
          if (typeof id !== "string") fail("bad_exclusions", `${w}: ID должен быть строкой`);
          if (ex.has(id)) fail("duplicate_id", `${w}: ${id.slice(0, 40)} повторяется`);
          if (!src.has(id)) fail(cands.has(id) ? "candidate_not_source" : "unknown_source", `${w}: ${id.slice(0, 40)} — ${cands.has(id) ? "это кандидат, а не исходная запись" : "нет такой исходной записи этой категории в срезе"}`);
          ex.add(id);
        }
        return { id: c.id, label: c.label, disabled_source_ids: [...ex].sort(cmpStr) };
      });
      return { schema_version: SCHEMA, plan, cases };
    }
    const allCases = (env) => [{ id: "base", label: "Исходный срез (без исключений)", disabled_source_ids: [] }, ...env.cases];

    // ---------- digests (order-independent; selected_ids only in the scenario digest) ----------
    function canonCases(env) { return env.cases.slice().sort((a, b) => cmpStr(a.id, b.id)).map((c) => [c.id, c.label, c.disabled_source_ids.slice().sort(cmpStr)]); }
    const resilienceProblemDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, PL.METRIC, OBJECTIVE, PL.problemDigest(env.plan, F), canonCases(env)]));
    const resilienceScenarioDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([resilienceProblemDigest(env, F), env.plan.selected_ids.slice().sort(cmpStr)]));

    // ---------- per-case precomputation: the context is filtered in a new object, never mutated ----------
    function prepare(ctx, env) {
      const cases = allCases(env);
      const pres = cases.map((c) => { const off = new Set(c.disabled_source_ids); return PL.precompute({ ...ctx, places: ctx.places.filter((p) => !off.has(p.id)) }, env.plan); });
      const P0 = pres[0];
      return { cases, pres, cands: P0.cands, pts: P0.pts, weights: P0.pts.map((p) => p.weight), radiusMm: env.plan.coverage_radius_m * 1000,
        base: pres.map((P) => P.base.map((b) => (b ? b.mm : null))), dist: P0.dist.map((row) => row.map((d) => d.mm)), index: P0.candIndex };
    }
    const lossOf = (m) => [m.unknown_count, m.weighted_sum_mm, m.max_mm === null ? INF : m.max_mm];
    const cmpVec = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; return 0; };
    const cmpIds = (a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = cmpStr(a[i], b[i]); if (c) return c; } return a.length - b.length; };
    const ext = (v) => v.map((x) => (x === INF ? null : x));  // strict JSON outside: null instead of infinity
    function perCase(R, idx) {
      const per = R.cases.map((c, k) => {
        const after = R.base[k].map((b, j) => { let a = b; for (const i of idx) { const d = R.dist[i][j]; if (a === null || d < a) a = d; } return a; });
        const m = PL.metricsOf(after, R.weights, R.radiusMm);
        return { case_id: c.id, label: c.label, metrics: m, loss: lossOf(m) };
      });
      let W = per[0].loss;
      for (const x of per) if (cmpVec(x.loss, W) > 0) W = x.loss;
      const worst = per.filter((x) => cmpVec(x.loss, W) === 0).map((x) => x.case_id).sort(cmpStr);
      return { per, W, worst };
    }
    const shapeOut = (pc) => ({ per_case: pc.per.map((x) => ({ case_id: x.case_id, label: x.label, metrics: x.metrics, loss: ext(x.loss) })), worst_vector: ext(pc.W), worst_case_ids: pc.worst });

    // public entry points re-validate the envelope: a mutated object can not bypass the limits (CORE_SPEC r9)
    function evaluateResilience(ctx, input, selectedIds) {
      const env = validateResilience(input, ctx), R = prepare(ctx, env), ids = [...new Set(selectedIds === undefined ? env.plan.selected_ids : selectedIds)].sort(cmpStr);
      for (const id of ids) if (!R.index.has(id)) fail("unknown_ref", `кандидата ${id} нет`);
      const f = PL.feasibility(env.plan, ids);
      return { selected_ids: ids, cost: f.cost, feasible: f.feasible, feasibility: f, ...shapeOut(perCase(R, ids.map((id) => R.index.get(id)))) };
    }

    // ---------- exact search over ≤ 4096 subsets: nominal (mean on base) and robust (W, L_base, cost, IDs) ----------
    function createResilienceSearch(ctx, input, opts) {
      const env = validateResilience(input, ctx);  // limits (≤ 12 candidates, cases) are checked before any precomputation
      const F = opts && opts.F, R = prepare(ctx, env), sc = env.plan, n = R.cands.length;
      const req = sc.required_ids.map((id) => R.index.get(id)), exc = new Set(sc.excluded_ids.map((id) => R.index.get(id)));
      const reqCost = req.reduce((s, i) => s + R.cands[i].cost, 0), reasons = [];
      if (req.length > sc.max_selected) reasons.push({ code: "required_exceeds_max_selected", text: `обязательных ${req.length} > максимума ${sc.max_selected}` });
      if (reqCost > sc.budget) reasons.push({ code: "required_cost_exceeds_budget", text: `стоимость обязательных ${reqCost} > бюджета ${sc.budget} усл. ед.` });
      const total = reasons.length ? 0 : 2 ** n;
      let mask = 0, examined = 0, feasible = 0, cancelled = false, nominal = null, robust = null;
      const digest = F ? resilienceProblemDigest(env, F) : null;
      function step(k) {
        if (cancelled || reasons.length) return true;
        const end = Math.min(total, mask + k);
        for (; mask < end; mask++) {
          examined++;
          let ok = true, cost = 0; const idx = [];
          for (let i = 0; i < n && ok; i++) if (mask & (1 << i)) { if (exc.has(i)) ok = false; cost += R.cands[i].cost; idx.push(i); }
          if (!ok || idx.length > sc.max_selected || cost > sc.budget || req.some((i) => !(mask & (1 << i)))) continue;
          feasible++;
          const pc = perCase(R, idx), ids = idx.map((i) => R.cands[i].id).sort(cmpStr), Lb = pc.per[0].loss;
          const nk = [...Lb, cost], rk = [...pc.W, ...Lb, cost];
          if (!nominal || cmpVec(nk, nominal.k) < 0 || (cmpVec(nk, nominal.k) === 0 && cmpIds(ids, nominal.ids) < 0)) nominal = { k: nk, ids, pc, cost };
          if (!robust || cmpVec(rk, robust.k) < 0 || (cmpVec(rk, robust.k) === 0 && cmpIds(ids, robust.ids) < 0)) robust = { k: rk, ids, pc, cost };
        }
        return mask >= total;
      }
      function result() {
        const base = { resilience_problem_digest: digest, metric_version: PL.METRIC, objective_version: OBJECTIVE, total_subsets: total, evaluated: examined, feasible_count: feasible };
        if (reasons.length) return { ...base, status: "infeasible", reasons, nominal: null, robust: null, price_of_robustness_m: null, price_reason: "нет допустимых планов" };
        if (cancelled || mask < total) return { ...base, status: cancelled ? "cancelled" : "incomplete", reasons: [], nominal: null, robust: null, price_of_robustness_m: null, price_reason: "поиск не завершён" };
        if (!feasible) return { ...base, status: "infeasible", reasons: [{ code: "no_feasible_plan", text: "нет допустимого набора" }], nominal: null, robust: null, price_of_robustness_m: null, price_reason: "нет допустимых планов" };
        const out = (x) => ({ selected_ids: x.ids, cost: x.cost, ...shapeOut(x.pc) });
        const mN = nominal.pc.per[0].metrics.weighted_mean_mm, mR = robust.pc.per[0].metrics.weighted_mean_mm;
        const known = mN !== null && mR !== null;
        return { ...base, status: "optimal", reasons: [], nominal: out(nominal), robust: out(robust), same_plan: nominal.ids.join("\u0000") === robust.ids.join("\u0000"),
          price_of_robustness_m: known ? (mR - mN) / 1000 : null,
          price_reason: known ? null : "среднее расстояние в исходном срезе не определено (есть точки без записи и без выбранного места)" };
      }
      return { get total() { return total; }, get examined() { return examined; }, step, cancel: () => { cancelled = true; }, result, problem_digest: digest };
    }
    function optimizeResilience(ctx, env, opts) { const s = createResilienceSearch(ctx, env, opts); while (!s.step(1 << 16)); return s.result(); }

    return { SCHEMA, OBJECTIVE, LIMITS: LIM, ResilienceError, validateResilience, evaluateResilience, createResilienceSearch, optimizeResilience,
      resilienceProblemDigest, resilienceScenarioDigest, allCases, sourceIds };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = make;
  else if (root.CITY_PLAN) root.CITY_RESILIENCE_K07 = make(root.CITY_PLAN);
})(typeof window !== "undefined" ? window : globalThis);
