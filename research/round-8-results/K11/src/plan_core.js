/* K11 round 8 — city-plan-v2 search core, written to be RESUMABLE in small steps (for a Web Worker or for
 * time-sliced chunks on the main thread). Follows research/round-8/CORE_SPEC.txt. Pure JS, no DOM, no network.
 * Browser: window.CITY_PLAN_CORE ; Node / worker_threads / importScripts: module.exports or self.CITY_PLAN_CORE.
 *
 * This is the reference engine the K11 orchestration adapter drives; a BUILD solver can replace it as long as it
 * exposes prepareProblem / createSearch / stepSearch / finalizeSearch (see plan_runner.js "engine" contract).
 * Distances are geometric straight-line metres inside the stored slice: no walking time, population or capacity.
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-plan-v2";
  const METRIC_VERSION = "haversine-mm-v1";
  const ENGINE = "k11-plan-core/1";
  const R_EARTH = 6371008.8;
  const CATEGORIES = ["school", "outpatient_clinic"];
  const LIMITS = { points: [1, 25], candidates: [0, 16], max_selected: [0, 5], cost: [1, 1000000],
    budget: [0, 1000000], weight: [1, 100], radius: [100, 5000], id_len: 64 };
  const TOP = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
    "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"];

  class PlanError extends Error {
    constructor(code, detail) { super(code + ": " + detail); this.name = "PlanError"; this.code = code; this.detail = detail; }
  }

  // ---------- numbers and strings ----------
  function haversine(lon1, lat1, lon2, lat2) {
    const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r, dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
    let a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    a = Math.min(1, Math.max(0, a));
    return 2 * R_EARTH * Math.asin(Math.sqrt(a));
  }
  const toMm = (d) => Math.round(d * 1000);  // d >= 0, rounded once (CORE_SPEC haversine-mm-v1)

  // Code-point order (same as Python str ordering), not UTF-16 unit order.
  function cmpStr(a, b) {
    if (a === b) return 0;
    const A = Array.from(a), B = Array.from(b);
    for (let i = 0; i < Math.min(A.length, B.length); i++) {
      const x = A[i].codePointAt(0), y = B[i].codePointAt(0);
      if (x !== y) return x < y ? -1 : 1;
    }
    return A.length < B.length ? -1 : A.length > B.length ? 1 : 0;
  }
  function cmpIdLists(a, b) {  // element-wise, shorter prefix first
    for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = cmpStr(a[i], b[i]); if (c) return c; }
    return a.length - b.length;
  }
  function cmpKeys(a, b) {  // numeric key elements, last element = sorted id list
    for (let i = 0; i < a.length - 1; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
    return cmpIdLists(a[a.length - 1], b[b.length - 1]);
  }

  // ---------- SHA-256 (sync, for digests in Worker and main thread alike) ----------
  const K256 = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
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
  function sha256hex(str) {
    const msg = utf8(str), len = msg.length, total = ((len + 9 + 63) >> 6) << 6;
    const buf = new Uint8Array(total); buf.set(msg); buf[len] = 0x80;
    const bits = len * 8, dv = new DataView(buf.buffer);
    dv.setUint32(total - 4, bits >>> 0); dv.setUint32(total - 8, Math.floor(bits / 0x100000000));
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const W = new Uint32Array(64);
    for (let off = 0; off < total; off += 64) {
      for (let i = 0; i < 16; i++) W[i] = dv.getUint32(off + i * 4);
      for (let i = 16; i < 64; i++) {
        const a = W[i - 15], b = W[i - 2];
        const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
        const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        const t1 = (h + S1 + ((e & f) ^ (~e & g)) + K256[i] + W[i]) >>> 0;
        const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        const t2 = (S0 + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    return Array.from(H, (x) => x.toString(16).padStart(8, "0")).join("");
  }

  // ---------- validation (structure, ranges, references; strict JSON text parsing is a separate concern) ----------
  const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);
  function checkId(v, where) {
    if (typeof v !== "string" || v.length === 0 || Array.from(v).length > LIMITS.id_len) throw new PlanError("bad_id", where);
    if (/[\u0000-\u001f\u007f]/.test(v)) throw new PlanError("bad_id", where + ": control character");
    return v;
  }
  function uniqueIds(list, where) {
    if (!Array.isArray(list)) throw new PlanError("bad_shape", where + " must be an array");
    const s = new Set();
    for (const id of list) { checkId(id, where); if (s.has(id)) throw new PlanError("duplicate_id", where + ": " + id); s.add(id); }
    return s;
  }
  function inBbox(bb, lon, lat) { return bb[0] <= lon && lon <= bb[2] && bb[1] <= lat && lat <= bb[3]; }
  function checkCoord(o, where, bbox) {
    if (!isNum(o.lon) || !isNum(o.lat) || o.lon < -180 || o.lon > 180 || o.lat < -90 || o.lat > 90)
      throw new PlanError("bad_coord", where);
    if (!inBbox(bbox, o.lon, o.lat)) throw new PlanError("outside_bbox", where);
  }

  /* context: {city_id, bbox:[minlon,minlat,maxlon,maxlat], source_snapshot, records:[{id, lon, lat, group}]} */
  function validatePlanScenario(input, context) {
    if (!input || typeof input !== "object" || Array.isArray(input)) throw new PlanError("bad_shape", "scenario");
    for (const k of Object.keys(input)) if (!TOP.includes(k) && k !== "derived_results") throw new PlanError("unknown_field", k);
    for (const k of TOP) if (!(k in input)) throw new PlanError("missing_field", k);
    if (input.schema_version !== SCHEMA) throw new PlanError("bad_version", String(input.schema_version));
    if (input.city_id !== context.city_id) throw new PlanError("bad_city", String(input.city_id));
    if (input.source_snapshot !== context.source_snapshot) throw new PlanError("bad_snapshot", "scenario is for another slice");
    if (!CATEGORIES.includes(input.category)) throw new PlanError("bad_category", String(input.category));
    const P = input.control_points, C = input.candidates;
    if (!Array.isArray(P) || P.length < LIMITS.points[0] || P.length > LIMITS.points[1]) throw new PlanError("bad_points", "1..25");
    if (!Array.isArray(C) || C.length > LIMITS.candidates[1]) throw new PlanError("bad_candidates", "0..16");
    const pids = new Set(), cids = new Set();
    const points = P.map((p, i) => {
      const w = `control_points[${i}]`;
      if (!p || typeof p !== "object") throw new PlanError("bad_shape", w);
      for (const k of Object.keys(p)) if (!["id", "lon", "lat", "weight"].includes(k)) throw new PlanError("unknown_field", w + "." + k);
      checkId(p.id, w); if (pids.has(p.id)) throw new PlanError("duplicate_id", w); pids.add(p.id);
      checkCoord(p, w, context.bbox);
      if (!isInt(p.weight, ...LIMITS.weight)) throw new PlanError("bad_weight", w);
      return { id: p.id, lon: p.lon, lat: p.lat, weight: p.weight };
    });
    const candidates = C.map((c, i) => {
      const w = `candidates[${i}]`;
      if (!c || typeof c !== "object") throw new PlanError("bad_shape", w);
      for (const k of Object.keys(c)) if (!["id", "lon", "lat", "category", "kind", "cost"].includes(k)) throw new PlanError("unknown_field", w + "." + k);
      checkId(c.id, w); if (cids.has(c.id)) throw new PlanError("duplicate_id", w); cids.add(c.id);
      checkCoord(c, w, context.bbox);
      if (c.category !== input.category) throw new PlanError("bad_category", w);
      if (c.kind !== "hypothetical") throw new PlanError("bad_kind", w);
      if (!isInt(c.cost, ...LIMITS.cost)) throw new PlanError("bad_cost", w);
      return { id: c.id, lon: c.lon, lat: c.lat, category: c.category, kind: "hypothetical", cost: c.cost };
    });
    if (!isInt(input.budget, ...LIMITS.budget)) throw new PlanError("bad_budget", String(input.budget));
    if (!isInt(input.max_selected, ...LIMITS.max_selected)) throw new PlanError("bad_max_selected", String(input.max_selected));
    if (!isInt(input.coverage_radius_m, ...LIMITS.radius)) throw new PlanError("bad_radius", String(input.coverage_radius_m));
    const req = uniqueIds(input.required_ids, "required_ids"), exc = uniqueIds(input.excluded_ids, "excluded_ids");
    const sel = uniqueIds(input.selected_ids, "selected_ids");
    for (const id of [...req, ...exc, ...sel]) if (!cids.has(id)) throw new PlanError("unknown_candidate", id);
    for (const id of req) if (exc.has(id)) throw new PlanError("required_excluded_overlap", id);
    return { schema_version: SCHEMA, city_id: input.city_id, source_snapshot: input.source_snapshot, category: input.category,
      control_points: points, candidates, budget: input.budget, max_selected: input.max_selected,
      coverage_radius_m: input.coverage_radius_m, required_ids: [...req], excluded_ids: [...exc], selected_ids: [...sel] };
  }

  // ---------- problem preparation: every haversine is computed here once, never inside the search ----------
  function canonicalProblem(sc) {
    const byId = (a, b) => cmpStr(a.id, b.id);
    return {
      schema_version: SCHEMA, metric_version: METRIC_VERSION, engine: ENGINE,
      city_id: sc.city_id, source_snapshot: sc.source_snapshot, category: sc.category,
      control_points: sc.control_points.slice().sort(byId).map((p) => [p.id, p.lon, p.lat, p.weight]),
      candidates: sc.candidates.slice().sort(byId).map((c) => [c.id, c.lon, c.lat, c.cost]),
      budget: sc.budget, max_selected: sc.max_selected, coverage_radius_m: sc.coverage_radius_m,
      required_ids: sc.required_ids.slice().sort(cmpStr), excluded_ids: sc.excluded_ids.slice().sort(cmpStr),
    };
  }
  const problemDigest = (sc) => "sha256:" + sha256hex(JSON.stringify(canonicalProblem(sc)));
  const scenarioDigest = (sc) => "sha256:" + sha256hex(JSON.stringify([canonicalProblem(sc), sc.selected_ids.slice().sort(cmpStr)]));

  function prepareProblem(context, sc) {
    const pts = sc.control_points.slice().sort((a, b) => cmpStr(a.id, b.id));
    const cands = sc.candidates.slice().sort((a, b) => cmpStr(a.id, b.id));
    const srcs = context.records.filter((r) => r.group === sc.category).slice().sort((a, b) => cmpStr(a.id, b.id));
    const m = pts.length, n = cands.length;
    const baseMm = new Float64Array(m).fill(-1), baseId = new Array(m).fill(null);
    for (let i = 0; i < m; i++) {
      for (const s of srcs) {  // sources sorted by id: strict < keeps the smallest id on ties
        const d = toMm(haversine(pts[i].lon, pts[i].lat, s.lon, s.lat));
        if (baseMm[i] < 0 || d < baseMm[i]) { baseMm[i] = d; baseId[i] = s.id; }
      }
    }
    const candMm = Array.from({ length: n }, (_, j) =>
      Float64Array.from(pts, (p) => toMm(haversine(p.lon, p.lat, cands[j].lon, cands[j].lat))));
    const idx = new Map(cands.map((c, j) => [c.id, j]));
    const maskOf = (ids) => ids.reduce((acc, id) => acc | (1 << idx.get(id)), 0);
    return {
      sc, pts, cands, m, n, baseMm, baseId, candMm, sources: srcs.length,
      weights: Int32Array.from(pts, (p) => p.weight), totalWeight: pts.reduce((s, p) => s + p.weight, 0),
      costs: Int32Array.from(cands, (c) => c.cost), radiusMm: sc.coverage_radius_m * 1000,
      requiredMask: maskOf(sc.required_ids), excludedMask: maskOf(sc.excluded_ids), maskOf,
      problem_digest: problemDigest(sc),
    };
  }

  // ---------- evaluation of one set (mask over sorted candidates) ----------
  function popcount(x) { let c = 0; while (x) { x &= x - 1; c++; } return c; }
  function maskCost(pb, mask) { let s = 0; for (let j = 0; j < pb.n; j++) if (mask & (1 << j)) s += pb.costs[j]; return s; }
  function feasibility(pb, mask, budget) {
    const reasons = [];
    if ((mask & pb.requiredMask) !== pb.requiredMask) reasons.push("missing_required");
    if (mask & pb.excludedMask) reasons.push("contains_excluded");
    if (popcount(mask) > pb.sc.max_selected) reasons.push("over_max_selected");
    if (maskCost(pb, mask) > budget) reasons.push("over_budget");
    return reasons;
  }
  function metricsOf(pb, mask) {  // hot path: integers only, no haversine
    let unknown = 0, ws = 0, max = -1, covered = 0;
    for (let i = 0; i < pb.m; i++) {
      let a = pb.baseMm[i];
      for (let j = 0; j < pb.n; j++) if (mask & (1 << j)) { const d = pb.candMm[j][i]; if (a < 0 || d < a) a = d; }
      if (a < 0) { unknown++; continue; }
      ws += pb.weights[i] * a;
      if (a > max) max = a;
      if (a <= pb.radiusMm) covered += pb.weights[i];
    }
    return { unknown, ws, max: unknown ? Infinity : max, covered, cost: maskCost(pb, mask) };
  }
  const idsOf = (pb, mask) => pb.cands.filter((_, j) => mask & (1 << j)).map((c) => c.id).sort(cmpStr);
  const KEYS = {
    mean: (x, ids) => [x.unknown, x.ws, x.max, x.cost, ids],
    minimax: (x, ids) => [x.unknown, x.max, x.ws, x.cost, ids],
    coverage: (x, ids) => [-x.covered, x.unknown, x.ws, x.max, x.cost, ids],
  };
  function publicMetrics(pb, x, mask) {
    const known = x.unknown === 0;
    return { selected_count: popcount(mask), cost: x.cost, unknown_count: x.unknown, weighted_sum_mm: x.ws,
      weighted_mean_mm: known ? x.ws / pb.totalWeight : null, max_mm: known ? x.max : null,
      covered_weight: x.covered, coverage_fraction: x.covered / pb.totalWeight };
  }

  /* Manual plan: per-point rows (nearest source / hypothetical, mm before/after/delta) + metrics + feasibility. */
  function evaluatePlan(context, scenario, selectedIds) {
    const sc = validatePlanScenario(scenario, context);
    const pb = prepareProblem(context, sc);
    if (!Array.isArray(selectedIds)) throw new PlanError("bad_shape", "selectedIds must be an array");
    for (const id of selectedIds) if (!pb.cands.some((c) => c.id === id)) throw new PlanError("unknown_candidate", String(id));
    const mask = pb.maskOf([...new Set(selectedIds)]);
    const rows = pb.pts.map((p, i) => {
      const before = pb.baseMm[i] < 0 ? null : pb.baseMm[i];
      let after = before, nearest = before === null ? null : { kind: "source", id: pb.baseId[i] };
      for (let j = 0; j < pb.n; j++) if (mask & (1 << j)) {
        const d = pb.candMm[j][i];
        // a source keeps ties (source key before hypothetical key), then the smaller hypothetical id (sorted order)
        if (after === null || d < after) { after = d; nearest = { kind: "hypothetical", id: pb.cands[j].id }; }
      }
      return { id: p.id, weight: p.weight, before_mm: before, after_mm: after,
        delta_mm: before !== null && after !== null ? before - after : null, nearest_after: nearest };
    });
    const reasons = feasibility(pb, mask, sc.budget);
    return { rows, metrics: publicMetrics(pb, metricsOf(pb, mask), mask), feasible: reasons.length === 0, reasons,
      selected_ids: idsOf(pb, mask), scenario_digest: scenarioDigest(sc), problem_digest: pb.problem_digest,
      metric_version: METRIC_VERSION };
  }

  // ---------- resumable exhaustive search ----------
  function createSearch(pb, opts) {
    const budget = opts && Number.isInteger(opts.budget) ? opts.budget : pb.sc.budget;
    const reqCount = popcount(pb.requiredMask), reqCost = maskCost(pb, pb.requiredMask);
    const pre = [];
    if (reqCount > pb.sc.max_selected) pre.push("required_exceeds_max_selected");
    if (reqCost > budget) pre.push("required_exceeds_budget");
    return { pb, budget, next: 0, total: 2 ** pb.n, evaluated: 0, feasible: 0, best: { mean: null, minimax: null, coverage: null },
      pareto: new Map(), pre, done: pre.length > 0, cancelled: false };
  }
  /* Process up to maxMasks subsets; returns true when the whole space has been searched. */
  function stepSearch(st, maxMasks) {
    const pb = st.pb, end = Math.min(st.total, st.next + Math.max(1, maxMasks | 0));
    for (let mask = st.next; mask < end; mask++) {
      st.evaluated++;
      if ((mask & pb.requiredMask) !== pb.requiredMask || (mask & pb.excludedMask)) continue;
      if (popcount(mask) > pb.sc.max_selected) continue;
      const x = metricsOf(pb, mask);
      if (x.cost > st.budget) continue;
      st.feasible++;
      const ids = idsOf(pb, mask);
      for (const k of ["mean", "minimax", "coverage"]) {
        const key = KEYS[k](x, ids);
        if (!st.best[k] || cmpKeys(key, st.best[k].key) < 0) st.best[k] = { key, mask, x };
      }
      if (x.unknown === 0) {
        const pk = x.cost + "|" + x.ws, cur = st.pareto.get(pk);
        if (!cur || cmpIdLists(ids, cur.ids) < 0) st.pareto.set(pk, { cost: x.cost, ws: x.ws, ids, mask, x });
      }
    }
    st.next = end;
    if (st.next >= st.total) st.done = true;
    return st.done;
  }
  function finalizeSearch(st) {
    const pb = st.pb;
    const base = { problem_digest: pb.problem_digest, metric_version: METRIC_VERSION, engine: ENGINE, budget: st.budget,
      evaluated: st.evaluated, total: st.total, feasible_count: st.feasible };
    if (st.cancelled) return Object.assign({ status: "cancelled", objectives: null, pareto: null }, base);
    if (!st.done) return Object.assign({ status: "incomplete", objectives: null, pareto: null }, base);
    if (st.feasible === 0) return Object.assign({ status: "infeasible", reasons: st.pre.length ? st.pre : ["no_feasible_set"],
      objectives: null, pareto: [] }, base);
    const objectives = {};
    for (const k of ["mean", "minimax", "coverage"]) {
      const b = st.best[k];
      objectives[k] = { selected_ids: idsOf(pb, b.mask), metrics: publicMetrics(pb, b.x, b.mask), same_as: [] };
    }
    for (const a of ["mean", "minimax", "coverage"]) for (const b of ["mean", "minimax", "coverage"])
      if (a !== b && st.best[a].mask === st.best[b].mask) objectives[a].same_as.push(b);
    const pts = [...st.pareto.values()].sort((a, b) => a.cost - b.cost || a.ws - b.ws || cmpIdLists(a.ids, b.ids));
    const pareto = [];
    let bestWs = Infinity;
    for (const p of pts) if (p.ws < bestWs) { bestWs = p.ws; pareto.push({ selected_ids: p.ids, cost: p.cost, weighted_sum_mm: p.ws }); }
    return Object.assign({ status: "optimal", objectives, pareto,
      distinct_objective_plans: new Set(["mean", "minimax", "coverage"].map((k) => st.best[k].mask)).size }, base);
  }
  /* Synchronous convenience: whole search in one call (blocks; use plan_runner.js in a UI). */
  function optimizePlansSync(context, scenario, opts) {
    const sc = validatePlanScenario(scenario, context);
    const st = createSearch(prepareProblem(context, sc), opts);
    while (!st.done) stepSearch(st, 1 << 16);
    return finalizeSearch(st);
  }
  /* Sensitivity budgets: [0, floor(B/2), B] without duplicates (CORE_SPEC). */
  const sensitivityBudgets = (B) => [...new Set([0, Math.floor(B / 2), B])];

  const api = { SCHEMA, METRIC_VERSION, ENGINE, R_EARTH, LIMITS, PlanError, haversine, toMm, cmpStr, sha256hex,
    validatePlanScenario, canonicalProblem, problemDigest, scenarioDigest, prepareProblem, evaluatePlan,
    createSearch, stepSearch, finalizeSearch, optimizePlansSync, sensitivityBudgets };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CITY_PLAN_CORE = api;
})(typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : globalThis);
