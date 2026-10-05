/* «План нескольких объектов» — city-plan-v2 (research/round-8/CORE_SPEC.txt). Pure module, no DOM.
 * Several hypothetical candidate sites of one category with conditional costs, a budget and constraints; control points
 * with user weights. Utility is ONLY straight-line geometry inside the saved slice: no walking time, population,
 * capacity or traffic. Costs are conditional units entered by the user, not tenge and not an estimate.
 * Distances are rounded once to whole millimetres (metric haversine-mm-v1) so that comparisons are deterministic.
 * Works in the browser (window.CITY_PLAN; needs facts.js and whatif.js loaded first) and in Node (module.exports).
 * Independent Python oracle: tools/plan_oracle.py (tests/plan.cjs compares both).
 */
(function (root) {
  "use strict";
  const X = typeof module !== "undefined" && module.exports ? require("./whatif.js") : root.CITY_WHATIF;
  const SCHEMA = "city-plan-v2";
  const METRIC = "haversine-mm-v1";
  const CATEGORIES = { school: "Школа", outpatient_clinic: "Поликлиника" };
  const LIMITS = { points: 25, candidates: 16, max_selected: 5, weight: [1, 100], cost: [1, 1000000], budget: [0, 1000000], radius: [100, 5000], id: 64 };
  const ID_RE = /^[A-Za-z0-9_.-]{1,64}$/;
  const TOP_KEYS = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget", "max_selected",
    "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"];

  class PlanError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const fail = (code, d) => { throw new PlanError(code, d); };
  const mmOf = (m) => Math.round(m * 1000);  // non-negative input: equals floor(x + 0.5)
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const deepFreeze = (o) => { if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.freeze(o); for (const v of Object.values(o)) deepFreeze(v); } return o; };

  // ---------- context: the current slice; source records are frozen copies (never modified) ----------
  function sourceSnapshot(data, city, F) {
    const c = data.cities[city];
    if (!c) fail("bad_city", String(city));
    const fsha = c.files && c.files.places_social && c.files.places_social.sha256;
    return "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, city, c.release, fsha || null, F.placesDigest(data, city), METRIC]));
  }
  function makeContext(data, city, F) {
    const c = data.cities[city];
    if (!c) fail("bad_city", String(city));
    const places = c.places.filter((p) => CATEGORIES[p.group]).map((p) => ({ id: p.id, group: p.group, lon: p.lon, lat: p.lat, name: p.name || null }));
    return deepFreeze({ city_id: city, bbox: c.bbox.slice(), release: c.release, source_snapshot: sourceSnapshot(data, city, F), places,
      versions: { schema: SCHEMA, metric: METRIC } });
  }

  // ---------- validation (typed errors; returns a clean, normalised copy) ----------
  const isInt = (v, [lo, hi]) => typeof v === "number" && Number.isInteger(v) && v >= lo && v <= hi;
  function checkKeys(o, what, keys) {
    if (!o || typeof o !== "object" || Array.isArray(o)) fail("bad_shape", `${what}: ожидается объект`);
    const ks = Object.keys(o).sort().join(","), want = keys.slice().sort().join(",");
    if (ks !== want) fail("bad_shape", `${what}: поля {${ks.slice(0, 120)}} ≠ {${want}}`);
  }
  function checkId(v, what) { if (typeof v !== "string" || !ID_RE.test(v)) fail("bad_id", `${what}: ${JSON.stringify(v).slice(0, 40)} (A–Z, 0–9, _ . -, до 64 символов)`); return v; }
  function checkCoord(p, what, bb) {
    if (typeof p.lon !== "number" || typeof p.lat !== "number" || !Number.isFinite(p.lon) || !Number.isFinite(p.lat) || Math.abs(p.lon) > 180 || Math.abs(p.lat) > 90)
      fail("bad_coord", `${what}: координаты не конечны или вне диапазона`);
    if (!X.inBbox(bb, p.lon, p.lat)) fail("outside_bbox", `${what}: вне квадрата среза`);
  }
  function idList(v, what, known) {
    if (!Array.isArray(v)) fail("bad_shape", `${what}: массив`);
    const seen = new Set();
    for (const id of v) {
      checkId(id, what);
      if (seen.has(id)) fail("duplicate_id", `${what}: ${id}`);
      if (!known.has(id)) fail("unknown_ref", `${what}: кандидата ${id} нет`);
      seen.add(id);
    }
    return v.slice().sort(cmpStr);
  }
  /* input: parsed object; ctx: makeContext(...). opts.requirePoints=false allows an empty editor state. */
  function validatePlanScenario(input, ctx, opts) {
    const requirePoints = !opts || opts.requirePoints !== false;
    if (!input || typeof input !== "object" || Array.isArray(input)) fail("bad_shape", "ожидается объект");
    for (const k of Object.keys(input)) if (!TOP_KEYS.includes(k) && k !== "derived_results") fail("unknown_field", `поле ${JSON.stringify(k).slice(0, 40)} не допускается`);
    for (const k of TOP_KEYS) if (!(k in input)) fail("missing_field", k);
    if (input.schema_version === X.SCHEMA) fail("wrong_version", "это сценарий city-whatif-v1 (один объект) — загрузите его в режиме «Один объект»; стоимости и бюджет не подставляются");
    if (input.schema_version !== SCHEMA) fail("bad_version", `версия ${String(input.schema_version).slice(0, 40)} ≠ ${SCHEMA}`);
    if (input.city_id !== ctx.city_id) fail(input.city_id === "shymkent" || input.city_id === "astana" ? "other_city" : "bad_city", String(input.city_id).slice(0, 40));
    if (input.source_snapshot !== ctx.source_snapshot) fail("foreign_snapshot", "сценарий сделан на другом срезе данных или другой метрике (source_snapshot не совпадает)");
    if (!CATEGORIES[input.category]) fail("bad_category", String(input.category).slice(0, 40));
    const cps = input.control_points, cands = input.candidates;
    if (!Array.isArray(cps)) fail("bad_shape", "control_points — массив");
    if (cps.length > LIMITS.points || (requirePoints && cps.length < 1)) fail("bad_points", `контрольных точек 1..${LIMITS.points}, получено ${cps.length}`);
    if (!Array.isArray(cands)) fail("bad_shape", "candidates — массив");
    if (cands.length > LIMITS.candidates) fail("too_many_candidates", `кандидатов не больше ${LIMITS.candidates}, получено ${cands.length}`);
    const pids = new Set(), cids = new Set();
    const control_points = cps.map((p, k) => {
      checkKeys(p, `control_points[${k}]`, ["id", "lon", "lat", "weight"]);
      checkId(p.id, `control_points[${k}].id`);
      if (pids.has(p.id)) fail("duplicate_id", `control_points: ${p.id}`);
      pids.add(p.id);
      checkCoord(p, p.id, ctx.bbox);
      if (!isInt(p.weight, LIMITS.weight)) fail("bad_weight", `${p.id}: вес — целое 1..100`);
      return { id: p.id, lon: p.lon, lat: p.lat, weight: p.weight };
    });
    const candidates = cands.map((c, k) => {
      checkKeys(c, `candidates[${k}]`, ["id", "lon", "lat", "category", "kind", "cost"]);
      checkId(c.id, `candidates[${k}].id`);
      if (cids.has(c.id)) fail("duplicate_id", `candidates: ${c.id}`);
      cids.add(c.id);
      if (c.kind !== "hypothetical") fail("bad_kind", `${c.id}: kind должен быть hypothetical`);
      if (c.category !== input.category) fail("bad_category", `${c.id}: категория кандидата ≠ category сценария`);
      checkCoord(c, c.id, ctx.bbox);
      if (!isInt(c.cost, LIMITS.cost)) fail("bad_cost", `${c.id}: стоимость — целое 1..1000000 условных единиц`);
      return { id: c.id, lon: c.lon, lat: c.lat, category: c.category, kind: "hypothetical", cost: c.cost };
    });
    if (!isInt(input.budget, LIMITS.budget)) fail("bad_budget", "бюджет — целое 0..1000000 условных единиц");
    if (!isInt(input.max_selected, [0, LIMITS.max_selected])) fail("bad_max_selected", "max_selected — целое 0..5");
    if (!isInt(input.coverage_radius_m, LIMITS.radius)) fail("bad_radius", "coverage_radius_m — целое 100..5000 м");
    const required_ids = idList(input.required_ids, "required_ids", cids);
    const excluded_ids = idList(input.excluded_ids, "excluded_ids", cids);
    const both = required_ids.filter((id) => excluded_ids.includes(id));
    if (both.length) fail("required_excluded_overlap", `кандидат одновременно обязателен и исключён: ${both.join(", ")}`);
    const selected_ids = idList(input.selected_ids, "selected_ids", cids);
    return { schema_version: SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, category: input.category, control_points, candidates,
      budget: input.budget, max_selected: input.max_selected, coverage_radius_m: input.coverage_radius_m, required_ids, excluded_ids, selected_ids };
  }

  // ---------- digests: canonical (order-independent) problem input; scenario digest adds the manual selection ----------
  function problemCanon(sc) {
    const byId = (a, b) => cmpStr(a.id, b.id);
    return [SCHEMA, METRIC, sc.city_id, sc.source_snapshot, sc.category,
      sc.control_points.slice().sort(byId).map((p) => [p.id, p.lon, p.lat, p.weight]),
      sc.candidates.slice().sort(byId).map((c) => [c.id, c.lon, c.lat, c.cost]),
      sc.budget, sc.max_selected, sc.coverage_radius_m, sc.required_ids.slice().sort(cmpStr), sc.excluded_ids.slice().sort(cmpStr)];
  }
  const problemDigest = (sc, F) => "sha256:" + F.sha256hex(JSON.stringify(problemCanon(sc)));
  const scenarioDigest = (sc, F) => "sha256:" + F.sha256hex(JSON.stringify([problemCanon(sc), sc.selected_ids.slice().sort(cmpStr)]));

  // ---------- precomputation: every haversine once, rounded once to mm ----------
  function precompute(ctx, sc) {
    const pts = sc.control_points.slice().sort((a, b) => cmpStr(a.id, b.id));
    const cands = sc.candidates.slice().sort((a, b) => cmpStr(a.id, b.id));
    const src = ctx.places.filter((p) => p.group === sc.category).slice().sort((a, b) => cmpStr(a.id, b.id));
    const base = pts.map((p) => {
      let best = null;
      for (const s of src) {
        const m = X.haversine(p.lon, p.lat, s.lon, s.lat), mm = mmOf(m);
        if (best === null || mm < best.mm || (mm === best.mm && s.id < best.id)) best = { mm, m, id: s.id };
      }
      return best;
    });
    const dist = cands.map((c) => pts.map((p) => { const m = X.haversine(p.lon, p.lat, c.lon, c.lat); return { mm: mmOf(m), m }; }));
    return { pts, cands, src, base, dist, candIndex: new Map(cands.map((c, i) => [c.id, i])) };
  }

  // Feasibility of one set of candidate IDs; reasons are codes with a Russian text.
  function feasibility(sc, ids) {
    const set = new Set(ids), reasons = [];
    const cost = sc.candidates.filter((c) => set.has(c.id)).reduce((s, c) => s + c.cost, 0);
    if (cost > sc.budget) reasons.push({ code: "over_budget", text: `стоимость ${cost} > бюджета ${sc.budget} усл. ед.` });
    if (set.size > sc.max_selected) reasons.push({ code: "too_many", text: `выбрано ${set.size} > максимума ${sc.max_selected}` });
    const miss = sc.required_ids.filter((id) => !set.has(id));
    if (miss.length) reasons.push({ code: "missing_required", text: `не выбраны обязательные: ${miss.join(", ")}` });
    const exc = sc.excluded_ids.filter((id) => set.has(id));
    if (exc.length) reasons.push({ code: "has_excluded", text: `выбраны исключённые: ${exc.join(", ")}` });
    return { feasible: reasons.length === 0, reasons, cost };
  }

  // Metrics of an after-distance vector (mm; null = unknown) with point weights.
  function metricsOf(afterMm, weights, radiusMm) {
    let unknown = 0, wsum = 0, max = 0, covered = 0, total = 0;
    for (let i = 0; i < afterMm.length; i++) {
      const a = afterMm[i], w = weights[i];
      total += w;
      if (a === null) { unknown++; continue; }
      wsum += w * a; if (a > max) max = a; if (a <= radiusMm) covered += w;
    }
    return { unknown_count: unknown, weighted_sum_mm: wsum, weighted_mean_mm: unknown === 0 && total > 0 ? wsum / total : null,
      max_mm: unknown === 0 && afterMm.length ? max : null, covered_weight: covered, total_weight: total, coverage_fraction: total > 0 ? covered / total : null };
  }

  /* evaluatePlan(ctx, scenario, selectedIds) -> rows (input order of control points) + metrics + feasibility.
   * nearest_* = {kind: "source"|"hypothetical", id}; ties: mm, then source before hypothetical, then ID. */
  function evaluatePlan(ctx, sc, selectedIds, pre) {
    const P = pre || precompute(ctx, sc);
    const ids = [...new Set(selectedIds)].sort(cmpStr);
    for (const id of ids) if (!P.candIndex.has(id)) fail("unknown_ref", `кандидата ${id} нет`);
    const sel = ids.map((id) => P.candIndex.get(id));
    const rowsById = new Map();
    P.pts.forEach((p, j) => {
      const b = P.base[j];
      let best = b ? { mm: b.mm, m: b.m, kind: "source", id: b.id } : null;
      for (const i of sel) {
        const d = P.dist[i][j], c = P.cands[i];
        if (best === null || d.mm < best.mm || (d.mm === best.mm && best.kind === "hypothetical" && c.id < best.id)) best = { mm: d.mm, m: d.m, kind: "hypothetical", id: c.id };
      }
      rowsById.set(p.id, { id: p.id, lon: p.lon, lat: p.lat, weight: p.weight,
        before_mm: b ? b.mm : null, before_m: b ? b.m : null, nearest_before: b ? { kind: "source", id: b.id } : null,
        after_mm: best ? best.mm : null, after_m: best ? best.m : null, nearest_after: best ? { kind: best.kind, id: best.id } : null,
        delta_mm: b && best ? b.mm - best.mm : null });
    });
    const rows = sc.control_points.map((p) => rowsById.get(p.id));
    const metrics = metricsOf(P.pts.map((p) => rowsById.get(p.id).after_mm), P.pts.map((p) => p.weight), sc.coverage_radius_m * 1000);
    const baseline = metricsOf(P.base.map((b) => (b ? b.mm : null)), P.pts.map((p) => p.weight), sc.coverage_radius_m * 1000);
    const f = feasibility(sc, ids);
    return { selected_ids: ids, rows, metrics: { ...metrics, cost: f.cost, count: ids.length }, baseline, feasibility: { feasible: f.feasible, reasons: f.reasons },
      source_candidates: P.src.length, metric_version: METRIC };
  }

  const api = { SCHEMA, METRIC, CATEGORIES, LIMITS, PlanError, mmOf, sourceSnapshot, makeContext, validatePlanScenario, problemDigest, scenarioDigest,
    precompute, feasibility, metricsOf, evaluatePlan };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN = api;
})(typeof window !== "undefined" ? window : globalThis);
