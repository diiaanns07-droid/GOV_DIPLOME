/* city-plan-v2 — точная оценка и оптимизация набора условных соцобъектов (CORE_SPEC round 8). K05 round 8.
 * Чистый модуль: без DOM и сети; браузер (window.CITY_PLAN) и Node (module.exports). Headless API:
 *
 *   parsePlanJSON(text)                       -> object (строгий JSON ≤256 KiB) | throws PlanError
 *   validatePlanScenario(input, context)      -> {ok:true, scenario} | {ok:false, error:{code, message, path}}
 *   prepareProblem(context, scenario)         -> problem (матрица расстояний в мм считается ОДИН раз)
 *   evaluatePlan(context, scenario, ids)      -> {rows, metrics, feasibility, plan_ids}
 *   optimizePlans(context, scenario, options) -> {status, objectives, pareto, sensitivity, evaluated, total,
 *                                                 feasible_count, problem_digest, metric_version, ...}
 *   optimizePlansAsync(context, scenario, options) -> Promise (чанки, onProgress, signal/shouldCancel)
 *   problemDigest(scenario), scenarioDigest(scenario), isCurrent(result, digest, requestId)
 *
 * Только расстояния ПО ПРЯМОЙ до контрольных точек в срезе. Не время пути, не население, не вместимость.
 * Стоимости и бюджет — условные единицы пользователя, не тенге и не смета.
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-plan-v2";
  const METRIC_VERSION = "haversine-mm-v1";
  const RESULT_SCHEMA = "city-plan-result-v2";
  const R_EARTH_M = 6371008.8;
  const CITIES = ["shymkent", "astana"];
  const CATEGORIES = ["school", "outpatient_clinic"];
  const LIM = { points: [1, 25], candidates: [0, 16], weight: [1, 100], cost: [1, 1000000], budget: [0, 1000000],
    max_selected: [0, 5], radius: [100, 5000], idLen: 64, bytes: 256 * 1024 };
  const KEYS = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
    "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"];
  const OPTIONAL_KEYS = ["derived_results"];
  const ID_RE = /^[A-Za-z0-9_.-]{1,64}$/;

  class PlanError extends Error {
    constructor(code, message, path) { super(message); this.code = code; this.path = path || null; }
  }

  // ---------------- геометрия ----------------
  function haversineM(lon1, lat1, lon2, lat2) {
    const rad = Math.PI / 180;
    const dp = (lat2 - lat1) * rad, dl = (lon2 - lon1) * rad;
    let a = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dl / 2) ** 2;
    a = Math.min(1, Math.max(0, a));
    return 2 * R_EARTH_M * Math.asin(Math.sqrt(a));
  }
  const distMm = (lon1, lat1, lon2, lat2) => Math.round(haversineM(lon1, lat1, lon2, lat2) * 1000);

  // ---------------- SHA-256 и каноническая форма (для digest) ----------------
  const K = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb,
    0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f,
    0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
  function utf8(str) {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(str);
    return Uint8Array.from(Buffer.from(str, "utf8"));
  }
  function sha256Hex(str) {
    const msg = utf8(str), l = msg.length, nb = (l + 9 + 63) >> 6;
    const buf = new Uint8Array(nb * 64); buf.set(msg); buf[l] = 0x80;
    const dv = new DataView(buf.buffer), bits = l * 8;
    dv.setUint32(buf.length - 4, bits >>> 0); dv.setUint32(buf.length - 8, Math.floor(bits / 2 ** 32));
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const W = new Uint32Array(64), rotr = (x, n) => (x >>> n) | (x << (32 - n));
    for (let b = 0; b < nb; b++) {
      for (let i = 0; i < 16; i++) W[i] = dv.getUint32(b * 64 + i * 4);
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >>> 3);
        const s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      let [a, b2, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + W[i]) >>> 0;
        const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b2) ^ (a & c) ^ (b2 & c))) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b2; b2 = a; a = (t1 + t2) >>> 0;
      }
      H[0] += a; H[1] += b2; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    return Array.from(H, (x) => x.toString(16).padStart(8, "0")).join("");
  }
  function canon(v) {
    if (v === null || typeof v !== "object") return JSON.stringify(v);
    if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
    return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}";
  }
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

  // ---------------- строгий JSON ----------------
  function parsePlanJSON(text) {
    if (typeof text !== "string") throw new PlanError("bad_json", "ожидается текст");
    if (utf8(text).length > LIM.bytes) throw new PlanError("too_large", `больше ${LIM.bytes} байт`);
    let i = text.charCodeAt(0) === 0xfeff ? 1 : 0;
    const err = (m) => { throw new PlanError("bad_json", `${m} (позиция ${i})`); };
    const ws = () => { while (i < text.length && " \t\n\r".includes(text[i])) i++; };
    function str() {
      i++; let out = "";
      while (i < text.length) {
        const ch = text[i];
        if (ch === '"') { i++; return out; }
        if (ch === "\\") {
          const e = text[i + 1], map = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
          if (e in map) { out += map[e]; i += 2; continue; }
          if (e === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) { out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16)); i += 6; continue; }
          err("неверная escape-последовательность");
        }
        if (ch < " ") err("управляющий символ в строке");
        out += ch; i++;
      }
      return err("незакрытая строка");
    }
    function value(depth) {
      if (depth > 32) err("слишком глубокая вложенность");
      ws();
      const ch = text[i];
      if (ch === "{") {
        i++; const obj = Object.create(null); ws();
        if (text[i] === "}") { i++; return obj; }
        for (;;) {
          ws(); if (text[i] !== '"') err("ожидается ключ");
          const k = str();
          if (Object.prototype.hasOwnProperty.call(obj, k)) err(`повтор ключа ${JSON.stringify(k)}`);
          ws(); if (text[i] !== ":") err("ожидается :"); i++;
          obj[k] = value(depth + 1); ws();
          if (text[i] === ",") { i++; continue; }
          if (text[i] === "}") { i++; return obj; }
          err("ожидается , или }");
        }
      }
      if (ch === "[") {
        i++; const arr = []; ws();
        if (text[i] === "]") { i++; return arr; }
        for (;;) {
          arr.push(value(depth + 1)); ws();
          if (text[i] === ",") { i++; continue; }
          if (text[i] === "]") { i++; return arr; }
          err("ожидается , или ]");
        }
      }
      if (ch === '"') return str();
      if (text.startsWith("true", i)) { i += 4; return true; }
      if (text.startsWith("false", i)) { i += 5; return false; }
      if (text.startsWith("null", i)) { i += 4; return null; }
      const m = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i, i + 64));
      if (!m) err("недопустимый токен (NaN/Infinity не допускаются)");
      i += m[0].length;
      const v = Number(m[0]);
      if (!Number.isFinite(v)) err(`число ${m[0]} не конечно`);
      return v;
    }
    const v = value(0); ws();
    if (i !== text.length) err("лишние данные после JSON");
    return v;
  }

  // ---------------- контекст ----------------
  // context: {city_id, category?, bbox:[xmin,ymin,xmax,ymax], source_snapshot, records:[{id,lon,lat,group}], versions?}
  // source_snapshot вычисляет вызывающий код из актуальных данных (в сборке — whatif.sourceSnapshot).
  function contextFromCityData(cityKey, cityData, sourceSnapshot, versions) {
    return { city_id: cityKey, bbox: cityData.bbox.slice(), source_snapshot: sourceSnapshot,
      records: cityData.places.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, group: p.group })),
      versions: versions || { release: cityData.release } };
  }

  // ---------------- валидация ----------------
  function validatePlanScenario(input, context) {
    try { return { ok: true, scenario: checkScenario(input, context) }; }
    catch (e) {
      if (e instanceof PlanError) return { ok: false, error: { code: e.code, message: e.message, path: e.path } };
      throw e;
    }
  }

  function checkScenario(o, ctx) {
    const fail = (code, msg, path) => { throw new PlanError(code, msg, path); };
    if (!o || typeof o !== "object" || Array.isArray(o)) fail("bad_type", "ожидается объект", "$");
    for (const k of Object.keys(o)) if (!KEYS.includes(k) && !OPTIONAL_KEYS.includes(k)) fail("unknown_field", `неожиданное поле ${k}`, k);
    for (const k of KEYS) if (!(k in o)) fail("missing_field", `нет поля ${k}`, k);
    if (o.schema_version !== SCHEMA) fail("bad_version", `ожидается ${SCHEMA}`, "schema_version");
    if (!CITIES.includes(o.city_id)) fail("bad_city", "неизвестный город", "city_id");
    if (!ctx || o.city_id !== ctx.city_id) fail("foreign_city", "сценарий другого города", "city_id");
    if (o.source_snapshot !== ctx.source_snapshot) fail("foreign_snapshot", "сценарий сделан на другом срезе данных", "source_snapshot");
    if (!CATEGORIES.includes(o.category)) fail("bad_category", "только school или outpatient_clinic", "category");
    const int = (v, [lo, hi], path) => { if (!Number.isInteger(v) || v < lo || v > hi) fail("bad_number", `${path}: целое ${lo}..${hi}`, path); return v; };
    const bb = ctx.bbox;
    const coord = (p, path) => {
      if (typeof p.lon !== "number" || typeof p.lat !== "number" || !Number.isFinite(p.lon) || !Number.isFinite(p.lat)
        || p.lon < -180 || p.lon > 180 || p.lat < -90 || p.lat > 90) fail("bad_coord", `${path}: координаты`, path);
      if (!(bb[0] <= p.lon && p.lon <= bb[2] && bb[1] <= p.lat && p.lat <= bb[3])) fail("outside_bbox", `${path}: вне квадрата среза`, path);
    };
    const id = (v, path) => {
      if (typeof v !== "string" || !ID_RE.test(v)) fail("bad_id", `${path}: id 1..64 символа [A-Za-z0-9_.-]`, path);
      return v;
    };
    const objKeys = (p, allowed, path) => {
      if (!p || typeof p !== "object" || Array.isArray(p)) fail("bad_type", `${path}: ожидается объект`, path);
      for (const k of Object.keys(p)) if (!allowed.includes(k)) fail("unknown_field", `${path}.${k}`, `${path}.${k}`);
      for (const k of allowed) if (!(k in p)) fail("missing_field", `${path}.${k}`, `${path}.${k}`);
    };
    if (!Array.isArray(o.control_points)) fail("bad_type", "control_points: список", "control_points");
    if (o.control_points.length < LIM.points[0] || o.control_points.length > LIM.points[1]) fail("bad_count", `контрольных точек ${LIM.points[0]}..${LIM.points[1]}`, "control_points");
    const pIds = new Set();
    const points = o.control_points.map((p, i) => {
      const path = `control_points[${i}]`;
      objKeys(p, ["id", "lon", "lat", "weight"], path);
      id(p.id, `${path}.id`);
      if (pIds.has(p.id)) fail("duplicate_id", `повтор id ${p.id}`, `${path}.id`);
      pIds.add(p.id); coord(p, path);
      return { id: p.id, lon: p.lon, lat: p.lat, weight: int(p.weight, LIM.weight, `${path}.weight`) };
    });
    if (!Array.isArray(o.candidates)) fail("bad_type", "candidates: список", "candidates");
    if (o.candidates.length > LIM.candidates[1]) fail("bad_count", `кандидатов не больше ${LIM.candidates[1]} (точный перебор)`, "candidates");
    const cIds = new Set();
    const candidates = o.candidates.map((c, i) => {
      const path = `candidates[${i}]`;
      objKeys(c, ["id", "lon", "lat", "category", "kind", "cost"], path);
      id(c.id, `${path}.id`);
      if (cIds.has(c.id)) fail("duplicate_id", `повтор id ${c.id}`, `${path}.id`);
      cIds.add(c.id); coord(c, path);
      if (c.category !== o.category) fail("category_mismatch", `${path}: категория кандидата ≠ category`, `${path}.category`);
      if (c.kind !== "hypothetical") fail("bad_kind", `${path}: kind должен быть hypothetical`, `${path}.kind`);
      return { id: c.id, lon: c.lon, lat: c.lat, category: c.category, kind: "hypothetical", cost: int(c.cost, LIM.cost, `${path}.cost`) };
    });
    const budget = int(o.budget, LIM.budget, "budget");
    const max_selected = int(o.max_selected, LIM.max_selected, "max_selected");
    const coverage_radius_m = int(o.coverage_radius_m, LIM.radius, "coverage_radius_m");
    const idList = (arr, path) => {
      if (!Array.isArray(arr)) fail("bad_type", `${path}: список`, path);
      const s = new Set();
      arr.forEach((v, i) => {
        id(v, `${path}[${i}]`);
        if (s.has(v)) fail("duplicate_id", `${path}: повтор ${v}`, `${path}[${i}]`);
        if (!cIds.has(v)) fail("unknown_candidate", `${path}: нет кандидата ${v}`, `${path}[${i}]`);
        s.add(v);
      });
      return arr.slice().sort(cmpStr);
    };
    const required_ids = idList(o.required_ids, "required_ids");
    const excluded_ids = idList(o.excluded_ids, "excluded_ids");
    const selected_ids = idList(o.selected_ids, "selected_ids");
    const both = required_ids.filter((x) => excluded_ids.includes(x));
    if (both.length) fail("required_excluded_overlap", `одновременно required и excluded: ${both.join(", ")}`, "required_ids");
    return { schema_version: SCHEMA, city_id: o.city_id, source_snapshot: o.source_snapshot, category: o.category,
      control_points: points, candidates, budget, max_selected, coverage_radius_m, required_ids, excluded_ids, selected_ids };
  }

  // ---------------- digest ----------------
  function problemBody(s) {
    return { schema: SCHEMA, metric_version: METRIC_VERSION, city_id: s.city_id, category: s.category, source_snapshot: s.source_snapshot,
      control_points: s.control_points.map((p) => [p.id, p.lon, p.lat, p.weight]).sort((a, b) => cmpStr(a[0], b[0])),
      candidates: s.candidates.map((c) => [c.id, c.lon, c.lat, c.cost, c.category, c.kind]).sort((a, b) => cmpStr(a[0], b[0])),
      budget: s.budget, max_selected: s.max_selected, coverage_radius_m: s.coverage_radius_m,
      required_ids: s.required_ids.slice().sort(cmpStr), excluded_ids: s.excluded_ids.slice().sort(cmpStr) };
  }
  const problemDigest = (s) => "plan2-sha256:" + sha256Hex(canon(problemBody(s)));
  const scenarioDigest = (s) => "plan2s-sha256:" + sha256Hex(canon({ ...problemBody(s), selected_ids: s.selected_ids.slice().sort(cmpStr) }));

  // ---------------- подготовка: расстояния один раз ----------------
  // Ключ ближайшего: (мм, пространство source=0 < candidate=1, id) — порядок входных массивов не влияет.
  function prepareProblem(ctx, s) {
    const src = ctx.records.filter((r) => r.group === s.category);
    // кандидаты в каноническом порядке id: бит j маски = candidates[j] в этом порядке
    const cands = s.candidates.slice().sort((a, b) => cmpStr(a.id, b.id));
    const n = cands.length, m = s.control_points.length;
    const points = s.control_points.slice().sort((a, b) => cmpStr(a.id, b.id));
    const baseMm = new Array(m).fill(null), baseId = new Array(m).fill(null);
    const candMm = Array.from({ length: m }, () => new Float64Array(n));
    let haversineCalls = 0;
    points.forEach((p, i) => {
      for (const r of src) {
        const d = distMm(p.lon, p.lat, r.lon, r.lat); haversineCalls++;
        if (baseMm[i] === null || d < baseMm[i] || (d === baseMm[i] && r.id < baseId[i])) { baseMm[i] = d; baseId[i] = r.id; }
      }
      cands.forEach((c, j) => { candMm[i][j] = distMm(p.lon, p.lat, c.lon, c.lat); haversineCalls++; });
    });
    const idx = new Map(cands.map((c, j) => [c.id, j]));
    const maskOf = (ids) => ids.reduce((acc, x) => acc | (1 << idx.get(x)), 0);
    return { scenario: s, points, cands, n, m, baseMm, baseId, candMm, weights: points.map((p) => p.weight),
      totalWeight: points.reduce((a, p) => a + p.weight, 0), radiusMm: s.coverage_radius_m * 1000,
      requiredMask: maskOf(s.required_ids), excludedMask: maskOf(s.excluded_ids), costs: cands.map((c) => c.cost),
      n_source_records: src.length, haversineCalls, idx };
  }

  // ---------------- оценка подмножества (без гаверсинуса) ----------------
  function popcount(x) { let c = 0; while (x) { x &= x - 1; c++; } return c; }

  function feasibility(P, mask, budget) {
    const reasons = [];
    let cost = 0;
    for (let j = 0; j < P.n; j++) if (mask & (1 << j)) cost += P.costs[j];
    const k = popcount(mask);
    if (cost > budget) reasons.push("over_budget");
    if (k > P.scenario.max_selected) reasons.push("too_many_selected");
    if ((mask & P.requiredMask) !== P.requiredMask) reasons.push("missing_required");
    if (mask & P.excludedMask) reasons.push("includes_excluded");
    return { feasible: reasons.length === 0, reasons, cost, count: k };
  }

  function metricsOf(P, mask, withRows) {
    let unknown = 0, wsum = 0, maxMm = -1, covered = 0;
    const rows = withRows ? [] : null;
    for (let i = 0; i < P.m; i++) {
      let best = P.baseMm[i], ns = best === null ? null : "source", bid = P.baseId[i];
      for (let j = 0; j < P.n; j++) {
        if (!(mask & (1 << j))) continue;
        const d = P.candMm[i][j];
        // source выигрывает ничью у кандидата; среди кандидатов — меньший id (кандидаты отсортированы по id)
        if (best === null || d < best) { best = d; ns = "candidate"; bid = P.cands[j].id; }
      }
      if (best === null) unknown++;
      else {
        wsum += P.weights[i] * best;
        if (best > maxMm) maxMm = best;
        if (best <= P.radiusMm) covered += P.weights[i];
      }
      if (withRows) {
        const before = P.baseMm[i];
        rows.push({ point_id: P.points[i].id, weight: P.weights[i], before_mm: before,
          before_ref: before === null ? null : { ns: "source", id: P.baseId[i], kind: "observed_secondary" },
          after_mm: best, after_ref: best === null ? null : { ns, id: bid, kind: ns === "source" ? "observed_secondary" : "hypothetical" },
          delta_mm: before === null || best === null ? null : before - best,
          covered: best !== null && best <= P.radiusMm });
      }
    }
    const metrics = { unknown_count: unknown, weighted_sum_mm: wsum,
      weighted_mean_mm: unknown === 0 ? wsum / P.totalWeight : null,
      max_mm: unknown === 0 && P.m > 0 ? maxMm : null,
      covered_weight: covered, total_weight: P.totalWeight, coverage_fraction: covered / P.totalWeight };
    return { metrics, rows };
  }

  function idsOf(P, mask) {
    const out = [];
    for (let j = 0; j < P.n; j++) if (mask & (1 << j)) out.push(P.cands[j].id);
    return out; // уже по возрастанию id
  }

  function evaluatePlan(ctx, scenario, selectedIds, prepared) {
    const P = prepared || prepareProblem(ctx, scenario);
    const ids = (selectedIds || scenario.selected_ids).slice();
    for (const x of ids) if (!P.idx.has(x)) throw new PlanError("unknown_candidate", `нет кандидата ${x}`, "selected_ids");
    if (new Set(ids).size !== ids.length) throw new PlanError("duplicate_id", "повтор id в плане", "selected_ids");
    const mask = ids.reduce((a, x) => a | (1 << P.idx.get(x)), 0);
    const f = feasibility(P, mask, scenario.budget);
    const { metrics, rows } = metricsOf(P, mask, true);
    return { plan_ids: idsOf(P, mask), cost: f.cost, feasibility: { feasible: f.feasible, reasons: f.reasons },
      metrics: { ...metrics, cost: f.cost }, rows, n_source_records: P.n_source_records, metric_version: METRIC_VERSION };
  }

  // ---------------- лексикографические ключи ----------------
  const INF = Number.POSITIVE_INFINITY;
  function cmpIds(a, b) {
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) { const c = cmpStr(a[i], b[i]); if (c) return c; }
    return a.length - b.length;
  }
  function keyOf(obj, met, cost, ids) {
    const mx = met.max_mm === null ? INF : met.max_mm;
    if (obj === "mean") return [met.unknown_count, met.weighted_sum_mm, mx, cost, ids];
    if (obj === "minimax") return [met.unknown_count, mx, met.weighted_sum_mm, cost, ids];
    return [-met.covered_weight, met.unknown_count, met.weighted_sum_mm, mx, cost, ids];
  }
  function cmpKey(a, b) {
    for (let i = 0; i < a.length; i++) {
      if (Array.isArray(a[i])) { const c = cmpIds(a[i], b[i]); if (c) return c; continue; }
      if (a[i] < b[i]) return -1;
      if (a[i] > b[i]) return 1;
    }
    return 0;
  }
  const OBJECTIVES = ["mean", "minimax", "coverage"];

  // ---------------- точный перебор ----------------
  function quickInfeasible(P, budget) {
    const reasons = [];
    let reqCost = 0;
    for (let j = 0; j < P.n; j++) if (P.requiredMask & (1 << j)) reqCost += P.costs[j];
    const reqN = popcount(P.requiredMask);
    if (reqN > P.scenario.max_selected) reasons.push(`required (${reqN}) больше max_selected (${P.scenario.max_selected})`);
    if (reqCost > budget) reasons.push(`стоимость required (${reqCost}) больше бюджета (${budget})`);
    return reasons;
  }

  function newSearch(P, budget) {
    return { P, budget, total: 2 ** P.n, next: 0, evaluated: 0, feasible_count: 0, best: {}, cand: [] };
  }

  // Обрабатывает маски [st.next, st.next+limit). Pareto-кандидаты копятся (только unknown_count=0).
  function step(st, limit) {
    const { P, budget } = st;
    const end = Math.min(st.total, st.next + limit);
    for (let mask = st.next; mask < end; mask++) {
      st.evaluated++;
      if ((mask & P.requiredMask) !== P.requiredMask || (mask & P.excludedMask) || popcount(mask) > P.scenario.max_selected) continue;
      let cost = 0;
      for (let j = 0; j < P.n; j++) if (mask & (1 << j)) cost += P.costs[j];
      if (cost > budget) continue;
      st.feasible_count++;
      const { metrics } = metricsOf(P, mask, false);
      const ids = idsOf(P, mask);
      for (const obj of OBJECTIVES) {
        const k = keyOf(obj, metrics, cost, ids);
        if (!st.best[obj] || cmpKey(k, st.best[obj].key) < 0) st.best[obj] = { key: k, mask, metrics, cost, ids };
      }
      if (metrics.unknown_count === 0) st.cand.push({ cost, wsum: metrics.weighted_sum_mm, ids, mask, metrics });
    }
    st.next = end;
    return st.next >= st.total;
  }

  function paretoOf(cands) {
    // сортировка (cost, wsum, ids); оставить строго улучшающие wsum — это и есть недоминируемые; равные пары свернуть к первому по ids
    const sorted = cands.slice().sort((a, b) => a.cost - b.cost || a.wsum - b.wsum || cmpIds(a.ids, b.ids));
    const out = [];
    let bestW = INF;
    for (const c of sorted) {
      if (c.wsum < bestW) { out.push(c); bestW = c.wsum; }
    }
    return out;
  }

  function planOut(P, b) {
    if (!b) return null;
    return { ids: b.ids, cost: b.cost, metrics: { ...b.metrics, cost: b.cost } };
  }

  function finish(st, statusOverride) {
    const P = st.P, complete = st.next >= st.total;
    const objectives = {};
    for (const o of OBJECTIVES) objectives[o] = planOut(P, st.best[o]);
    const pareto = complete ? paretoOf(st.cand).map((c) => ({ ids: c.ids, cost: c.cost, weighted_sum_mm: c.wsum, metrics: { ...c.metrics, cost: c.cost } })) : null;
    let status;
    if (statusOverride) status = statusOverride;
    else if (!complete) status = "incomplete";
    else status = st.feasible_count ? "optimal" : "infeasible";
    // одинаковые планы разных целей помечаются, чтобы не создавать видимость трёх разных решений
    const same = {};
    for (const o of OBJECTIVES) if (objectives[o]) same[o] = OBJECTIVES.filter((q) => q !== o && objectives[q] && cmpIds(objectives[q].ids, objectives[o].ids) === 0);
    return { status, complete, evaluated: st.evaluated, total: st.total, feasible_count: st.feasible_count,
      objectives: status === "optimal" ? objectives : (complete ? objectives : null),
      best_so_far: !complete ? objectives : undefined,
      same_plan_as: same, pareto, pareto_excluded_partial: complete ? st.feasible_count - st.cand.length : null };
  }

  function budgetsFor(B) { return Array.from(new Set([0, Math.floor(B / 2), B])).sort((a, b) => a - b); }

  function baseResult(ctx, s, P) {
    return { schema_version: RESULT_SCHEMA, metric_version: METRIC_VERSION, problem_digest: problemDigest(s),
      city_id: s.city_id, category: s.category, source_snapshot: s.source_snapshot, n_candidates: P.n,
      n_control_points: P.m, n_source_records: P.n_source_records, haversine_calls: P.haversineCalls,
      note: "Оптимум только среди введённых кандидатов и условий; расстояния по прямой; стоимость условная." };
  }

  function sensitivity(P, s, chunkRunner) {
    return budgetsFor(s.budget).map((b) => {
      const q = quickInfeasible(P, b);
      if (q.length) return { budget: b, status: "infeasible", reasons: q, objectives: null };
      const st = newSearch(P, b);
      chunkRunner(st);
      const r = finish(st);
      const short = {};
      for (const o of OBJECTIVES) short[o] = r.objectives && r.objectives[o] ? { ids: r.objectives[o].ids, cost: r.objectives[o].cost,
        weighted_sum_mm: r.objectives[o].metrics.weighted_sum_mm, max_mm: r.objectives[o].metrics.max_mm,
        covered_weight: r.objectives[o].metrics.covered_weight, unknown_count: r.objectives[o].metrics.unknown_count } : null;
      return { budget: b, status: r.status, feasible_count: r.feasible_count, objectives: short };
    });
  }

  function optimizePlans(ctx, scenario, options) {
    const opt = options || {};
    const P = prepareProblem(ctx, scenario);
    const out = baseResult(ctx, scenario, P);
    if (opt.request_id !== undefined) out.request_id = opt.request_id;
    const q = quickInfeasible(P, scenario.budget);
    if (q.length) return { ...out, status: "infeasible", reasons: q, evaluated: 0, total: 2 ** P.n, feasible_count: 0,
      objectives: null, pareto: [], sensitivity: opt.sensitivity === false ? null : sensitivity(P, scenario, (st) => step(st, st.total)) };
    const st = newSearch(P, scenario.budget);
    const chunk = opt.chunk || 4096, maxEval = opt.maxEvaluations === undefined ? INF : opt.maxEvaluations;
    let canceled = false;
    while (st.next < st.total) {
      if (opt.shouldCancel && opt.shouldCancel()) { canceled = true; break; }
      if (st.evaluated >= maxEval) break;
      step(st, Math.min(chunk, maxEval - st.evaluated));
      if (opt.onProgress) opt.onProgress({ evaluated: st.evaluated, total: st.total, feasible_count: st.feasible_count });
    }
    const r = finish(st, canceled ? "canceled" : null);
    if (r.status === "canceled") r.status = "incomplete";
    return { ...out, ...r, canceled,
      sensitivity: r.complete && opt.sensitivity !== false ? sensitivity(P, scenario, (s2) => step(s2, s2.total)) : null };
  }

  // Асинхронный вариант для UI: чанки с отдачей event loop; signal (AbortSignal-подобный) или shouldCancel.
  function optimizePlansAsync(ctx, scenario, options) {
    const opt = options || {};
    const tick = typeof setImmediate === "function" ? (f) => setImmediate(f) : (f) => setTimeout(f, 0);
    return new Promise((resolve) => {
      const P = prepareProblem(ctx, scenario);
      const out = baseResult(ctx, scenario, P);
      if (opt.request_id !== undefined) out.request_id = opt.request_id;
      const q = quickInfeasible(P, scenario.budget);
      if (q.length) { resolve({ ...out, status: "infeasible", reasons: q, evaluated: 0, total: 2 ** P.n, feasible_count: 0, objectives: null, pareto: [], sensitivity: null }); return; }
      const st = newSearch(P, scenario.budget);
      const chunk = opt.chunk || 2048;
      const cancelled = () => (opt.signal && opt.signal.aborted) || (opt.shouldCancel && opt.shouldCancel());
      const loop = () => {
        if (cancelled()) { const r = finish(st, "canceled"); r.status = "incomplete"; resolve({ ...out, ...r, canceled: true, sensitivity: null }); return; }
        step(st, chunk);
        if (opt.onProgress) opt.onProgress({ evaluated: st.evaluated, total: st.total, feasible_count: st.feasible_count });
        if (st.next < st.total) { tick(loop); return; }
        const r = finish(st);
        resolve({ ...out, ...r, canceled: false, sensitivity: opt.sensitivity === false ? null : sensitivity(P, scenario, (s2) => step(s2, s2.total)) });
      };
      tick(loop);
    });
  }

  // Ответ применим, только если digest и request_id совпадают с текущим состоянием.
  function isCurrent(result, currentProblemDigest, currentRequestId) {
    return !!result && result.problem_digest === currentProblemDigest
      && (currentRequestId === undefined || result.request_id === currentRequestId);
  }

  // Наружу — строгий JSON: Infinity не возникает (max_mm=null), проверка на всякий случай.
  function toStrictJSON(obj) {
    return JSON.stringify(obj, (k, v) => {
      if (typeof v === "number" && !Number.isFinite(v)) throw new PlanError("nonfinite", `нечисловое значение в ${k}`);
      return v;
    });
  }

  const API = { SCHEMA, RESULT_SCHEMA, METRIC_VERSION, R_EARTH_M, LIM, CATEGORIES, PlanError,
    haversineM, distMm, sha256Hex, canon, parsePlanJSON, contextFromCityData, validatePlanScenario, prepareProblem,
    evaluatePlan, optimizePlans, optimizePlansAsync, problemDigest, scenarioDigest, isCurrent, toStrictJSON, budgetsFor,
    _internal: { cmpKey, keyOf, cmpIds, paretoOf } };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.CITY_PLAN = API;
})(typeof window !== "undefined" ? window : this);
