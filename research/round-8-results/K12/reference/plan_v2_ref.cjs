// K12 round 8: REFERENCE implementation of city-plan-v2 (research/round-8/CORE_SPEC.txt @ c3f6c00).
// Logic only (no DOM, no network, no eval). Oracle for the K12 stress/fuzz tests and an integrable proposal.
// Works in Node and in a browser: sha256hex (and optionally placesDigest) are injected, e.g. from facts.js.
//
//   const P = require("./plan_v2_ref.cjs");
//   const reg = P.makeRegistry(window.CITY_EVIDENCE, { sha256hex, placesDigest });   // current slice
//   const sc  = P.validatePlanScenario(textOrObject, reg);          // clean copy or throws PlanError {code, detail}
//   const ev  = P.evaluatePlan(reg, sc, sc.selected_ids);           // rows + metrics + feasibility
//   const opt = P.optimizePlans(reg, sc);                           // exact search over all subsets (<= 16 candidates)
//   const r   = await P.optimizePlansAsync(reg, sc, { requestId, signal, chunk, yieldFn });   // cancellable
//   const gate = new P.ResultGate(); const id = gate.begin(opt.problem_digest); gate.accept(result)  // late results
"use strict";

const SCHEMA = "city-plan-v2";
const METRIC_VERSION = "haversine-mm-v1";
const R_EARTH = 6371008.8;
const LIMITS = Object.freeze({ maxBytes: 256 * 1024, maxDepth: 32, points: [1, 25], candidates: [0, 16], maxSelected: [0, 5],
  weight: [1, 100], cost: [1, 1000000], budget: [0, 1000000], radius: [100, 5000], idMax: 64, exactMaxCandidates: 16 });
const ID_RE = /^[A-Za-z0-9_.-]{1,64}$/;
const CITIES = ["shymkent", "astana"];
const CATEGORIES = ["school", "outpatient_clinic"];
const REQUIRED_KEYS = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
  "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"];
const ALLOWED_KEYS = new Set([...REQUIRED_KEYS, "derived_results"]);
const POINT_KEYS = ["id", "lon", "lat", "weight"];
const CAND_KEYS = ["id", "lon", "lat", "category", "kind", "cost"];

class PlanError extends Error {
  constructor(code, detail) { super(`${code}: ${detail}`); this.code = code; this.detail = detail; }
}
const fail = (code, detail) => { throw new PlanError(code, detail); };
const isInt = (v) => typeof v === "number" && Number.isInteger(v);
const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

// ------------------------------------------------------------------ strict JSON
function utf8Length(s) {
  let n = 0;
  for (const ch of s) { const c = ch.codePointAt(0); n += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4; }
  return n;
}

