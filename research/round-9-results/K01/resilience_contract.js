/* city-resilience-v1 envelope contract (K01 round 9). Narrow module: NOT a planner. Reuses the BUILD's
 * web/plan.js (validatePlanScenario, problemDigest, makeContext) and web/whatif.js (parseStrict). No DOM.
 * Browser: window.CITY_RESILIENCE_CONTRACT (load after whatif.js, facts.js, plan.js). Node: module.exports(PL, X).
 *
 *   validateResilience(input, ctx)        -> clean envelope {schema_version, plan, cases (sorted by id, exclusions sorted)} | ResilienceError
 *   importResilience(text, ctxFor, F)     -> {envelope, ctx}; nothing is applied (caller swaps state only on success)
 *   exportResilience(env, ctx)            -> JSON text of the INPUT only (no derived fields)
 *   resilienceProblemDigest(env, F) / resilienceScenarioDigest(env, F) / exclusionsDigest(env, F)
 *   computationCases(env)                 -> [{id:"base", disabled:[]}, ...user cases] for an engine (base added here, never in the file)
 */
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) module.exports = factory;
  else root.CITY_RESILIENCE_CONTRACT = factory(root.CITY_PLAN, root.CITY_WHATIF);
})(typeof window !== "undefined" ? window : globalThis, function (PL, X) {
  "use strict";
  const SCHEMA = "city-resilience-v1", OBJECTIVE = "worst-lex-v1";
  const LIMITS = { cases: [1, 7], candidates: 12, label: 120, bytes: 256 * 1024 };
  class ResilienceError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const fail = (c, d) => { throw new ResilienceError(c, d); };
  const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const ID_CHARS = /^[\p{L}\p{N}_.-]+$/u;
  const CTRL_RE = new RegExp("[\\u0000-\\u001f\\u007f-\\u009f\\u2028\\u2029]");
  const idOk = (v) => typeof v === "string" && v.normalize("NFC") === v && [...v].length >= 1 && [...v].length <= 64 && ID_CHARS.test(v);
  const short = (v) => { try { return JSON.stringify(v).slice(0, 48); } catch (e) { return "?"; } };
  const exact = (o, keys, where) => {
    if (!isObj(o)) fail("bad_shape", `${where}: ожидается объект`);
    for (const k of Object.keys(o)) if (!keys.includes(k)) fail("unknown_field", `${where}: поле ${short(k)}`);
    for (const k of keys) if (!(k in o)) fail("missing_field", `${where}.${k}`);
  };
  function labelOk(s) {
    if (typeof s !== "string") return "не строка";
    if (s.length === 0 || s.trim().length === 0) return "пустая";
    if (s.isWellFormed ? !s.isWellFormed() : /[\ud800-\udfff]/u.test(s.replace(/[\ud800-\udbff][\udc00-\udfff]/g, ""))) return "непарный суррогат";
    if ([...s].length > LIMITS.label) return `длиннее ${LIMITS.label} символов`;
    if (CTRL_RE.test(s)) return "управляющий символ";
    return null;
  }

  function validateResilience(input, ctx) {
    exact(input, ["schema_version", "plan", "cases"], "envelope");
    if (input.schema_version !== SCHEMA) fail("bad_version", `версия ${short(input.schema_version)} ≠ ${SCHEMA}`);
    if (!isObj(input.plan)) fail("bad_shape", "plan: ожидается объект city-plan-v2");
    if ("derived_results" in input.plan) fail("derived_not_allowed", "в r9 envelope производные поля не принимаются");
    const plan = PL.validatePlanScenario(input.plan, ctx);               // BUILD rules: snapshot, city, bbox, IDs, limits (typed PlanError)
    if (plan.candidates.length > LIMITS.candidates)
      fail("too_many_candidates", `устойчивость: не больше ${LIMITS.candidates} кандидатов (в плане ${plan.candidates.length}); v2 продолжает решать до 16`);
    const cases = input.cases;
    if (!Array.isArray(cases)) fail("bad_shape", "cases: ожидается массив");
    if (cases.length < LIMITS.cases[0] || cases.length > LIMITS.cases[1]) fail("bad_cases", `пользовательских случаев 1..7 (base добавляется сам), получено ${cases.length}`);
    const sources = new Map(ctx.places.map((p) => [p.id, p.group]));
    const own = new Set(ctx.places.filter((p) => p.group === plan.category).map((p) => p.id));
    const candIds = new Set(plan.candidates.map((c) => c.id));
    const seen = new Set();
    const clean = cases.map((c, k) => {
      const w = `cases[${k}]`;
      exact(c, ["id", "label", "disabled_source_ids"], w);
      if (!idOk(c.id)) fail("bad_case_id", `${w}.id ${short(c.id)} (NFC, буквы/цифры/_ . -, до 64)`);
      if (c.id === "base") fail("reserved_case_id", `${w}: id "base" зарезервирован для случая без исключений`);
      if (seen.has(c.id)) fail("duplicate_case_id", `${w}: ${c.id}`);
      seen.add(c.id);
      const lb = labelOk(c.label);
      if (lb) fail("bad_label", `${w}.label: ${lb}`);
      const ds = c.disabled_source_ids;
      if (!Array.isArray(ds) || ds.length < 1) fail("bad_exclusions", `${w}: нужен хотя бы один исключаемый источник`);
      if (ds.length > own.size) fail("bad_exclusions", `${w}: исключений ${ds.length} > записей категории ${own.size}`);
      const ss = new Set();
      for (const id of ds) {
        if (!idOk(id)) fail("bad_id", `${w}: ${short(id)}`);
        if (ss.has(id)) fail("duplicate_source_id", `${w}: ${id}`);
        ss.add(id);
        if (!own.has(id)) {
          if (candIds.has(id)) fail("candidate_id_as_source", `${w}: ${id} — кандидат, а не исходная запись`);
          if (sources.has(id)) fail("wrong_category_source", `${w}: ${id} — запись категории ${sources.get(id)}, а план ${plan.category}`);
          fail("unknown_source", `${w}: исходной записи ${id} нет в срезе ${ctx.city_id}`);
        }
      }
      return { id: c.id, label: c.label, disabled_source_ids: ds.slice().sort(cmp) };
    }).sort((a, b) => cmp(a.id, b.id));
    return { schema_version: SCHEMA, plan, cases: clean };
  }

  function importResilience(text, ctxFor, F) {
    if (typeof text !== "string") fail("bad_json", "ожидается текст");
    let obj;
    try { obj = X.parseStrict(text); } catch (e) { fail(e.code === "too_large" || e.code === "bad_encoding" ? e.code : "bad_json", e.detail || e.message); }
    if (!isObj(obj)) fail("bad_shape", "ожидается объект");
    if (obj.schema_version !== SCHEMA) fail(obj.schema_version === PL.SCHEMA ? "wrong_version" : "bad_version", `версия ${short(obj.schema_version)}`);
    const city = isObj(obj.plan) ? obj.plan.city_id : null;
    if (city !== "shymkent" && city !== "astana") fail("bad_city", short(city));
    const ctx = ctxFor(city);
    return { envelope: validateResilience(obj, ctx), ctx };
  }
  function exportResilience(env, ctx) {
    const v = validateResilience(env, ctx);
    const txt = JSON.stringify(v, null, 1) + "\n";
    if (new TextEncoder().encode(txt).length > LIMITS.bytes) fail("too_large", "экспорт больше 256 KiB");
    return txt;
  }
  const casesCanon = (env) => env.cases.slice().sort((a, b) => cmp(a.id, b.id)).map((c) => [c.id, c.label, c.disabled_source_ids.slice().sort(cmp)]);
  const resilienceProblemDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, OBJECTIVE, PL.METRIC, PL.problemDigest(env.plan, F), casesCanon(env)]));
  const resilienceScenarioDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify([resilienceProblemDigest(env, F), env.plan.selected_ids.slice().sort(cmp)]));
  const exclusionsDigest = (env, F) => "sha256:" + F.sha256hex(JSON.stringify(casesCanon(env).map((c) => [c[0], c[2]])));
  const computationCases = (env) => [{ id: "base", label: "base", disabled_source_ids: [] }, ...env.cases];
  return { SCHEMA, OBJECTIVE, LIMITS, ResilienceError, validateResilience, importResilience, exportResilience,
    resilienceProblemDigest, resilienceScenarioDigest, exclusionsDigest, computationCases, labelOk, idOk };
});
