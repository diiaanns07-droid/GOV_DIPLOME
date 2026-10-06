/* «Устойчивость к допущениям» — city-resilience-v1 (research/round-9/CORE_SPEC.txt). Pure module on top of plan.js.
 * The user conditionally leaves chosen source records out of the calculation in up to 7 named cases (+ the automatic
 * "base" case with nothing excluded). Each plan is evaluated in every case with that case's own baseline; the robust plan
 * minimises the lexicographically worst loss (unknown_count, weighted_sum_mm, max_mm) over all cases.
 * This is an analysis of assumptions about the DATA, not a forecast of closures, risk or residents' needs.
 * Source records, QA and the slice snapshot are never modified: each case filters a copy of the record list.
 * Geometry, limits and v2 validation are reused from plan.js (haversine-mm-v1); this file does not re-implement them.
 * Browser: window.CITY_RESILIENCE (needs facts.js, whatif.js, plan.js); Node: module.exports.
 * Independent Python oracle: tools/resilience_oracle.py (tests/resilience.cjs compares the math).
 */
(function (root) {
  "use strict";
  const node = typeof module !== "undefined" && module.exports;
  const PL = node ? require("./plan.js") : root.CITY_PLAN;
  const X = node ? require("./whatif.js") : root.CITY_WHATIF;
  const SCHEMA = "city-resilience-v1";
  const OBJECTIVE = "worst-lex-v1";
  const LIMITS = { candidates: 12, user_cases: 7, label: 120 };
  const ENV_KEYS = ["schema_version", "plan", "cases"];
  const PlanError = PL.PlanError;
  const fail = (code, d) => { throw new PlanError(code, d); };
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const CTRL = new RegExp("[\\u0000-\\u001f\\u007f-\\u009f\\u2028\\u2029]");  // control characters and line/paragraph separators

  // ---------- validation: full envelope and plan, before any precomputation or UI change ----------
  function sourcesOf(ctx, category) { return ctx.places.filter((p) => p.group === category); }
  /* validateResilience(input, ctx) -> { schema_version, plan (clean v2), cases: [{id, label, disabled_source_ids (sorted)}] }.
   * The automatic "base" case is NOT part of the input; it is added by the calculation. */
  function validateResilience(input, ctx) {
    if (!input || typeof input !== "object" || Array.isArray(input)) fail("bad_shape", "ожидается объект");
    if ("schema_version" in input && input.schema_version !== SCHEMA)
      fail(input.schema_version === PL.SCHEMA ? "wrong_version" : input.schema_version === X.SCHEMA ? "wrong_version" : "bad_version",
        input.schema_version === PL.SCHEMA ? "это план city-plan-v2 — откройте его в режиме «Несколько объектов (v2)»"
          : input.schema_version === X.SCHEMA ? "это сценарий city-whatif-v1 — откройте его в режиме «Один объект (v1)»"
            : `версия ${String(input.schema_version).slice(0, 40)} ≠ ${SCHEMA}`);
    for (const k of Object.keys(input)) if (!ENV_KEYS.includes(k)) fail("unknown_field", `поле ${JSON.stringify(k).slice(0, 40)} не допускается (производные значения в ${SCHEMA} не принимаются)`);
    for (const k of ENV_KEYS) if (!(k in input)) fail("missing_field", k);
    const plan = input.plan;
    if (!plan || typeof plan !== "object" || Array.isArray(plan)) fail("bad_shape", "plan: ожидается объект city-plan-v2");
    if ("derived_results" in plan) fail("derived_not_allowed", "plan.derived_results: в файле устойчивости производные значения не принимаются");
    // limit of this analysis before anything else is computed (v2 itself keeps its 16)
    if (Array.isArray(plan.candidates) && plan.candidates.length > LIMITS.candidates)
      fail("too_many_candidates", `для анализа устойчивости не больше ${LIMITS.candidates} кандидатов, получено ${plan.candidates.length}; кандидаты не отбрасываются автоматически`);
    const cleanPlan = PL.validatePlanScenario(plan, ctx);
    const cases = input.cases;
    if (!Array.isArray(cases)) fail("bad_shape", "cases — массив");
    if (cases.length < 1 || cases.length > LIMITS.user_cases) fail("bad_cases", `случаев 1..${LIMITS.user_cases} (плюс автоматический base), получено ${cases.length}`);
    const src = sourcesOf(ctx, cleanPlan.category), srcIds = new Set(src.map((p) => p.id)), candIds = new Set(cleanPlan.candidates.map((c) => c.id));
    const seen = new Set();
    const clean = cases.map((c, k) => {
      const what = `cases[${k}]`;
      if (!c || typeof c !== "object" || Array.isArray(c)) fail("bad_shape", `${what}: ожидается объект`);
      const ks = Object.keys(c).sort().join(",");
      if (ks !== "disabled_source_ids,id,label") fail("bad_shape", `${what}: поля {${ks.slice(0, 80)}} ≠ {id, label, disabled_source_ids}`);
      if (!PL.isId(c.id)) fail("bad_id", `${what}.id: ${JSON.stringify(c.id).slice(0, 40)}`);
      if (c.id === "base") fail("reserved_id", `${what}.id: «base» зарезервирован для автоматического случая без исключений`);
      if (seen.has(c.id)) fail("duplicate_id", `cases: ${c.id}`);
      seen.add(c.id);
      if (typeof c.label !== "string" || !c.label.trim() || [...c.label].length > LIMITS.label || CTRL.test(c.label))
        fail("bad_label", `${what}.label: непустой текст до ${LIMITS.label} символов без управляющих символов`);
      const ids = c.disabled_source_ids;
      if (!Array.isArray(ids)) fail("bad_shape", `${what}.disabled_source_ids — массив`);
      if (ids.length < 1 || ids.length > src.length) fail("bad_exclusions", `${what}: исключить можно от 1 до ${src.length} записей категории`);
      const set = new Set();
      for (const id of ids) {
        if (typeof id !== "string") fail("bad_id", `${what}: ID записи — строка`);
        if (set.has(id)) fail("duplicate_id", `${what}.disabled_source_ids: ${id.slice(0, 64)}`);
        if (candIds.has(id) && !srcIds.has(id)) fail("candidate_not_source", `${what}: ${id.slice(0, 64)} — кандидат (гипотеза), а не исходная запись`);
        if (!srcIds.has(id)) fail("unknown_source", `${what}: исходной записи ${id.slice(0, 64)} категории «${PL.CATEGORIES[cleanPlan.category]}» в срезе нет`);
        set.add(id);
      }
      return { id: c.id, label: c.label, disabled_source_ids: [...set].sort(cmpStr) };
    });
    return { schema_version: SCHEMA, plan: cleanPlan, cases: clean };
  }
  const allCases = (env) => [{ id: "base", label: "Базовый: все записи среза", disabled_source_ids: [] }, ...env.cases];
  // groups of user cases with the same exclusion set (allowed; shown to the user; do not change the result)
  function duplicateCaseGroups(env) {
    const by = new Map();
    for (const c of env.cases) { const k = JSON.stringify(c.disabled_source_ids); by.set(k, [...(by.get(k) || []), c.id]); }
    return [...by.values()].filter((g) => g.length > 1).map((g) => g.slice().sort(cmpStr));
  }

  // ---------- digests (order independent; exclusions have their own digest; snapshot is the plan's own) ----------
  const canonCases = (env) => env.cases.slice().sort((a, b) => cmpStr(a.id, b.id)).map((c) => [c.id, c.label, c.disabled_source_ids.slice().sort(cmpStr)]);
  const exclusionsDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, canonCases(env).map(([id, , ex]) => [id, ex])]));
  const resilienceProblemDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, PL.METRIC, OBJECTIVE, PL.problemDigest(env.plan, F), canonCases(env)]));
  const resilienceScenarioDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([resilienceProblemDigest(env, F), env.plan.selected_ids.slice().sort(cmpStr)]));

  // ---------- per-case precomputation: a filtered COPY of the records per case; ctx is never mutated ----------
  function caseContext(ctx, disabled) { const off = new Set(disabled); return { ...ctx, places: ctx.places.filter((p) => !off.has(p.id)) }; }
  function precomputeCases(ctx, env) {
    return allCases(env).map((c) => ({ case: c, P: PL.precompute(caseContext(ctx, c.disabled_source_ids), env.plan) }));
  }
  const lossKey = (m) => [m.unknown_count, m.weighted_sum_mm, m.max_mm === null ? Infinity : m.max_mm];
  const lexCmp = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; return 0; };
  const outVec = (k) => ({ unknown_count: k[0], weighted_sum_mm: k[1], max_mm: k[2] === Infinity ? null : k[2] });
  function worstOf(perCase) {
    let w = null;
    for (const r of perCase) if (w === null || lexCmp(r.key, w) > 0) w = r.key;
    return { vector: w, ids: perCase.filter((r) => lexCmp(r.key, w) === 0).map((r) => r.case_id).sort(cmpStr) };
  }

  /* evaluateResilience(ctx, envelope, selectedIds) -> per_case (metrics, loss), worst_vector, worst_case_ids, feasibility. */
  function evaluateInternal(ctx, env, selectedIds, pre) {
    const PC = pre || precomputeCases(ctx, env);
    const per = PC.map(({ case: c, P }) => {
      const ev = PL.internal.evaluate(ctx, env.plan, selectedIds, P);
      return { case_id: c.id, label: c.label, disabled_count: c.disabled_source_ids.length, source_records: P.src.length, metrics: ev.metrics, rows: ev.rows,
        key: lossKey(ev.metrics) };
    });
    const w = worstOf(per), base = per[0];
    const f = PL.feasibility(env.plan, selectedIds);
    return { selected_ids: [...new Set(selectedIds)].sort(cmpStr), feasibility: { feasible: f.feasible, reasons: f.reasons }, cost: f.cost,
      per_case: per.map(({ key, ...r }) => ({ ...r, loss: outVec(key) })), worst_vector: outVec(w.vector), worst_case_ids: w.ids,
      base_weighted_mean_mm: base.metrics.weighted_mean_mm, metric_version: PL.METRIC, objective_version: OBJECTIVE };
  }
  function evaluateResilience(ctx, env, selectedIds) {
    const clean = validateResilience(env, ctx);
    for (const id of selectedIds) if (!clean.plan.candidates.some((c) => c.id === id)) fail("unknown_ref", `кандидата ${id} нет`);
    return evaluateInternal(ctx, clean, selectedIds);
  }

  // ---------- exact search: ≤ 2^12 subsets, all cases precomputed once, chunked, cancellable ----------
  function createSearchInternal(ctx, env, opts) {
    const F = (opts && opts.F) || null, request_id = opts && opts.request_id !== undefined ? opts.request_id : null;
    const sc = env.plan, PC = precomputeCases(ctx, env), nCase = PC.length;
    const P0 = PC[0].P, nP = P0.pts.length, cands = P0.cands, weights = P0.pts.map((p) => p.weight);
    const idx = new Map(cands.map((c, i) => [c.id, i]));
    const req = sc.required_ids.map((id) => idx.get(id)).sort((a, b) => a - b), exc = new Set(sc.excluded_ids.map((id) => idx.get(id)));
    const free = []; for (let i = 0; i < cands.length; i++) if (!req.includes(i) && !exc.has(i)) free.push(i);
    const reqCost = req.reduce((s, i) => s + cands[i].cost, 0), reasons = [];
    if (req.length > sc.max_selected) reasons.push({ code: "required_exceeds_max_selected", text: `обязательных ${req.length} > максимума ${sc.max_selected}` });
    if (reqCost > sc.budget) reasons.push({ code: "required_cost_exceeds_budget", text: `стоимость обязательных ${reqCost} > бюджета ${sc.budget} усл. ед.` });
    const total = reasons.length ? 0 : 2 ** free.length, slots = sc.max_selected - req.length;
    // per case: start vector (case baseline + required) and candidate distance rows in mm; the case's baseline differs, candidates do not
    const start = PC.map(({ P }) => { const a = new Float64Array(nP); for (let j = 0; j < nP; j++) { let v = P.base[j] ? P.base[j].mm : Infinity; for (const i of req) v = Math.min(v, P.dist[i][j].mm); a[j] = v; } return a; });
    const dist = free.map((i) => Float64Array.from(P0.dist[i].map((d) => d.mm)));
    const fcost = free.map((i) => cands[i].cost);
    const idsOf = (m) => { const ids = req.map((i) => cands[i].id); for (let k = 0; k < free.length; k++) if (m & (1 << k)) ids.push(cands[free[k]].id); return ids.sort(cmpStr); };
    const after = new Float64Array(nP);
    let examined = 0, feasible = 0, mask = 0, cancelled = false, bestRobust = null, bestNominal = null;
    const caseLoss = (c, m) => {
      after.set(start[c]);
      for (let k = 0; k < free.length; k++) if (m & (1 << k)) { const d = dist[k]; for (let j = 0; j < nP; j++) if (d[j] < after[j]) after[j] = d[j]; }
      let u = 0, s = 0, mx = 0;
      for (let j = 0; j < nP; j++) { const a = after[j]; if (a === Infinity) { u++; continue; } s += weights[j] * a; if (a > mx) mx = a; }
      return [u, s, u ? Infinity : mx];
    };
    const better = (ka, ma, b) => { const c = lexCmp(ka, b.k); if (c) return c < 0; return PL.cmpIds(idsOf(ma), b.ids || (b.ids = idsOf(b.m))) < 0; };
    function step(n) {
      if (cancelled || reasons.length) return true;
      const end = Math.min(total, mask + n);
      for (; mask < end; mask++) {
        examined++;
        if (PL.popcount(mask) > slots) continue;
        let cost = reqCost; for (let k = 0; k < free.length; k++) if (mask & (1 << k)) cost += fcost[k];
        if (cost > sc.budget) continue;
        feasible++;
        const L = []; for (let c = 0; c < nCase; c++) L.push(caseLoss(c, mask));
        let W = L[0]; for (let c = 1; c < nCase; c++) if (lexCmp(L[c], W) > 0) W = L[c];
        const kR = [...W, ...L[0], cost], kN = [...L[0], cost];  // robust: (W, L_base, cost, ids); nominal = v2 mean on base: (L_base, cost, ids)
        if (!bestRobust || better(kR, mask, bestRobust)) bestRobust = { k: kR, m: mask, ids: null };
        if (!bestNominal || better(kN, mask, bestNominal)) bestNominal = { k: kN, m: mask, ids: null };
      }
      return mask >= total;
    }
    const base = { metric_version: PL.METRIC, objective_version: OBJECTIVE, request_id, resilience_problem_digest: F ? resilienceProblemDigest(env, F) : null,
      exclusions_digest: F ? exclusionsDigest(env, F) : null, source_snapshot: sc.source_snapshot, cases: allCases(env).map((c) => c.id) };
    function result() {
      if (reasons.length) return { ...base, status: "infeasible", reasons, nominal: null, robust: null, evaluated: 0, total_subsets: 0, feasible_count: 0,
        price_of_robustness_m: null, price_reason: "нет допустимых планов" };
      if (cancelled || mask < total) return { ...base, status: cancelled ? "cancelled" : "incomplete", reasons: [], nominal: null, robust: null, evaluated: examined, total_subsets: total,
        feasible_count: feasible, price_of_robustness_m: null, price_reason: "поиск не завершён" };
      const pre = PC;
      const nominal = evaluateInternal(ctx, env, idsOf(bestNominal.m), pre), robust = evaluateInternal(ctx, env, idsOf(bestRobust.m), pre);
      const a = robust.base_weighted_mean_mm, b = nominal.base_weighted_mean_mm;
      const price = a !== null && b !== null ? (a - b) / 1000 : null;
      return { ...base, status: "optimal", reasons: [], nominal, robust, same_plan: nominal.selected_ids.join() === robust.selected_ids.join(),
        evaluated: examined, total_subsets: total, feasible_count: feasible, duplicate_case_groups: duplicateCaseGroups(env),
        price_of_robustness_m: price, price_reason: price === null ? "в базовом случае у одного из планов есть точки без расстояния — среднее не определено" : null };
    }
    return { get total() { return total; }, get examined() { return examined; }, step, cancel: () => { cancelled = true; }, result, request_id };
  }
  function createResilienceSearch(ctx, env, opts) { return createSearchInternal(ctx, validateResilience(env, ctx), opts); }
  function optimizeResilience(ctx, env, opts) { const s = createResilienceSearch(ctx, env, opts); while (!s.step(1 << 20)); return s.result(); }

  // ---------- files: the envelope is input only (no derived values); strict JSON; atomic for the caller ----------
  function exportResilience(ctx, env) {
    const clean = validateResilience(env, ctx);
    return JSON.stringify({ schema_version: SCHEMA, plan: clean.plan, cases: clean.cases }, null, 1) + "\n";
  }
  function importResilience(text, ctxFor) {
    let obj;
    try { obj = X.parseStrict(text); } catch (e) { throw new PlanError(e.code === "too_large" || e.code === "bad_encoding" ? e.code : "bad_json", e.detail || e.message); }
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) fail("bad_shape", "ожидается объект");
    if (obj.schema_version !== SCHEMA) validateResilience(obj, null);  // names the foreign version (v1 / v2 / unknown)
    const plan = obj.plan;
    const city = plan && typeof plan === "object" ? plan.city_id : null;
    if (city !== "shymkent" && city !== "astana") fail("bad_city", String(city).slice(0, 40));
    const ctx = ctxFor(city);
    return { envelope: validateResilience(obj, ctx), ctx };
  }

  // ---------- template explanation over computed facts (not an LLM) ----------
  const mText = (mm) => (mm === null || mm === undefined ? "нет данных" : mm >= 1e6 ? (mm / 1e6).toFixed(2).replace(".", ",") + " км" : Math.round(mm / 1000) + " м");
  const idsText = (ids) => (ids.length ? ids.join(", ") : "без новых объектов");
  const vecText = (v) => `${v.unknown_count} точек без расстояния, сумма ${mText(v.weighted_sum_mm)}·вес, худшая точка ${mText(v.max_mm)}`;
  function explainResilience(env, manual, result) {
    const L = [`Шаблонное объяснение по вычисленным фактам (не LLM). Случаев: ${env.cases.length} пользовательских + базовый. В каждом случае выбранные исходные записи условно не учитываются в расчёте; это не подтверждение закрытия и не прогноз.`];
    const dups = duplicateCaseGroups(env);
    if (dups.length) L.push(`Случаи с одинаковым набором исключений: ${dups.map((g) => g.join(" = ")).join("; ")}. Повтор не меняет результат.`);
    if (manual) L.push(`Ручной план (${idsText(manual.selected_ids)}): ${manual.feasibility.feasible ? "допустим" : "НЕДОПУСТИМ — " + manual.feasibility.reasons.map((r) => r.text).join("; ") + "; не рекомендуется"}; худший исход: ${vecText(manual.worst_vector)} (случаи ${manual.worst_case_ids.join(", ")}).`);
    if (result && result.status === "infeasible") L.push("Допустимых планов нет: " + result.reasons.map((r) => r.text).join("; ") + ". Ограничения не снимались.");
    if (result && result.status === "optimal") {
      const n = result.nominal, r = result.robust;
      L.push(`Обычный план (лучшее среднее в базовом случае): ${idsText(n.selected_ids)}; худший исход по случаям: ${vecText(n.worst_vector)} (${n.worst_case_ids.join(", ")}).`);
      L.push(`Устойчивый план (лучший худший исход): ${idsText(r.selected_ids)}; худший исход: ${vecText(r.worst_vector)} (${r.worst_case_ids.join(", ")}).`);
      if (result.same_plan) L.push("Обычный и устойчивый планы совпали: при этих случаях устойчивость ничего не стоит и ничего не добавляет.");
      if (result.price_of_robustness_m !== null) L.push(`Цена устойчивости в базовом случае: ${result.price_of_robustness_m >= 0 ? "+" : ""}${result.price_of_robustness_m.toFixed(1).replace(".", ",")} м к взвешенному среднему расстоянию по прямой.`);
      else L.push(`Цена устойчивости не вычисляется: ${result.price_reason}.`);
    }
    L.push("Худший исход — это худший из перечисленных случаев по порядку (неизвестные точки, затем сумма, затем худшая точка), а не сочетание худших значений разных случаев. Нет вероятностей, риска, населения, вместимости и пешего времени; стоимости — условные единицы.");
    return L.join("\n");
  }

  const api = { SCHEMA, OBJECTIVE, LIMITS, validateResilience, evaluateResilience, createResilienceSearch, optimizeResilience, exportResilience, importResilience,
    resilienceProblemDigest, resilienceScenarioDigest, exclusionsDigest, duplicateCaseGroups, allCases, explainResilience, caseContext };
  if (node) module.exports = api; else root.CITY_RESILIENCE = api;
})(typeof window !== "undefined" ? window : globalThis);