function parseStrict(text) {
  if (typeof text !== "string") fail("bad_json", "ожидается текст");
  const bytes = utf8Length(text);
  if (bytes > LIMITS.maxBytes) fail("too_large", `${bytes} байт > ${LIMITS.maxBytes}`);
  let i = text.charCodeAt(0) === 0xfeff ? 1 : 0;
  const err = (code, m) => fail(code, `${m} (позиция ${i})`);
  const ws = () => { while (i < text.length && (text[i] === " " || text[i] === "\t" || text[i] === "\n" || text[i] === "\r")) i++; };
  function value(depth) {
    if (depth > LIMITS.maxDepth) err("too_deep", `вложенность > ${LIMITS.maxDepth}`);
    ws();
    const ch = text[i];
    if (ch === "{") {
      i++;
      const obj = Object.create(null);
      ws();
      if (text[i] === "}") { i++; return obj; }
      for (;;) {
        ws();
        if (text[i] !== '"') err("bad_json", "ожидается ключ");
        const k = str();
        if (has(obj, k)) err("duplicate_key", `повтор ключа ${JSON.stringify(k).slice(0, 40)}`);
        ws();
        if (text[i] !== ":") err("bad_json", "ожидается :");
        i++;
        obj[k] = value(depth + 1);
        ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "}") { i++; return obj; }
        err("bad_json", "ожидается , или }");
      }
    }
    if (ch === "[") {
      i++;
      const arr = [];
      ws();
      if (text[i] === "]") { i++; return arr; }
      for (;;) {
        arr.push(value(depth + 1));
        ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "]") { i++; return arr; }
        err("bad_json", "ожидается , или ]");
      }
    }
    if (ch === '"') return str();
    if (text.startsWith("true", i)) { i += 4; return true; }
    if (text.startsWith("false", i)) { i += 5; return false; }
    if (text.startsWith("null", i)) { i += 4; return null; }
    const m = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i, i + 64));
    if (!m) err("bad_json", "недопустимый токен (NaN/Infinity не допускаются)");
    i += m[0].length;
    const v = Number(m[0]);
    if (!Number.isFinite(v)) err("nonfinite_number", `число ${m[0].slice(0, 20)} не конечно`);
    return v;
  }
  function str() {
    i++;
    let out = "";
    while (i < text.length) {
      const ch = text[i];
      if (ch === '"') { i++; return out; }
      if (ch === "\\") {
        const e = text[i + 1];
        const map = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
        if (e in map) { out += map[e]; i += 2; continue; }
        if (e === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) { out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16)); i += 6; continue; }
        err("bad_json", "неверная escape-последовательность");
      }
      if (ch < " ") err("bad_json", "управляющий символ в строке");
      out += ch;
      i++;
    }
    return err("bad_json", "незакрытая строка");
  }
  const v = value(0);
  ws();
  if (i !== text.length) err("bad_json", "лишние данные после JSON");
  return v;
}

// ------------------------------------------------------------------ geometry
function haversine(lon1, lat1, lon2, lat2) {
  const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r, dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
  let a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  a = Math.min(1, Math.max(0, a));
  return 2 * R_EARTH * Math.asin(Math.sqrt(a));
}
const mm = (lon1, lat1, lon2, lat2) => Math.round(haversine(lon1, lat1, lon2, lat2) * 1000);   // metric haversine-mm-v1

// ------------------------------------------------------------------ registry (current slice)
function makeRegistry(D, { sha256hex, placesDigest } = {}) {
  if (!D || !D.cities) fail("bad_context", "нужны данные CITY_EVIDENCE");
  if (typeof sha256hex !== "function") fail("bad_context", "нужна функция sha256hex");
  const cities = {};
  for (const city of CITIES) {
    const c = D.cities[city];
    if (!c) continue;
    const fsha = c.files && c.files.places_social && c.files.places_social.sha256;
    const pd = typeof placesDigest === "function" ? placesDigest(D, city) : null;
    cities[city] = {
      bbox: c.bbox.slice(), release: c.release,
      snapshot: "sha256:" + sha256hex(JSON.stringify([SCHEMA, city, c.release, fsha || null, pd, METRIC_VERSION])),
      sources: Object.fromEntries(CATEGORIES.map((cat) => [cat, c.places.filter((p) => p.group === cat)
        .map((p) => ({ id: String(p.id), lon: p.lon, lat: p.lat })).sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))])),
    };
  }
  return { schema: SCHEMA, metric_version: METRIC_VERSION, cities, sha256hex };
}

