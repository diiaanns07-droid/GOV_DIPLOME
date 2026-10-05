/* K07 round 8 — city-plan-v2 calculator ADAPTER for the planner UI (research/round-8/CORE_SPEC.txt).
 * Pure functions, no DOM. Browser: window.CITY_PLAN_CALC; Node: module.exports (headless tests).
 * K07's own implementation so that the UI can be built and tested before K05's engine exists. The UI talks only to
 * the API below (validatePlanScenario / evaluatePlan / optimizePlans / createSearch), so K05's module can replace it
 * through CITY_PLAN_UI.setCalculator(engine) without UI changes. Cross-checked by tests/oracle_plan.py (independent
 * Python, written from CORE_SPEC). Straight-line distance inside the slice only: no walking time, population, capacity.
 * Costs are conditional units set by the user (or explicit SYNTHETIC demo), weights are user priorities.
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-plan-v2", METRIC_VERSION = "haversine-mm-v1", CALC_VERSION = "k07-plan-calc-r8.1";
  const R_EARTH = 6371008.8;
  const CATEGORIES = { school: "Школа", outpatient_clinic: "Поликлиника" };
  const LIMITS = { points: [1, 25], candidates: [0, 16], max_selected: [0, 5], weight: [1, 100], cost: [1, 1000000],
    budget: [0, 1000000], radius: [100, 5000] };
  const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;  // ASCII only: JS and Python order these IDs identically
  const TOP = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
    "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"];
  const POINT_KEYS = ["id", "lon", "lat", "weight"], CAND_KEYS = ["id", "lon", "lat", "category", "kind", "cost"];

  class PlanError extends Error {
    constructor(code, path, detail) { super(`${code} at ${path}: ${detail}`); this.code = code; this.path = path; this.detail = detail; }
  }

  // ---------- geometry ----------
  function haversine(lon1, lat1, lon2, lat2) {
    const r = Math.PI / 180, dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
    let a = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dl / 2) ** 2;
    a = Math.min(1, Math.max(0, a));
    return 2 * R_EARTH * Math.asin(Math.sqrt(a));
  }
  const toMm = (d) => Math.round(d * 1000);  // once per distance (haversine-mm-v1); all values are >= 0
  const inBbox = (bb, lon, lat) => bb[0] <= lon && lon <= bb[2] && bb[1] <= lat && lat <= bb[3];
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

  // ---------- context: the slice the scenario belongs to ----------
  // F: facts.js API (sha256hex, placesDigest). The snapshot binds city, release, the places file hash, a digest of all
  // record coordinates, the schema and the metric version; a file name alone is never accepted as a version.
  function makeContext(data, city, F) {
    const c = data && data.cities && data.cities[city];
    if (!c) throw new PlanError("bad_city", "city_id", String(city));
    const fsha = c.files && c.files.places_social && c.files.places_social.sha256;
    const snap = "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, city, c.release, fsha || null, F.placesDigest(data, city), METRIC_VERSION]));
    return { city_id: city, bbox: c.bbox.slice(), source_snapshot: snap, release: c.release, places_sha256: fsha || null,
      places: c.places, hash: F.sha256hex, versions: { schema: SCHEMA, metric_version: METRIC_VERSION, calc_version: CALC_VERSION } };
  }

  // ---------- validation ----------
  const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const isInt = (v) => typeof v === "number" && Number.isInteger(v);
  function intIn(v, [lo, hi], path) {
    if (!isInt(v)) throw new PlanError("not_integer", path, String(v));
    if (v < lo || v > hi) throw new PlanError("out_of_range", path, `${v} not in ${lo}..${hi}`);
  }
  function exactKeys(o, keys, path) {
    if (!isObj(o)) throw new PlanError("bad_type", path, "object expected");
    for (const k of Object.keys(o)) if (!keys.includes(k)) throw new PlanError("unknown_field", `${path}.${k}`, "not allowed");
    for (const k of keys) if (!(k in o)) throw new PlanError("missing_field", `${path}.${k}`, "required");
  }
  function coord(o, bb, path) {
    for (const k of ["lon", "lat"]) if (typeof o[k] !== "number" || !Number.isFinite(o[k])) throw new PlanError("bad_coordinate", `${path}.${k}`, String(o[k]));
    if (o.lon < -180 || o.lon > 180 || o.lat < -90 || o.lat > 90) throw new PlanError("bad_coordinate", path, "out of WGS84 range");
    if (!inBbox(bb, o.lon, o.lat)) throw new PlanError("outside_bbox", path, `${o.lon}, ${o.lat} outside ${bb.join(", ")}`);
  }
  function idList(v, path, known) {
    if (!Array.isArray(v)) throw new PlanError("bad_type", path, "array expected");
    const seen = new Set();
    v.forEach((id, i) => {
      if (typeof id !== "string" || !ID_RE.test(id)) throw new PlanError("bad_id", `${path}[${i}]`, String(id));
      if (seen.has(id)) throw new PlanError("duplicate_id", `${path}[${i}]`, id);
      if (!known.has(id)) throw new PlanError("unknown_reference", `${path}[${i}]`, id);
      seen.add(id);
    });
    return v.slice();
  }
  // Returns {ok:true, scenario} (normalised copy; derived_results dropped, never trusted) or {ok:false, error}.
  // opts.allowEmptyPoints: the editor may hold 0 points (empty UI state); calculation/export need 1..25.
  function validatePlanScenario(input, context, opts = {}) {
    try { return { ok: true, scenario: validateOrThrow(input, context, opts) }; }
    catch (e) { if (e instanceof PlanError) return { ok: false, error: { code: e.code, path: e.path, detail: e.detail } }; throw e; }
  }
  function validateOrThrow(o, ctx, opts) {
    exactKeys(o, TOP.concat("derived_results" in (isObj(o) ? o : {}) ? ["derived_results"] : []), "$");
    if (o.schema_version !== SCHEMA) throw new PlanError("bad_schema", "$.schema_version", String(o.schema_version));
    if (o.city_id !== ctx.city_id) throw new PlanError("bad_city", "$.city_id", `${o.city_id} ≠ ${ctx.city_id}`);
    if (o.source_snapshot !== ctx.source_snapshot) throw new PlanError("bad_snapshot", "$.source_snapshot", "another slice or version");
    if (!CATEGORIES[o.category]) throw new PlanError("bad_category", "$.category", String(o.category));
    if (!Array.isArray(o.control_points)) throw new PlanError("bad_type", "$.control_points", "array expected");
    const [pmin, pmax] = LIMITS.points;
    if (o.control_points.length > pmax || (o.control_points.length < pmin && !opts.allowEmptyPoints))
      throw new PlanError("bad_count", "$.control_points", `${o.control_points.length} not in ${pmin}..${pmax}`);
    const pids = new Set();
    const points = o.control_points.map((p, i) => {
      const path = `$.control_points[${i}]`;
      exactKeys(p, POINT_KEYS, path);
      if (typeof p.id !== "string" || !ID_RE.test(p.id)) throw new PlanError("bad_id", `${path}.id`, String(p.id));
      if (pids.has(p.id)) throw new PlanError("duplicate_id", `${path}.id`, p.id);
      pids.add(p.id); coord(p, ctx.bbox, path); intIn(p.weight, LIMITS.weight, `${path}.weight`);
      return { id: p.id, lon: p.lon, lat: p.lat, weight: p.weight };
    });
    if (!Array.isArray(o.candidates)) throw new PlanError("bad_type", "$.candidates", "array expected");
    if (o.candidates.length > LIMITS.candidates[1]) throw new PlanError("bad_count", "$.candidates", `${o.candidates.length} > ${LIMITS.candidates[1]}`);
    const cids = new Set();
    const cands = o.candidates.map((c, i) => {
      const path = `$.candidates[${i}]`;
      exactKeys(c, CAND_KEYS, path);
      if (typeof c.id !== "string" || !ID_RE.test(c.id)) throw new PlanError("bad_id", `${path}.id`, String(c.id));
      if (cids.has(c.id)) throw new PlanError("duplicate_id", `${path}.id`, c.id);
      cids.add(c.id); coord(c, ctx.bbox, path);
      if (c.category !== o.category) throw new PlanError("bad_category", `${path}.category`, `${c.category} ≠ ${o.category}`);
      if (c.kind !== "hypothetical") throw new PlanError("bad_kind", `${path}.kind`, String(c.kind));
      intIn(c.cost, LIMITS.cost, `${path}.cost`);
      return { id: c.id, lon: c.lon, lat: c.lat, category: c.category, kind: "hypothetical", cost: c.cost };
    });
    intIn(o.budget, LIMITS.budget, "$.budget");
    intIn(o.max_selected, LIMITS.max_selected, "$.max_selected");
    intIn(o.coverage_radius_m, LIMITS.radius, "$.coverage_radius_m");
    const req = idList(o.required_ids, "$.required_ids", cids), exc = idList(o.excluded_ids, "$.excluded_ids", cids);
    const both = req.filter((x) => exc.includes(x));
    if (both.length) throw new PlanError("required_excluded_overlap", "$.required_ids", both.join(", "));
    const sel = idList(o.selected_ids, "$.selected_ids", cids);
    return { schema_version: SCHEMA, city_id: o.city_id, source_snapshot: o.source_snapshot, category: o.category,
      control_points: points, candidates: cands, budget: o.budget, max_selected: o.max_selected,
      coverage_radius_m: o.coverage_radius_m, required_ids: req, excluded_ids: exc, selected_ids: sel };
  }

  // ---------- digests (order-independent) ----------
  function canon(v) {
    if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
    if (isObj(v)) return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}";
    return JSON.stringify(v);
  }
  function problemCore(sc) {
    const byId = (a, b) => cmpStr(a.id, b.id);
    return { schema_version: SCHEMA, metric_version: METRIC_VERSION, city_id: sc.city_id, source_snapshot: sc.source_snapshot,
      category: sc.category, control_points: sc.control_points.slice().sort(byId), candidates: sc.candidates.slice().sort(byId),
      budget: sc.budget, max_selected: sc.max_selected, coverage_radius_m: sc.coverage_radius_m,
      required_ids: sc.required_ids.slice().sort(cmpStr), excluded_ids: sc.excluded_ids.slice().sort(cmpStr) };
  }
  // The optimisation problem (no selected_ids) and the manual scenario (with selected_ids).
  const problemDigest = (ctx, sc) => "sha256:" + ctx.hash(canon(problemCore(sc)));
  const scenarioDigest = (ctx, sc) => "sha256:" + ctx.hash(canon({ ...problemCore(sc), selected_ids: sc.selected_ids.slice().sort(cmpStr) }));

  // ---------- precomputed distance matrix ----------
  // Candidates are ordered by ID (bit i = i-th smallest ID), so input order never changes a plan or a tie.
  function prepare(ctx, sc) {
    const sources = ctx.places.filter((p) => p.group === sc.category).slice().sort((a, b) => cmpStr(a.id, b.id));
    const cands = sc.candidates.slice().sort((a, b) => cmpStr(a.id, b.id));
    const pts = sc.control_points;
    const before = pts.map((cp) => {  // nearest source: (mm, id) — ties to the smaller ID
      let best = null;
      for (const s of sources) { const d = toMm(haversine(cp.lon, cp.lat, s.lon, s.lat)); if (best === null || d < best.mm) best = { mm: d, id: s.id }; }
      return best;
    });
    const dist = cands.map((c) => pts.map((cp) => toMm(haversine(cp.lon, cp.lat, c.lon, c.lat))));
    const bit = (id) => 1 << cands.findIndex((c) => c.id === id);
    const mask = (ids) => ids.reduce((m, id) => m | bit(id), 0);
    return { sources, cands, pts, before, dist, weights: pts.map((p) => p.weight), totalWeight: pts.reduce((s, p) => s + p.weight, 0),
      costs: cands.map((c) => c.cost), radiusMm: sc.coverage_radius_m * 1000, reqMask: mask(sc.required_ids), excMask: mask(sc.excluded_ids), mask };
  }
  // Metrics of one subset (mask over pr.cands). Nearest-after ties: source before hypothetical, then the smaller ID.
  function metricsOf(pr, m) {
    let unknown = 0, wsum = 0, max = 0, covered = 0, cost = 0, count = 0;
    for (let c = 0; c < pr.cands.length; c++) if (m & (1 << c)) { cost += pr.costs[c]; count++; }
    for (let p = 0; p < pr.pts.length; p++) {
      let a = pr.before[p] ? pr.before[p].mm : null;
      for (let c = 0; c < pr.cands.length; c++) if (m & (1 << c)) { const d = pr.dist[c][p]; if (a === null || d < a) a = d; }
      if (a === null) { unknown++; continue; }
      wsum += pr.weights[p] * a; if (a > max) max = a;
      if (a <= pr.radiusMm) covered += pr.weights[p];
    }
    return { unknown_count: unknown, weighted_sum_mm: wsum, weighted_mean_mm: unknown ? null : wsum / pr.totalWeight,
      max_mm: unknown ? null : max, covered_weight: covered, total_weight: pr.totalWeight,
      coverage_fraction: pr.totalWeight ? covered / pr.totalWeight : 0, cost, selected_count: count };
  }
  const idsOf = (pr, m) => pr.cands.filter((_, c) => m & (1 << c)).map((c) => c.id);
  function feasibility(pr, sc, m, cost, count, budget) {
    const reasons = [];
    if (cost > budget) reasons.push({ code: "over_budget", detail: `${cost} > ${budget}` });
    if (count > sc.max_selected) reasons.push({ code: "too_many", detail: `${count} > ${sc.max_selected}` });
    const missing = idsOf(pr, pr.reqMask & ~m); if (missing.length) reasons.push({ code: "missing_required", detail: missing.join(", ") });
    const banned = idsOf(pr, pr.excMask & m); if (banned.length) reasons.push({ code: "has_excluded", detail: banned.join(", ") });
    return { feasible: !reasons.length, reasons };
  }

  // ---------- manual plan ----------
  function evaluatePlan(ctx, sc, selectedIds) {
    const pr = prepare(ctx, sc), ids = selectedIds === undefined ? sc.selected_ids : selectedIds;
    for (const id of ids) if (!pr.cands.some((c) => c.id === id)) throw new PlanError("unknown_reference", "selected_ids", id);
    const m = pr.mask(ids), met = metricsOf(pr, m);
    const rows = pr.pts.map((cp, p) => {
      const b = pr.before[p];
      let after = b ? { mm: b.mm, kind: "source", id: b.id } : null;
      for (let c = 0; c < pr.cands.length; c++) if (m & (1 << c)) {
        const d = pr.dist[c][p];
        if (after === null || d < after.mm) after = { mm: d, kind: "hypothetical", id: pr.cands[c].id };
      }
      return { control_point_id: cp.id, weight: cp.weight, before_mm: b ? b.mm : null, after_mm: after ? after.mm : null,
        delta_mm: b && after ? b.mm - after.mm : null, nearest_before: b ? { kind: "source", id: b.id } : null,
        nearest_after: after ? { kind: after.kind, id: after.id } : null, covered: after ? after.mm <= pr.radiusMm : false };
    });
    return { metric_version: METRIC_VERSION, selected_ids: idsOf(pr, m), rows, metrics: met, baseline_records: pr.sources.length,
      feasibility: feasibility(pr, sc, m, met.cost, met.selected_count, sc.budget), scenario_digest: scenarioDigest(ctx, sc) };
  }

  // ---------- exact search ----------
  const INF = Number.POSITIVE_INFINITY;
  function cmpIds(a, b) { for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = cmpStr(a[i], b[i]); if (c) return c; } return a.length - b.length; }
  function cmpKey(a, b) { for (let i = 0; i < a.length; i++) { const c = Array.isArray(a[i]) ? cmpIds(a[i], b[i]) : a[i] - b[i]; if (c) return c < 0 ? -1 : 1; } return 0; }
  const KEYS = {
    mean: (x, ids) => [x.unknown_count, x.weighted_sum_mm, x.max_mm === null ? INF : x.max_mm, x.cost, ids],
    minimax: (x, ids) => [x.unknown_count, x.max_mm === null ? INF : x.max_mm, x.weighted_sum_mm, x.cost, ids],
    coverage: (x, ids) => [-x.covered_weight, x.unknown_count, x.weighted_sum_mm, x.max_mm === null ? INF : x.max_mm, x.cost, ids],
  };
  function budgetsOf(B) { return [...new Set([0, Math.floor(B / 2), B])].sort((a, b) => a - b); }
  // Incremental exhaustive search: step(n) examines up to n more subsets; result() is never "optimal" before done.
  function createSearch(ctx, sc) {
    const pr = prepare(ctx, sc), n = pr.cands.length, total = 2 ** n, budgets = budgetsOf(sc.budget);
    const tiers = budgets.map((b) => ({ budget: b, feasible: 0, best: { mean: null, minimax: null, coverage: null } }));
    const main = tiers[tiers.length - 1];
    let next = 0, pareto = [], unknownFeasible = 0;
    const reqCount = idsOf(pr, pr.reqMask).length, reqCost = pr.costs.reduce((s, c, i) => s + (pr.reqMask & (1 << i) ? c : 0), 0);
    const pc = (m) => { let k = 0; while (m) { m &= m - 1; k++; } return k; };
    function consider(m) {
      if (m & pr.excMask || (m & pr.reqMask) !== pr.reqMask || pc(m) > sc.max_selected) return;
      let cost = 0; for (let c = 0; c < n; c++) if (m & (1 << c)) cost += pr.costs[c];
      if (cost > sc.budget) return;
      const x = metricsOf(pr, m), ids = idsOf(pr, m);
      for (const t of tiers) {
        if (cost > t.budget) continue;
        t.feasible++;
        for (const k of Object.keys(KEYS)) {
          const key = KEYS[k](x, ids);
          if (!t.best[k] || cmpKey(key, t.best[k].key) < 0) t.best[k] = { key, mask: m, metrics: x, ids };
        }
      }
      if (x.unknown_count) { unknownFeasible++; return; }
      // Pareto on (cost, weighted_sum_mm): drop dominated, equal pairs collapse to the smaller sorted IDs
      for (const q of pareto) {
        if (q.cost <= cost && q.wsum <= x.weighted_sum_mm && (q.cost < cost || q.wsum < x.weighted_sum_mm)) return;
        if (q.cost === cost && q.wsum === x.weighted_sum_mm && cmpIds(q.ids, ids) <= 0) return;
      }
      pareto = pareto.filter((q) => !(cost <= q.cost && x.weighted_sum_mm <= q.wsum));
      pareto.push({ cost, wsum: x.weighted_sum_mm, ids, metrics: x });
    }
    const plan = (b) => b && { selected_ids: b.ids, metrics: b.metrics };
    return {
      total, problem_digest: problemDigest(ctx, sc),
      get evaluated() { return next; },
      get done() { return next >= total; },
      step(limit) { const end = Math.min(total, next + limit); for (; next < end; next++) consider(next); return next >= total; },
      result(interrupted) {
        const complete = next >= total && !interrupted;
        const reasons = [];
        if (reqCost > sc.budget) reasons.push({ code: "required_over_budget", detail: `${reqCost} > ${sc.budget}` });
        if (reqCount > sc.max_selected) reasons.push({ code: "required_over_count", detail: `${reqCount} > ${sc.max_selected}` });
        const status = !complete ? (interrupted === "cancelled" ? "cancelled" : "partial") : main.feasible ? "optimal" : "infeasible";
        return { status, problem_digest: this.problem_digest, metric_version: METRIC_VERSION, calc_version: CALC_VERSION,
          evaluated: next, total_subsets: total, feasible_count: main.feasible, infeasible_reasons: main.feasible ? [] : reasons,
          objectives: complete ? { mean: plan(main.best.mean), minimax: plan(main.best.minimax), coverage: plan(main.best.coverage) } : null,
          pareto: complete ? pareto.slice().sort((a, b) => a.cost - b.cost || a.wsum - b.wsum).map((q) => ({ selected_ids: q.ids, cost: q.cost,
            weighted_sum_mm: q.wsum, weighted_mean_mm: q.metrics.weighted_mean_mm, max_mm: q.metrics.max_mm })) : null,
          pareto_excluded_unknown: unknownFeasible,
          sensitivity: complete ? tiers.map((t) => ({ budget: t.budget, feasible_count: t.feasible,
            objectives: { mean: plan(t.best.mean), minimax: plan(t.best.minimax), coverage: plan(t.best.coverage) } })) : null };
      },
    };
  }
  function optimizePlans(ctx, sc) { const s = createSearch(ctx, sc); s.step(s.total); return s.result(); }

  const api = { SCHEMA, METRIC_VERSION, CALC_VERSION, R_EARTH, CATEGORIES, LIMITS, ID_RE, PlanError, haversine, toMm, inBbox,
    makeContext, validatePlanScenario, evaluatePlan, optimizePlans, createSearch, problemDigest, scenarioDigest, budgetsOf, canon };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN_CALC = api;
})(typeof window !== "undefined" ? window : globalThis);
