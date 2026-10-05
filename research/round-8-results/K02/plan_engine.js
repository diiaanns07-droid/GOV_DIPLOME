/* K02 r8: изолированный движок city-plan-v2 по research/round-8/CORE_SPEC.txt (не общий прототип).
 * validatePlanScenario(input, context) / evaluatePlan(context, scenario, selectedIds) / optimizePlans(context, scenario, options)
 * Расстояния: гаверсинус whatif.haversine сборки (R=6371008.8, [lon,lat], clamp), один раз округлены до мм
 * (metric_version haversine-mm-v1). Полный перебор ≤16 кандидатов, без эвристик. Headless: без DOM.
 * deps = { whatif (web/whatif.js), F (web/facts.js) } — передаются явно, ничего глобального не читается.
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-plan-v2", METRIC = "haversine-mm-v1";
  const CATS = ["school", "outpatient_clinic"], CITIES = ["shymkent", "astana"];
  const LIM = { points: 25, candidates: 16, maxSelected: 5, idLen: 64, cost: 1000000, budget: 1000000, wMin: 1, wMax: 100, rMin: 100, rMax: 5000 };
  const FIELDS = ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget", "max_selected",
    "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"];
  const OPTIONAL = ["derived_results"];

  class PlanScenarioError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const bad = (code, detail) => { throw new PlanScenarioError(code, detail); };
  const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
  const fin = (v) => typeof v === "number" && Number.isFinite(v);
  const byStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

  /** context: {city, category, bbox, source_snapshot, sources:[{id,lon,lat}], versions} из актуальных данных сборки. */
  function contextFromData(data, city, category, deps) {
    const c = data.cities[city];
    if (!c) bad("bad_city", city);
    const inB = (p) => p.lon >= c.bbox[0] && p.lon <= c.bbox[2] && p.lat >= c.bbox[1] && p.lat <= c.bbox[3];
    const sources = c.places.filter((p) => p.group === category && fin(p.lon) && fin(p.lat) && inB(p))
      .map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, name: p.name })).sort((a, b) => byStr(a.id, b.id));
    return { city, category, bbox: c.bbox.slice(), release: c.release, source_snapshot: deps.whatif.sourceSnapshot(data, city, deps.F),
      sources, versions: { schema: SCHEMA, metric: METRIC, formula: deps.whatif.FORMULA } };
  }

  function checkId(id, what) { if (typeof id !== "string" || !id.length || id.length > LIM.idLen) bad("bad_id", `${what}: id — строка 1..${LIM.idLen}`); }
  function checkCoord(o, ctx, what) {
    if (!fin(o.lon) || !fin(o.lat) || o.lon < -180 || o.lon > 180 || o.lat < -90 || o.lat > 90) bad("bad_coordinates", `${what} ${o.id}`);
    const b = ctx.bbox;
    if (o.lon < b[0] || o.lon > b[2] || o.lat < b[1] || o.lat > b[3]) bad("outside_bbox", `${what} ${o.id} вне сохранённого квадрата`);
  }
  function uniq(ids, what) { const s = new Set(); for (const id of ids) { if (s.has(id)) bad("duplicate_id", `${what}: ${id}`); s.add(id); } return s; }
  function exactKeys(o, keys, what) {
    if (!o || typeof o !== "object" || Array.isArray(o)) bad("bad_shape", `${what}: ожидается объект`);
    for (const k of Object.keys(o)) if (!keys.includes(k)) bad("unexpected_field", `${what}: поле ${k}`);
    for (const k of keys) if (!(k in o)) bad("missing_field", `${what}: нет ${k}`);
  }

  /** Строгая проверка. input — объект (из parseStrict для текста). derived_results игнорируется (пересчёт). */
  function validatePlanScenario(input, ctx) {
    if (typeof input === "string") input = ctxParse(input, ctx);
    if (!input || typeof input !== "object" || Array.isArray(input)) bad("bad_shape", "сценарий — объект");
    for (const k of Object.keys(input)) if (!FIELDS.includes(k) && !OPTIONAL.includes(k)) bad("unexpected_field", k);
    for (const k of FIELDS) if (!(k in input)) bad("missing_field", k);
    if (input.schema_version !== SCHEMA) bad("bad_version", String(input.schema_version));
    if (!CITIES.includes(input.city_id) || input.city_id !== ctx.city) bad("bad_city", `${input.city_id} ≠ ${ctx.city}`);
    if (!CATS.includes(input.category) || input.category !== ctx.category) bad("bad_category", `${input.category} ≠ ${ctx.category}`);
    if (input.source_snapshot !== ctx.source_snapshot) bad("stale_snapshot", "source_snapshot не совпадает с актуальным срезом");
    const pts = input.control_points, cands = input.candidates;
    if (!Array.isArray(pts) || pts.length < 1 || pts.length > LIM.points) bad("bad_points", `1..${LIM.points} точек`);
    if (!Array.isArray(cands) || cands.length > LIM.candidates) bad("too_many_candidates", `0..${LIM.candidates} кандидатов`);
    const cp = pts.map((p) => { exactKeys(p, ["id", "lon", "lat", "weight"], "точка"); checkId(p.id, "точка"); checkCoord(p, ctx, "точка");
      if (!isInt(p.weight, LIM.wMin, LIM.wMax)) bad("bad_weight", `${p.id}: вес — целое ${LIM.wMin}..${LIM.wMax}`); return { id: p.id, lon: p.lon, lat: p.lat, weight: p.weight }; });
    uniq(cp.map((p) => p.id), "контрольные точки");
    const cc = cands.map((c) => { exactKeys(c, ["id", "lon", "lat", "category", "kind", "cost"], "кандидат"); checkId(c.id, "кандидат"); checkCoord(c, ctx, "кандидат");
      if (c.kind !== "hypothetical") bad("bad_kind", `${c.id}: kind=hypothetical`);
      if (c.category !== input.category) bad("bad_category", `${c.id}: ${c.category}`);
      if (!isInt(c.cost, 1, LIM.cost)) bad("bad_cost", `${c.id}: cost — целое 1..${LIM.cost}`);
      return { id: c.id, lon: c.lon, lat: c.lat, category: c.category, kind: "hypothetical", cost: c.cost }; });
    const candIds = uniq(cc.map((c) => c.id), "кандидаты");
    if (!isInt(input.budget, 0, LIM.budget)) bad("bad_budget", `0..${LIM.budget}`);
    if (!isInt(input.max_selected, 0, LIM.maxSelected)) bad("bad_max_selected", `0..${LIM.maxSelected}`);
    if (!isInt(input.coverage_radius_m, LIM.rMin, LIM.rMax)) bad("bad_radius", `${LIM.rMin}..${LIM.rMax}`);
    const lists = {};
    for (const k of ["required_ids", "excluded_ids", "selected_ids"]) {
      const v = input[k];
      if (!Array.isArray(v)) bad("bad_shape", k);
      v.forEach((id) => { checkId(id, k); if (!candIds.has(id)) bad("unknown_candidate", `${k}: ${id}`); });
      uniq(v, k); lists[k] = v.slice().sort(byStr);
    }
    for (const id of lists.required_ids) if (lists.excluded_ids.includes(id)) bad("required_excluded_overlap", id);
    return { schema_version: SCHEMA, city_id: input.city_id, source_snapshot: input.source_snapshot, category: input.category,
      control_points: cp, candidates: cc, budget: input.budget, max_selected: input.max_selected, coverage_radius_m: input.coverage_radius_m,
      required_ids: lists.required_ids, excluded_ids: lists.excluded_ids, selected_ids: lists.selected_ids };
  }
  function ctxParse(text, ctx) { if (!ctx.parseStrict) bad("bad_json", "нет парсера"); return ctx.parseStrict(text); }

  // ---------- предвычисление (гаверсинус не вызывается внутри перебора) ----------
  const mm = (d) => Math.round(d * 1000);
  function precompute(ctx, sc, deps) {
    const h = (a, b) => deps.whatif.haversine(a.lon, a.lat, b.lon, b.lat);
    const base = sc.control_points.map((p) => {
      let best = null;
      for (const s of ctx.sources) { const d = mm(h(p, s)), key = "source:" + s.id; if (!best || d < best.mm || (d === best.mm && key < best.key)) best = { mm: d, key }; }
      return best;
    });
    const cand = {};
    for (const c of sc.candidates) cand[c.id] = sc.control_points.map((p) => mm(h(p, c)));
    return { base, cand };
  }

  function metricsFor(sc, pre, sel) {
    const r = sc.coverage_radius_m * 1000;
    let unknown = 0, wsum = 0, wtot = 0, maxv = -1, covered = 0;
    const rows = sc.control_points.map((p, i) => {
      let best = pre.base[i] ? { mm: pre.base[i].mm, key: pre.base[i].key } : null;
      for (const id of sel) { const d = pre.cand[id][i], key = "hypothetical:" + id; if (!best || d < best.mm || (d === best.mm && key < best.key)) best = { mm: d, key }; }
      wtot += p.weight;
      if (!best) unknown++; else { wsum += p.weight * best.mm; if (best.mm > maxv) maxv = best.mm; if (best.mm <= r) covered += p.weight; }
      const before = pre.base[i] ? pre.base[i].mm : null;
      return { point_id: p.id, weight: p.weight, before_mm: before, before_key: pre.base[i] ? pre.base[i].key : null,
        after_mm: best ? best.mm : null, after_key: best ? best.key : null, delta_mm: before !== null && best ? before - best.mm : null };
    });
    const cost = sel.reduce((s, id) => s + sc.candidates.find((c) => c.id === id).cost, 0);
    return { rows, metrics: { unknown_count: unknown, weighted_sum_mm: wsum, weighted_mean_mm: unknown === 0 ? wsum / wtot : null,
      max_mm: unknown === 0 ? maxv : null, covered_weight: covered, total_weight: wtot, coverage_fraction: covered / wtot, cost, count: sel.length } };
  }

  function feasibility(sc, sel, cost, budget) {
    const reasons = [], s = new Set(sel);
    if (cost > budget) reasons.push({ code: "over_budget", cost, budget });
    if (sel.length > sc.max_selected) reasons.push({ code: "too_many_selected", count: sel.length, max_selected: sc.max_selected });
    const miss = sc.required_ids.filter((id) => !s.has(id)); if (miss.length) reasons.push({ code: "missing_required", ids: miss });
    const exc = sc.excluded_ids.filter((id) => s.has(id)); if (exc.length) reasons.push({ code: "excluded_selected", ids: exc });
    return reasons;
  }

  function evaluatePlan(ctx, sc, selectedIds, deps, _pre) {
    const known = new Set(sc.candidates.map((c) => c.id));
    for (const id of selectedIds) if (!known.has(id)) bad("unknown_candidate", id);
    uniq(selectedIds, "selected_ids");
    const sel = selectedIds.slice().sort(byStr);
    const pre = _pre || precompute(ctx, sc, deps);
    const { rows, metrics } = metricsFor(sc, pre, sel);
    const reasons = feasibility(sc, sel, metrics.cost, sc.budget);
    return { selected_ids: sel, rows, metrics, feasible: reasons.length === 0, infeasible_reasons: reasons, metric_version: METRIC };
  }

  // ---------- лексикографические ключи (меньше — лучше); null max внутри алгоритма = +∞ ----------
  const INF = Number.POSITIVE_INFINITY;
  const KEYS = {
    mean: (m) => [m.unknown_count, m.weighted_sum_mm, m.max_mm ?? INF, m.cost],
    minimax: (m) => [m.unknown_count, m.max_mm ?? INF, m.weighted_sum_mm, m.cost],
    coverage: (m) => [-m.covered_weight, m.unknown_count, m.weighted_sum_mm, m.max_mm ?? INF, m.cost],
  };
  function cmpIds(a, b) { for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = byStr(a[i], b[i]); if (c) return c; } return a.length - b.length; }
  function cmpKey(ka, ia, kb, ib) { for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1; return cmpIds(ia, ib); }

  function canonicalProblem(ctx, sc) {
    const pts = sc.control_points.map((p) => [p.id, p.lon, p.lat, p.weight]).sort((a, b) => byStr(a[0], b[0]));
    const cs = sc.candidates.map((c) => [c.id, c.lon, c.lat, c.category, c.kind, c.cost]).sort((a, b) => byStr(a[0], b[0]));
    return [SCHEMA, METRIC, ctx.versions.formula, sc.city_id, sc.category, sc.source_snapshot, pts, cs, sc.budget, sc.max_selected,
      sc.coverage_radius_m, sc.required_ids.slice().sort(byStr), sc.excluded_ids.slice().sort(byStr)];
  }
  const problemDigest = (ctx, sc, deps) => deps.F.sha256hex(JSON.stringify(canonicalProblem(ctx, sc)));
  const scenarioDigest = (ctx, sc, deps) => deps.F.sha256hex(JSON.stringify([canonicalProblem(ctx, sc), sc.selected_ids.slice().sort(byStr)]));

  function search(ctx, sc, deps, budget, pre) {
    const free = sc.candidates.map((c) => c.id).filter((id) => !sc.required_ids.includes(id) && !sc.excluded_ids.includes(id)).sort(byStr);
    const best = { mean: null, minimax: null, coverage: null };
    const full = []; let evaluated = 0, feasible = 0;
    const n = free.length;
    for (let mask = 0; mask < 1 << n; mask++) {
      const sel = sc.required_ids.slice();
      for (let j = 0; j < n; j++) if (mask & (1 << j)) sel.push(free[j]);
      sel.sort(byStr); evaluated++;
      if (sel.length > sc.max_selected) continue;
      const { metrics } = metricsFor(sc, pre, sel);
      if (metrics.cost > budget) continue;
      feasible++;
      for (const k of Object.keys(best)) {
        const key = KEYS[k](metrics);
        if (!best[k] || cmpKey(key, sel, best[k].key, best[k].selected_ids) < 0) best[k] = { key, selected_ids: sel, metrics };
      }
      if (metrics.unknown_count === 0) full.push({ selected_ids: sel, cost: metrics.cost, weighted_sum_mm: metrics.weighted_sum_mm });
    }
    return { best, full, evaluated, feasible, free_count: n };
  }

  function pareto(full) {
    const groups = new Map();
    for (const p of full) { const k = p.cost + "|" + p.weighted_sum_mm; const g = groups.get(k); if (!g || cmpIds(p.selected_ids, g.selected_ids) < 0) groups.set(k, p); }
    const pts = [...groups.values()];
    return pts.filter((a) => !pts.some((b) => b !== a && b.cost <= a.cost && b.weighted_sum_mm <= a.weighted_sum_mm && (b.cost < a.cost || b.weighted_sum_mm < a.weighted_sum_mm)))
      .sort((a, b) => a.cost - b.cost || a.weighted_sum_mm - b.weighted_sum_mm);
  }

  function optimizePlans(ctx, sc, deps, options = {}) {
    if (sc.candidates.length > LIM.candidates) bad("too_many_candidates", "точный перебор ограничен 16 кандидатами");
    const pre = precompute(ctx, sc, deps);
    const run = (budget) => {
      const s = search(ctx, sc, deps, budget, pre);
      const objectives = {};
      for (const k of Object.keys(s.best)) objectives[k] = s.best[k] && { selected_ids: s.best[k].selected_ids, metrics: s.best[k].metrics };
      const infeasible = s.feasible === 0 ? feasibility(sc, sc.required_ids, sc.required_ids.reduce((t, id) => t + sc.candidates.find((c) => c.id === id).cost, 0), budget) : [];
      if (s.feasible === 0 && !infeasible.length) infeasible.push({ code: "no_feasible_subset" });
      return { budget, status: s.feasible ? "optimal" : "infeasible", objectives, pareto: s.feasible ? pareto(s.full) : [],
        evaluated: s.evaluated, feasible_count: s.feasible, infeasible_reasons: infeasible };
    };
    const main = run(sc.budget);
    const budgets = [...new Set([0, Math.floor(sc.budget / 2), sc.budget])];
    const sensitivity = options.sensitivity === false ? [] : budgets.map((b) => { const r = run(b); return { budget: b, status: r.status, feasible_count: r.feasible_count,
      objectives: Object.fromEntries(Object.entries(r.objectives).map(([k, v]) => [k, v && { selected_ids: v.selected_ids, metrics: v.metrics }])) }; });
    return { status: main.status, objectives: main.objectives, pareto: main.pareto, evaluated: main.evaluated, feasible_count: main.feasible_count,
      infeasible_reasons: main.infeasible_reasons, sensitivity, problem_digest: problemDigest(ctx, sc, deps), metric_version: METRIC, exact: true };
  }

  const api = { SCHEMA, METRIC, LIM, PlanScenarioError, contextFromData, validatePlanScenario, evaluatePlan, optimizePlans, problemDigest, scenarioDigest, precompute };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN_ENGINE = api;
})(typeof window !== "undefined" ? window : globalThis);