// ------------------------------------------------------------------ validation
function validatePlanScenario(input, reg) {
  const obj = typeof input === "string" ? parseStrict(input) : input;
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) fail("bad_shape", "сценарий — JSON-объект");
  for (const k of Object.keys(obj)) if (!ALLOWED_KEYS.has(k)) fail("unknown_field", `поле ${JSON.stringify(k).slice(0, 40)} не допускается`);
  for (const k of REQUIRED_KEYS) if (!has(obj, k)) fail("missing_field", k);
  if (obj.schema_version !== SCHEMA) fail("bad_version", `версия ${String(obj.schema_version).slice(0, 40)} ≠ ${SCHEMA}`);
  if (typeof obj.city_id !== "string" || !reg.cities[obj.city_id]) fail("bad_city", String(obj.city_id).slice(0, 40));
  const C = reg.cities[obj.city_id];
  if (obj.source_snapshot !== C.snapshot) fail("foreign_snapshot", "source_snapshot не совпадает с текущим срезом");
  if (!CATEGORIES.includes(obj.category)) fail("bad_category", String(obj.category).slice(0, 40));
  const bb = C.bbox;
  const intIn = (v, [lo, hi], code, what) => { if (!isInt(v) || v < lo || v > hi) fail(code, `${what}: ожидается целое ${lo}..${hi}`); return v; };
  const coord = (p, what) => {
    if (typeof p.lon !== "number" || typeof p.lat !== "number" || !Number.isFinite(p.lon) || !Number.isFinite(p.lat) ||
        Math.abs(p.lon) > 180 || Math.abs(p.lat) > 90) fail("bad_coord", `${what}: координаты`);
    if (p.lon < bb[0] || p.lon > bb[2] || p.lat < bb[1] || p.lat > bb[3]) fail("outside_bbox", `${what}: вне квадрата среза`);
  };
  const shape = (p, keys, what) => {
    if (!p || typeof p !== "object" || Array.isArray(p)) fail("bad_shape", `${what}: ожидается объект`);
    for (const k of Object.keys(p)) if (!keys.includes(k)) fail("unknown_field", `${what}: поле ${JSON.stringify(k).slice(0, 40)}`);
    for (const k of keys) if (!has(p, k)) fail("missing_field", `${what}.${k}`);
    if (typeof p.id !== "string" || !ID_RE.test(p.id)) fail("bad_id", `${what}: id (A–Z, 0–9, _.-, до ${LIMITS.idMax})`);
  };
  const uniq = (ids, what) => { if (new Set(ids).size !== ids.length) fail("duplicate_id", `${what}: повтор ID`); };

  if (!Array.isArray(obj.control_points)) fail("bad_shape", "control_points — массив");
  const np = obj.control_points.length;
  if (np < LIMITS.points[0] || np > LIMITS.points[1]) fail("bad_count", `контрольных точек ${np}, допустимо ${LIMITS.points.join("..")}`);
  const control_points = obj.control_points.map((p, k) => {
    const what = `control_points[${k}]`;
    shape(p, POINT_KEYS, what);
    coord(p, what);
    intIn(p.weight, LIMITS.weight, "bad_weight", `${what}.weight`);
    return { id: p.id, lon: p.lon, lat: p.lat, weight: p.weight };
  });
  uniq(control_points.map((p) => p.id), "control_points");

  if (!Array.isArray(obj.candidates)) fail("bad_shape", "candidates — массив");
  const nc = obj.candidates.length;
  if (nc > LIMITS.candidates[1]) fail("bad_count", `кандидатов ${nc}, допустимо ${LIMITS.candidates.join("..")}`);
  const candidates = obj.candidates.map((c, k) => {
    const what = `candidates[${k}]`;
    shape(c, CAND_KEYS, what);
    coord(c, what);
    if (c.kind !== "hypothetical") fail("bad_kind", `${what}: kind должен быть hypothetical`);
    if (c.category !== obj.category) fail("bad_category", `${what}: категория ≠ category сценария`);
    intIn(c.cost, LIMITS.cost, "bad_cost", `${what}.cost`);
    return { id: c.id, lon: c.lon, lat: c.lat, category: c.category, kind: "hypothetical", cost: c.cost };
  });
  uniq(candidates.map((c) => c.id), "candidates");
  const candIds = new Set(candidates.map((c) => c.id));

  const budget = intIn(obj.budget, LIMITS.budget, "bad_budget", "budget");
  const max_selected = intIn(obj.max_selected, LIMITS.maxSelected, "bad_max_selected", "max_selected");
  const coverage_radius_m = intIn(obj.coverage_radius_m, LIMITS.radius, "bad_radius", "coverage_radius_m");
  const idList = (key) => {
    const a = obj[key];
    if (!Array.isArray(a)) fail("bad_shape", `${key} — массив ID`);
    for (const id of a) {
      if (typeof id !== "string" || !ID_RE.test(id)) fail("bad_id", `${key}: неверный ID`);
      if (!candIds.has(id)) fail("unknown_id", `${key}: ${id} нет среди кандидатов`);
    }
    uniq(a, key);
    return a.slice().sort();
  };
  const required_ids = idList("required_ids"), excluded_ids = idList("excluded_ids"), selected_ids = idList("selected_ids");
  const both = required_ids.filter((id) => excluded_ids.includes(id));
  if (both.length) fail("conflicting_constraints", `одновременно required и excluded: ${both.join(",").slice(0, 80)}`);
  // derived_results (if any) is ignored: everything is recomputed
  return { schema_version: SCHEMA, city_id: obj.city_id, source_snapshot: C.snapshot, category: obj.category, control_points,
           candidates, budget, max_selected, coverage_radius_m, required_ids, excluded_ids, selected_ids };
}

