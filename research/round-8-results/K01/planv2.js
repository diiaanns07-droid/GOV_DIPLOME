/* city-plan-v2 contract module (K01 round 8): strict parse, validation, import/export, atomic store, v1→v2 migration,
 * canonical digests. Pure functions, no DOM. UMD: window.CITY_PLAN_V2 in the browser, module.exports in Node.
 * Spec: research/round-8/CORE_SPEC.txt. Independent Python oracle: planv2_ref.py (written separately, cross-checked).
 *
 * context = { city_id, bbox:[w,s,e,n], source_snapshot, category_records_count?, sha256hex(str)->hex }
 *   build it with contextFromData(data, city, F) where F = CITY_FACTS (sha256hex, placesDigest) of the prototype.
 * Check order is fixed (see CHECK_ORDER in README.md) so JS and Python return the same first error code.
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-plan-v2";
  const METRIC_VERSION = "haversine-mm-v1";
  const CITIES = ["shymkent", "astana"];
  const CATEGORIES = ["school", "outpatient_clinic"];
  const MAX_BYTES = 256 * 1024;
  const LIM = { points: [1, 25], candidates: [0, 16], weight: [1, 100], cost: [1, 1000000], budget: [0, 1000000],
                max_selected: [0, 5], radius: [100, 5000] };
  const ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;
  const SNAP_RE = /^sha256:[0-9a-f]{64}$/;
  const TOP_REQUIRED = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
    "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"];
  const TOP_ALLOWED = new Set([...TOP_REQUIRED, "derived_results"]);
  const CP_KEYS = ["id", "lat", "lon", "weight"];
  const CAND_KEYS = ["category", "cost", "id", "kind", "lat", "lon"];

  class PlanV2Error extends Error {
    constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; }
  }
  const fail = (code, detail) => { throw new PlanV2Error(code, detail); };
  const short = (v) => { try { return JSON.stringify(v).slice(0, 48); } catch (e) { return "?"; } };

  // ---------- strict JSON (own parser: no NaN/Infinity/1e999, no duplicate keys, no trailing data) ----------
  function utf8Length(text) {
    let n = 0;
    for (const ch of text) { const c = ch.codePointAt(0); n += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4; }
    return n;
  }
  function decodeBytes(bytes) {
    if (bytes.length > MAX_BYTES) fail("too_large", `${bytes.length} байт > ${MAX_BYTES}`);
    try { return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes); }
    catch (e) { fail("bad_encoding", "файл не в UTF-8"); }
  }
  function parseStrict(text) {
    if (typeof text !== "string") fail("bad_json", "ожидается текст");
    if (utf8Length(text) > MAX_BYTES) fail("too_large", `> ${MAX_BYTES} байт`);
    let i = text.charCodeAt(0) === 0xfeff ? 1 : 0;
    const err = (code, m) => fail(code, `${m} (позиция ${i})`);
    const ws = () => { while (i < text.length && (text[i] === " " || text[i] === "\t" || text[i] === "\n" || text[i] === "\r")) i++; };
    const str = () => {
      i++; let out = "";
      for (;;) {
        if (i >= text.length) err("bad_json", "незакрытая строка");
        const ch = text[i];
        if (ch === '"') { i++; return out; }
        if (ch === "\\") {
          const e = text[i + 1], map = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
          if (e in map) { out += map[e]; i += 2; continue; }
          if (e === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) { out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16)); i += 6; continue; }
          err("bad_json", "неверная escape-последовательность");
        }
        if (ch < " ") err("bad_json", "управляющий символ в строке");
        out += ch; i++;
      }
    };
    const value = (depth) => {
      if (depth > 32) err("bad_json", "слишком глубокая вложенность");
      ws();
      const ch = text[i];
      if (ch === "{") {
        i++; const obj = Object.create(null); ws();
        if (text[i] === "}") { i++; return obj; }
        for (;;) {
          ws(); if (text[i] !== '"') err("bad_json", "ожидается ключ");
          const k = str();
          if (Object.prototype.hasOwnProperty.call(obj, k)) err("duplicate_key", `повтор ключа ${short(k)}`);
          ws(); if (text[i] !== ":") err("bad_json", "ожидается :"); i++;
          obj[k] = value(depth + 1); ws();
          if (text[i] === ",") { i++; continue; }
          if (text[i] === "}") { i++; return obj; }
          err("bad_json", "ожидается , или }");
        }
      }
      if (ch === "[") {
        i++; const arr = []; ws();
        if (text[i] === "]") { i++; return arr; }
        for (;;) {
          arr.push(value(depth + 1)); ws();
          if (text[i] === ",") { i++; continue; }
          if (text[i] === "]") { i++; return arr; }
          err("bad_json", "ожидается , или ]");
        }
      }
      if (ch === '"') return str();
      if (text.startsWith("true", i)) { i += 4; return true; }
      if (text.startsWith("false", i)) { i += 5; return false; }
      if (text.startsWith("null", i)) { i += 4; return null; }
      if (/^-?(NaN|Infinity)/.test(text.slice(i, i + 9))) err("non_finite", "NaN/Infinity не допускаются");
      const m = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i, i + 400));
      if (!m) err("bad_json", "недопустимый токен");
      i += m[0].length;
      const v = Number(m[0]);
      if (!Number.isFinite(v)) err("non_finite", `число ${m[0].slice(0, 24)} не конечно`);
      return v;
    };
    const v = value(0); ws();
    if (i !== text.length) err("bad_json", "лишние данные после JSON");
    return v;
  }

  // ---------- validation ----------
  const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);
  const isInt = (v) => isNum(v) && Number.isInteger(v);
  const inRange = (v, [lo, hi]) => v >= lo && v <= hi;

  function checkKeys(o, keys, where) {
    if (!isObj(o)) fail("bad_shape", `${where}: ожидается объект`);
    const ks = Object.keys(o);
    for (const k of ks) if (!keys.includes(k)) fail("unknown_field", `${where}: поле ${short(k)} не допускается`);
    for (const k of keys) if (!(k in o)) fail("missing_field", `${where}.${k}`);
  }
  function checkId(v, where) { if (typeof v !== "string" || !ID_RE.test(v)) fail("bad_id", `${where}: ${short(v)}`); }
  function checkCoord(o, where, bbox) {
    if (!isNum(o.lon) || !isNum(o.lat) || Math.abs(o.lon) > 180 || Math.abs(o.lat) > 90) fail("bad_coord", `${where}: координаты`);
    if (!(bbox[0] <= o.lon && o.lon <= bbox[2] && bbox[1] <= o.lat && o.lat <= bbox[3])) fail("outside_bbox", `${where}: вне квадрата среза`);
  }
  function idList(v, name, candIds) {
    if (!Array.isArray(v)) fail("bad_shape", `${name}: ожидается массив`);
    if (v.length > LIM.candidates[1]) fail("bad_shape", `${name}: не более ${LIM.candidates[1]}`);
    const seen = new Set();
    v.forEach((x, k) => {
      checkId(x, `${name}[${k}]`);
      if (seen.has(x)) fail("duplicate_id", `${name}: ${x}`);
      seen.add(x);
      if (!candIds.has(x)) fail("unknown_ref", `${name}: кандидата ${x} нет`);
    });
    return v.slice();
  }

  /* Returns a clean, validated copy (never the parsed object); derived_results dropped. Throws PlanV2Error. */
  function validatePlanScenario(input, context) {
    if (!context || !CITIES.includes(context.city_id) || !Array.isArray(context.bbox) || !SNAP_RE.test(context.source_snapshot || ""))
      fail("bad_context", "контекст среза не задан");
    if (!isObj(input)) fail("bad_shape", "сценарий должен быть объектом");
    for (const k of Object.keys(input)) if (!TOP_ALLOWED.has(k)) fail("unknown_field", `поле ${short(k)} не допускается`);
    for (const k of TOP_REQUIRED) if (!(k in input)) fail("missing_field", k);
    if (input.schema_version !== SCHEMA) fail("bad_version", short(input.schema_version));
    if (!CITIES.includes(input.city_id)) fail("bad_city", short(input.city_id));
    if (input.city_id !== context.city_id) fail("foreign_city", `сценарий ${input.city_id}, открыт ${context.city_id}`);
    if (input.source_snapshot !== context.source_snapshot) fail("foreign_snapshot", "source_snapshot не совпадает с текущим срезом");
    if (!CATEGORIES.includes(input.category)) fail("bad_category", short(input.category));
    const bbox = context.bbox;

    const cps = input.control_points;
    if (!Array.isArray(cps) || !inRange(cps.length, LIM.points)) fail("bad_points", `контрольных точек 1..25`);
    const cpIds = new Set();
    const control_points = cps.map((p, k) => {
      const w = `control_points[${k}]`;
      checkKeys(p, CP_KEYS, w); checkId(p.id, w);
      if (cpIds.has(p.id)) fail("duplicate_id", `${w}: ${p.id}`);
      cpIds.add(p.id);
      checkCoord(p, w, bbox);
      if (!isInt(p.weight) || !inRange(p.weight, LIM.weight)) fail("bad_weight", `${w}: вес — целое 1..100`);
      return { id: p.id, lon: p.lon, lat: p.lat, weight: p.weight };
    });

    const cs = input.candidates;
    if (!Array.isArray(cs) || !inRange(cs.length, LIM.candidates)) fail("bad_candidates", `кандидатов 0..16`);
    const candIds = new Set();
    const candidates = cs.map((c, k) => {
      const w = `candidates[${k}]`;
      checkKeys(c, CAND_KEYS, w); checkId(c.id, w);
      if (candIds.has(c.id)) fail("duplicate_id", `${w}: ${c.id}`);
      candIds.add(c.id);
      checkCoord(c, w, bbox);
      if (c.category !== input.category) fail("bad_category", `${w}: категория кандидата ≠ category`);
      if (c.kind !== "hypothetical") fail("bad_kind", `${w}: kind должен быть hypothetical`);
      if (!isInt(c.cost) || !inRange(c.cost, LIM.cost)) fail("bad_cost", `${w}: cost — целое 1..1000000 условных единиц`);
      return { id: c.id, lon: c.lon, lat: c.lat, category: c.category, kind: "hypothetical", cost: c.cost };
    });

    if (!isInt(input.budget) || !inRange(input.budget, LIM.budget)) fail("bad_budget", "budget — целое 0..1000000");
    if (!isInt(input.max_selected) || !inRange(input.max_selected, LIM.max_selected)) fail("bad_max_selected", "max_selected — целое 0..5");
    if (!isInt(input.coverage_radius_m) || !inRange(input.coverage_radius_m, LIM.radius)) fail("bad_radius", "coverage_radius_m — целое 100..5000");
    const required_ids = idList(input.required_ids, "required_ids", candIds);
    const excluded_ids = idList(input.excluded_ids, "excluded_ids", candIds);
    const both = required_ids.filter((x) => excluded_ids.includes(x));
    if (both.length) fail("constraint_conflict", `и required, и excluded: ${both.join(",")}`);
    const selected_ids = idList(input.selected_ids, "selected_ids", candIds);
    return { schema_version: SCHEMA, city_id: input.city_id, source_snapshot: input.source_snapshot, category: input.category,
      control_points, candidates, budget: input.budget, max_selected: input.max_selected, coverage_radius_m: input.coverage_radius_m,
      required_ids, excluded_ids, selected_ids };
  }

  // ---------- canonical digests (order-independent; selected_ids only in scenario_digest) ----------
  const byId = (a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const sortStr = (xs) => xs.slice().sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  function problemCanonical(sc) {
    return [SCHEMA, METRIC_VERSION, sc.source_snapshot, sc.city_id, sc.category,
      sc.control_points.slice().sort(byId).map((p) => [p.id, p.lon, p.lat, p.weight]),
      sc.candidates.slice().sort(byId).map((c) => [c.id, c.lon, c.lat, c.category, c.kind, c.cost]),
      sc.budget, sc.max_selected, sc.coverage_radius_m, sortStr(sc.required_ids), sortStr(sc.excluded_ids)];
  }
  function problemDigest(sc, context) { return "pd1:" + context.sha256hex(JSON.stringify(problemCanonical(sc))); }
  function scenarioDigest(sc, context) {
    return "sd1:" + context.sha256hex(JSON.stringify([problemCanonical(sc), sortStr(sc.selected_ids)]));
  }

  // ---------- import / export ----------
  /* text|Uint8Array -> {scenario, notes}; derived_results never trusted (dropped, caller recomputes). */
  function importPlan(raw, context) {
    const text = typeof raw === "string" ? raw : decodeBytes(raw);
    const obj = parseStrict(text);
    const notes = isObj(obj) && "derived_results" in obj ? ["derived_results из файла отброшены: результаты пересчитываются"] : [];
    return { scenario: validatePlanScenario(obj, context), notes };
  }
  /* derive: optional (scenario) -> JSON-compatible derived block (e.g. BUILD evaluatePlan/optimizePlans output). */
  function exportPlan(sc, context, derive) {
    const clean = validatePlanScenario(sc, context);
    const out = Object.assign({}, clean);
    if (typeof derive === "function") {
      out.derived_results = { kind: "derived", note: "производные значения; при импорте не принимаются и пересчитываются",
        metric_version: METRIC_VERSION, problem_digest: problemDigest(clean, context), value: derive(clean) };
    }
    const txt = JSON.stringify(out, null, 1) + "\n";
    if (utf8Length(txt) > MAX_BYTES) fail("too_large", "экспорт превышает 256 KiB");
    return txt;
  }

  // ---------- v1 -> v2 migration: never invents costs/budget ----------
  function migrateV1(v1, opts, context) {
    if (!isObj(v1) || v1.schema_version !== "city-whatif-v1") fail("bad_version", "ожидается проверенный city-whatif-v1");
    opts = opts || {};
    const prop = v1.proposed_object;
    if (!isInt(opts.budget)) fail("cost_required", "для переноса v1→v2 пользователь задаёт budget явно");
    if (prop && !isInt(opts.cost)) fail("cost_required", "для переноса v1→v2 пользователь задаёт cost проектного объекта явно");
    const cand = prop ? [{ id: prop.id, lon: prop.lon, lat: prop.lat, category: v1.category, kind: "hypothetical", cost: opts.cost }] : [];
    return validatePlanScenario({ schema_version: SCHEMA, city_id: v1.city_id, source_snapshot: context.source_snapshot,
      category: v1.category, control_points: v1.control_points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, weight: 1 })),
      candidates: cand, budget: opts.budget, max_selected: isInt(opts.max_selected) ? opts.max_selected : Math.min(5, cand.length),
      coverage_radius_m: isInt(opts.coverage_radius_m) ? opts.coverage_radius_m : 1000, required_ids: [], excluded_ids: [],
      selected_ids: cand.map((c) => c.id) }, context);
  }

  // ---------- atomic state ----------
  /* Holds the active scenario. A failed import/edit leaves it untouched; a city/category switch resets it and invalidates
   * pending worker answers (request_id); an optimizer answer applies only for the current problem_digest. */
  class PlanStore {
    constructor(context) { this.context = context; this.active = null; this.request = 0; this.proposal = null; this.message = null; }
    _set(sc, msg) { this.active = sc; this.proposal = null; this.request++; this.message = msg || null; return true; }
    importText(raw) {
      let r;
      try { r = importPlan(raw, this.context); }
      catch (e) { if (!(e instanceof PlanV2Error)) throw e; this.message = `Импорт отклонён (${e.code}); текущий сценарий не изменён`; return false; }
      return this._set(r.scenario, r.notes.join("; "));
    }
    edit(mutator) {
      if (!this.active) return false;
      const draft = JSON.parse(JSON.stringify(this.active));
      try { mutator(draft); return this._set(validatePlanScenario(draft, this.context)); }
      catch (e) { if (!(e instanceof PlanV2Error)) throw e; this.message = `Изменение отклонено (${e.code}); сценарий не изменён`; return false; }
    }
    switchContext(context) {
      const changed = !this.active || this.active.city_id !== context.city_id || this.active.source_snapshot !== context.source_snapshot;
      this.context = context;
      if (this.active && changed) { this._set(null, "Город/срез изменён: сценарий, предложения и объяснение сброшены"); }
    }
    switchCategory(category) {
      if (this.active && this.active.category !== category) this._set(null, "Категория изменена: сценарий и объяснение сброшены");
    }
    startOptimization() { if (!this.active) return null; return { request_id: ++this.request, problem_digest: problemDigest(this.active, this.context) }; }
    receive(answer) {   // answer: {request_id, problem_digest, ...}; stale ones are ignored
      if (!this.active || !answer || answer.request_id !== this.request || answer.problem_digest !== problemDigest(this.active, this.context)) return false;
      this.proposal = answer; return true;
    }
    applyProposal(ids) {   // user pressed «Применить»: proposal ids become the manual plan
      if (!this.proposal) return false;
      const keep = this.proposal;
      const ok = this.edit((d) => { d.selected_ids = ids.slice(); });
      if (!ok) this.proposal = keep;
      return ok;
    }
  }

  // ---------- adapter for the prototype ----------
  /* data = window.CITY_EVIDENCE (web/data.js), F = CITY_FACTS (web/facts.js). Snapshot follows the v1 convention of
   * web/whatif.js sourceSnapshot, with this schema and metric version. */
  function sourceSnapshot(data, city, F) {
    const c = data.cities[city];
    if (!c) fail("bad_city", short(city));
    const fsha = c.files && c.files.places_social && c.files.places_social.sha256;
    return "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, city, c.release, fsha || null, F.placesDigest(data, city), METRIC_VERSION]));
  }
  function contextFromData(data, city, F) {
    return { city_id: city, bbox: data.cities[city].bbox.slice(), source_snapshot: sourceSnapshot(data, city, F), sha256hex: F.sha256hex,
      release: data.cities[city].release };
  }

  const api = { SCHEMA, METRIC_VERSION, MAX_BYTES, LIM, PlanV2Error, parseStrict, decodeBytes, validatePlanScenario, importPlan, exportPlan,
    migrateV1, problemCanonical, problemDigest, scenarioDigest, PlanStore, sourceSnapshot, contextFromData };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN_V2 = api;
})(typeof window !== "undefined" ? window : globalThis);