// ------------------------------------------------------------------ evaluation
// Distance matrix once per scenario: base_mm[p] (nearest source), cand_mm[p][j]. Ties: (mm, kind source<hypothetical, id).
function precompute(reg, sc) {
  const sources = reg.cities[sc.city_id].sources[sc.category];
  const order = sc.candidates.map((c, j) => j).sort((a, b) => (sc.candidates[a].id < sc.candidates[b].id ? -1 : 1));
  const cands = order.map((j) => sc.candidates[j]);   // canonical order: sorted by id
  const pts = sc.control_points.slice().sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const base = pts.map((p) => {
    let best = null;
    for (const s of sources) {
      const d = mm(p.lon, p.lat, s.lon, s.lat);
      if (best === null || d < best.mm || (d === best.mm && s.id < best.id)) best = { mm: d, id: s.id };
    }
    return best;
  });
  const cm = pts.map((p) => cands.map((c) => mm(p.lon, p.lat, c.lon, c.lat)));
  return { pts, cands, base, cm, sources: sources.length };
}

function metricsFor(pre, sc, mask) {
  let unknown = 0, wsum = 0, wtot = 0, max = -1, covered = 0, cost = 0;
  const R = sc.coverage_radius_m * 1000;
  for (let j = 0; j < pre.cands.length; j++) if (mask & (1 << j)) cost += pre.cands[j].cost;
  for (let p = 0; p < pre.pts.length; p++) {
    const w = pre.pts[p].weight;
    wtot += w;
    let a = pre.base[p] ? pre.base[p].mm : null;
    const row = pre.cm[p];
    for (let j = 0; j < row.length; j++) if (mask & (1 << j)) { if (a === null || row[j] < a) a = row[j]; }
    if (a === null) { unknown++; continue; }
    wsum += w * a;
    if (a > max) max = a;
    if (a <= R) covered += w;
  }
  return { unknown_count: unknown, weighted_sum_mm: wsum, weighted_mean_mm: unknown === 0 ? wsum / wtot : null,
           max_mm: unknown === 0 ? max : null, covered_weight: covered, total_weight: wtot, coverage_fraction: covered / wtot, cost };
}

const maskIds = (pre, mask) => pre.cands.filter((c, j) => mask & (1 << j)).map((c) => c.id);   // sorted (cands sorted)

function feasibility(sc, ids, cost) {
  const reasons = [];
  if (cost > sc.budget) reasons.push("over_budget");
  if (ids.length > sc.max_selected) reasons.push("over_max_selected");
  if (sc.required_ids.some((id) => !ids.includes(id))) reasons.push("missing_required");
  if (sc.excluded_ids.some((id) => ids.includes(id))) reasons.push("includes_excluded");
  return { feasible: reasons.length === 0, reasons };
}

function evaluatePlan(reg, sc, selectedIds) {
  if (!Array.isArray(selectedIds)) fail("bad_shape", "selectedIds — массив");
  const pre = precompute(reg, sc);
  const index = new Map(pre.cands.map((c, j) => [c.id, j]));
  let mask = 0;
  for (const id of selectedIds) {
    if (!index.has(id)) fail("unknown_id", `${id} нет среди кандидатов`);
    if (mask & (1 << index.get(id))) fail("duplicate_id", id);
    mask |= 1 << index.get(id);
  }
  const R = sc.coverage_radius_m * 1000;
  const rows = pre.pts.map((p, k) => {
    const b = pre.base[k];
    let after = b ? { mm: b.mm, kind: "source", id: b.id } : null;
    pre.cands.forEach((c, j) => {
      if (!(mask & (1 << j))) return;
      const d = pre.cm[k][j];
      if (after === null || d < after.mm) after = { mm: d, kind: "hypothetical", id: c.id };   // tie keeps the source
    });
    return { id: p.id, weight: p.weight, before_mm: b ? b.mm : null, before_ref: b ? { kind: "source", id: b.id } : null,
             after_mm: after ? after.mm : null, after_ref: after ? { kind: after.kind, id: after.id } : null,
             delta_mm: b && after ? b.mm - after.mm : null, covered: after !== null && after.mm <= R };
  });
  const ids = maskIds(pre, mask);
  const metrics = metricsFor(pre, sc, mask);
  return { selected_ids: ids, rows, metrics, feasibility: feasibility(sc, ids, metrics.cost), metric_version: METRIC_VERSION,
           baseline_records: pre.sources };
}

// ------------------------------------------------------------------ digests (order-independent)
function canonical(x) {
  if (Array.isArray(x)) return "[" + x.map(canonical).join(",") + "]";
  if (x && typeof x === "object") return "{" + Object.keys(x).sort().map((k) => JSON.stringify(k) + ":" + canonical(x[k])).join(",") + "}";
  return JSON.stringify(x);
}
function problemOf(sc) {
  const byId = (a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  return { schema: SCHEMA, metric_version: METRIC_VERSION, source_snapshot: sc.source_snapshot, city_id: sc.city_id, category: sc.category,
           control_points: sc.control_points.slice().sort(byId).map((p) => [p.id, p.lon, p.lat, p.weight]),
           candidates: sc.candidates.slice().sort(byId).map((c) => [c.id, c.lon, c.lat, c.category, c.kind, c.cost]),
           budget: sc.budget, max_selected: sc.max_selected, coverage_radius_m: sc.coverage_radius_m,
           required_ids: sc.required_ids.slice().sort(), excluded_ids: sc.excluded_ids.slice().sort() };
}
const problemDigest = (reg, sc) => reg.sha256hex(canonical(problemOf(sc)));
const scenarioDigest = (reg, sc) => reg.sha256hex(canonical({ ...problemOf(sc), selected_ids: sc.selected_ids.slice().sort() }));

// ------------------------------------------------------------------ exact search
function cmpIds(a, b) {
  for (let k = 0; k < Math.min(a.length, b.length); k++) if (a[k] !== b[k]) return a[k] < b[k] ? -1 : 1;
  return a.length - b.length;
}
function cmpKey(a, b) {
  for (let k = 0; k < a.length; k++) {
    if (Array.isArray(a[k])) { const c = cmpIds(a[k], b[k]); if (c) return c; continue; }
    if (a[k] !== b[k]) return a[k] < b[k] ? -1 : 1;
  }
  return 0;
}
const INF = Number.POSITIVE_INFINITY;
const KEYS = {
  mean: (m, ids) => [m.unknown_count, m.weighted_sum_mm, m.max_mm === null ? INF : m.max_mm, m.cost, ids],
  minimax: (m, ids) => [m.unknown_count, m.max_mm === null ? INF : m.max_mm, m.weighted_sum_mm, m.cost, ids],
  coverage: (m, ids) => [-m.covered_weight, m.unknown_count, m.weighted_sum_mm, m.max_mm === null ? INF : m.max_mm, m.cost, ids],
};

function searchState(reg, sc, budget) {
  const pre = precompute(reg, sc);
  const n = pre.cands.length;
  const pos = new Map(pre.cands.map((c, j) => [c.id, j]));
  const req = sc.required_ids.reduce((m, id) => m | (1 << pos.get(id)), 0);
  const exc = sc.excluded_ids.reduce((m, id) => m | (1 << pos.get(id)), 0);
  return { pre, n, req, exc, budget, total: 2 ** n, next: 0, evaluated: 0, feasible: 0, best: {}, pareto: [] };
}

function stepSearch(st, sc, limit) {
  const end = Math.min(st.total, st.next + limit);
  for (let mask = st.next; mask < end; mask++) {
    if (mask & st.exc || (mask & st.req) !== st.req) continue;
    st.evaluated++;
    let cnt = 0, cost = 0;
    for (let j = 0; j < st.n; j++) if (mask & (1 << j)) { cnt++; cost += st.pre.cands[j].cost; }
    if (cnt > sc.max_selected || cost > st.budget) continue;
    st.feasible++;
    const m = metricsFor(st.pre, sc, mask);
    const ids = maskIds(st.pre, mask);
    for (const [name, key] of Object.entries(KEYS)) {
      const k = key(m, ids);
      if (!st.best[name] || cmpKey(k, st.best[name].key) < 0) st.best[name] = { key: k, ids, metrics: m };
    }
    if (m.unknown_count === 0) st.pareto.push({ cost: m.cost, weighted_sum_mm: m.weighted_sum_mm, ids });
  }
  st.next = end;
  return st.next >= st.total;
}

function paretoFront(points) {
  const s = points.slice().sort((a, b) => a.cost - b.cost || a.weighted_sum_mm - b.weighted_sum_mm || cmpIds(a.ids, b.ids));
  const out = [];
  let best = INF;
  for (const p of s) {
    const last = out[out.length - 1];
    if (last && last.cost === p.cost && last.weighted_sum_mm === p.weighted_sum_mm) continue;   // equal pair: keep smallest ids
    if (p.weighted_sum_mm < best) { out.push({ cost: p.cost, weighted_sum_mm: p.weighted_sum_mm, selected_ids: p.ids }); best = p.weighted_sum_mm; }
  }
  return out;
}

function infeasibleReasons(sc, budget) {
  const reasons = [];
  const reqCost = sc.candidates.filter((c) => sc.required_ids.includes(c.id)).reduce((s, c) => s + c.cost, 0);
  if (sc.required_ids.length > sc.max_selected) reasons.push("required_count_exceeds_max_selected");
  if (reqCost > budget) reasons.push("required_cost_exceeds_budget");
  return reasons.length ? reasons : ["no_feasible_subset"];
}

function finish(st, sc, digest, extra = {}) {
  const status = st.feasible ? "optimal" : "infeasible";
  const objectives = {};
  for (const name of Object.keys(KEYS)) objectives[name] = st.best[name] ? { selected_ids: st.best[name].ids, metrics: st.best[name].metrics } : null;
  return { status, reasons: status === "infeasible" ? infeasibleReasons(sc, st.budget) : [], objectives,
           pareto: paretoFront(st.pareto), evaluated: st.evaluated, feasible_count: st.feasible,
           problem_digest: digest, metric_version: METRIC_VERSION, budget: st.budget, ...extra };
}

function tooLarge(reg, sc, n) {
  return { status: "too_large", reasons: [`candidates ${n} > ${LIMITS.exactMaxCandidates}: точный перебор не выполняется`],
           objectives: { mean: null, minimax: null, coverage: null }, pareto: [], evaluated: 0, feasible_count: 0,
           problem_digest: problemDigest(reg, sc), metric_version: METRIC_VERSION };
}

function optimizePlans(reg, sc, options = {}) {
  if (sc.candidates.length > LIMITS.exactMaxCandidates) return tooLarge(reg, sc, sc.candidates.length);   // refuse before enumeration
  const digest = problemDigest(reg, sc);
  const run = (budget) => { const st = searchState(reg, sc, budget); stepSearch(st, sc, st.total); return finish(st, sc, digest); };
  const main = run(sc.budget);
  if (options.sensitivity === false) return main;
  const budgets = [...new Set([0, Math.floor(sc.budget / 2), sc.budget])];
  main.sensitivity = budgets.map((b) => {
    const r = b === sc.budget ? main : run(b);
    return { budget: b, status: r.status, reasons: r.reasons, feasible_count: r.feasible_count,
             mean: r.objectives.mean && { selected_ids: r.objectives.mean.selected_ids, cost: r.objectives.mean.metrics.cost,
                                          weighted_sum_mm: r.objectives.mean.metrics.weighted_sum_mm, unknown_count: r.objectives.mean.metrics.unknown_count } };
  });
  return main;
}

// Cancellable, chunked search. Never reports "optimal" unless the enumeration completed.
async function optimizePlansAsync(reg, sc, { requestId = null, signal = null, chunk = 4096, yieldFn = () => new Promise((r) => setTimeout(r, 0)) } = {}) {
  if (sc.candidates.length > LIMITS.exactMaxCandidates) return { ...tooLarge(reg, sc, sc.candidates.length), request_id: requestId };
  const digest = problemDigest(reg, sc);
  const st = searchState(reg, sc, sc.budget);
  for (;;) {
    if (signal && signal.aborted) {
      return { status: "cancelled", reasons: ["cancelled"], objectives: { mean: null, minimax: null, coverage: null }, pareto: [],
               evaluated: st.evaluated, feasible_count: st.feasible, problem_digest: digest, metric_version: METRIC_VERSION,
               request_id: requestId, complete: false };
    }
    if (stepSearch(st, sc, chunk)) break;
    await yieldFn();
  }
  return finish(st, sc, digest, { request_id: requestId, complete: true });
}

// Accepts only the latest request for the current problem; resets on city/category change.
class ResultGate {
  constructor() { this.seq = 0; this.pending = null; this.digest = null; }
  begin(problemDigest) { this.seq += 1; this.pending = `req-${this.seq}`; this.digest = problemDigest; return this.pending; }
  reset() { this.pending = null; this.digest = null; }
  accept(result) {
    if (!result || this.pending === null) return { accepted: false, reason: "no_pending_request" };
    if (result.request_id !== this.pending) return { accepted: false, reason: "stale_request" };
    if (result.problem_digest !== this.digest) return { accepted: false, reason: "stale_problem" };
    if (result.status !== "optimal" && result.status !== "infeasible") return { accepted: false, reason: `status_${result.status}` };
    this.pending = null;
    return { accepted: true, reason: null };
  }
}

// Atomic import: the passed state is never changed; on success a new state object is returned.
function importPlanScenario(text, reg, state) {
  try {
    const sc = validatePlanScenario(text, reg);
    return { ok: true, code: null, state: { scenario: sc, evaluation: evaluatePlan(reg, sc, sc.selected_ids) } };
  } catch (e) {
    return { ok: false, code: e instanceof PlanError ? e.code : "internal_error", message: String(e && e.message), state };
  }
}

module.exports = { SCHEMA, METRIC_VERSION, LIMITS, PlanError, parseStrict, haversine, makeRegistry, validatePlanScenario,
  evaluatePlan, optimizePlans, optimizePlansAsync, ResultGate, importPlanScenario, problemDigest, scenarioDigest, canonical };
