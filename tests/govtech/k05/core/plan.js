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
  const ID_CHARS = /^[\p{L}\p{N}_.-]+$/u;  // letters of any script, digits, _ . -; NFC; 1..64 code points
  const ID_RE = { test: (v) => typeof v === "string" && v.normalize("NFC") === v && [...v].length >= 1 && [...v].length <= 64 && ID_CHARS.test(v) };
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
  function checkId(v, what) { if (typeof v !== "string" || !ID_RE.test(v)) fail("bad_id", `${what}: ${JSON.stringify(v).slice(0, 40)} (буквы, цифры, _ . -, NFC, до 64 символов)`); return v; }
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

  /* precomputeFromMatrix(sc, lookup) -> the same structure as precompute(), but distances come from a precomputed
   * matrix (school-access-case-v1, geodesic or pedestrian-v1) instead of haversine. sc = {control_points:[{id,weight}],
   * candidates:[{id}], sources:[{id}]}; lookup(originId, targetId) -> integer mm >= 0, or null when the matrix status is
   * not "ok" (unknown is never replaced by a straight line or by 0). Ties: mm, then ID — as in precompute(). */
  function precomputeFromMatrix(sc, lookup) {
    const pts = sc.control_points.slice().sort((a, b) => cmpStr(a.id, b.id));
    const cands = sc.candidates.slice().sort((a, b) => cmpStr(a.id, b.id));
    const src = sc.sources.slice().sort((a, b) => cmpStr(a.id, b.id));
    const base = pts.map((p) => {
      let best = null;
      for (const s of src) {
        const mm = lookup(p.id, s.id);
        if (mm === null) continue;
        if (best === null || mm < best.mm || (mm === best.mm && s.id < best.id)) best = { mm, m: mm / 1000, id: s.id };
      }
      return best;
    });
    const dist = cands.map((c) => pts.map((p) => { const mm = lookup(p.id, c.id); return { mm, m: mm === null ? null : mm / 1000 }; }));
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
  function evaluateInternal(ctx, sc, selectedIds, pre) {  // sc already validated against ctx
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
        if (d.mm === null) continue;  // unknown path in a precomputed matrix: never treated as 0 (null < n is true in JS)
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


  // ---------- exact search: bounded exhaustive enumeration (≤ 2^16 subsets), chunked, cancellable ----------
  const cmpIds = (a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = cmpStr(a[i], b[i]); if (c) return c; } return a.length - b.length; };
  // keys (smaller is better); unknown max = Infinity inside the algorithm, null outside
  const KEYS = {
    mean: (e) => [e.unknown, e.wsum, e.max, e.cost],
    minimax: (e) => [e.unknown, e.max, e.wsum, e.cost],
    coverage: (e) => [-e.covered, e.unknown, e.wsum, e.max, e.cost],
  };
  function better(ka, ida, kb, idb) {  // true if (ka, ida) < (kb, idb)
    for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] < kb[i];
    return cmpIds(ida, idb) < 0;
  }
  function popcount(x) { let c = 0; while (x) { x &= x - 1; c++; } return c; }
  /* createSearch(ctx, validatedScenario, {request_id}) -> { total, examined, step(n) -> done, cancel(), result() }.
   * Constraints are checked before any enumeration; the result is "optimal" only after every subset was examined. */
  function createSearchInternal(ctx, sc, opts) {  // sc already validated against ctx
    const F = (opts && opts.F) || null;
    const request_id = opts && opts.request_id !== undefined ? opts.request_id : null;
    const P = precompute(ctx, sc), nP = P.pts.length, nC = P.cands.length;
    const weights = P.pts.map((p) => p.weight), radiusMm = sc.coverage_radius_m * 1000;
    const req = sc.required_ids.map((id) => P.candIndex.get(id)).sort((a, b) => a - b);
    const exc = new Set(sc.excluded_ids.map((id) => P.candIndex.get(id)));
    const free = []; for (let i = 0; i < nC; i++) if (!req.includes(i) && !exc.has(i)) free.push(i);
    const reqCost = req.reduce((s, i) => s + P.cands[i].cost, 0);
    const reasons = [];
    if (req.length > sc.max_selected) reasons.push({ code: "required_exceeds_max_selected", text: `обязательных ${req.length} > максимума ${sc.max_selected}` });
    if (reqCost > sc.budget) reasons.push({ code: "required_cost_exceeds_budget", text: `стоимость обязательных ${reqCost} > бюджета ${sc.budget} усл. ед.` });
    const base = { problem_digest: F ? problemDigest(sc, F) : null, metric_version: METRIC, request_id, budget: sc.budget };
    const total = reasons.length ? 0 : 2 ** free.length;
    // start vector: baseline + required candidates (Infinity = unknown)
    const start = new Float64Array(nP);
    for (let j = 0; j < nP; j++) { let a = P.base[j] ? P.base[j].mm : Infinity; for (const i of req) a = Math.min(a, P.dist[i][j].mm); start[j] = a; }
    const dist = free.map((i) => Float64Array.from(P.dist[i].map((d) => d.mm)));
    const fcost = free.map((i) => P.cands[i].cost), slots = sc.max_selected - req.length;
    const best = { mean: null, minimax: null, coverage: null };
    const front = [];  // complete plans: [cost, wsum, mask]
    let examined = 0, feasible = 0, cancelled = false, mask = 0;
    const after = new Float64Array(nP);
    const idsOf = (m) => { const ids = req.map((i) => P.cands[i].id); for (let k = 0; k < free.length; k++) if (m & (1 << k)) ids.push(P.cands[free[k]].id); return ids.sort(cmpStr); };
    function evalMask(m) {
      let cost = reqCost;
      for (let k = 0; k < free.length; k++) if (m & (1 << k)) cost += fcost[k];
      if (cost > sc.budget) return null;
      after.set(start);
      for (let k = 0; k < free.length; k++) if (m & (1 << k)) { const d = dist[k]; for (let j = 0; j < nP; j++) if (d[j] < after[j]) after[j] = d[j]; }
      let unknown = 0, wsum = 0, max = 0, covered = 0;
      for (let j = 0; j < nP; j++) { const a = after[j]; if (a === Infinity) { unknown++; continue; } wsum += weights[j] * a; if (a > max) max = a; if (a <= radiusMm) covered += weights[j]; }
      return { mask: m, cost, unknown, wsum, max: unknown ? Infinity : max, covered };
    }
    function step(n) {
      if (cancelled || reasons.length) return true;
      const end = Math.min(total, mask + n);
      for (; mask < end; mask++) {
        examined++;
        if (popcount(mask) > slots) continue;
        const e = evalMask(mask);
        if (!e) continue;
        feasible++;
        for (const name of ["mean", "minimax", "coverage"]) {
          const k = KEYS[name](e), b = best[name];
          if (b === null) { best[name] = { e, k, ids: null }; continue; }
          let win = false, decided = false;
          for (let i = 0; i < k.length; i++) if (k[i] !== b.k[i]) { win = k[i] < b.k[i]; decided = true; break; }
          if (!decided) { if (!b.ids) b.ids = idsOf(b.e.mask); win = cmpIds(idsOf(mask), b.ids) < 0; }
          if (win) best[name] = { e, k, ids: null };
        }
        if (e.unknown === 0) front.push([e.cost, e.wsum, mask]);
      }
      return mask >= total;
    }
    function result() {
      if (reasons.length) return { ...base, status: "infeasible", reasons, objectives: null, pareto: [], evaluated: 0, total_subsets: 0, feasible_count: 0 };
      if (cancelled || mask < total) return { ...base, status: cancelled ? "cancelled" : "incomplete", reasons: [], objectives: null, pareto: [], evaluated: examined, total_subsets: total, feasible_count: feasible };
      const objectives = {};
      for (const name of Object.keys(best)) {
        const e = best[name].e;
        objectives[name] = { ids: idsOf(e.mask), cost: e.cost, unknown_count: e.unknown, weighted_sum_mm: e.wsum, max_mm: e.unknown ? null : e.max, covered_weight: e.covered };
      }
      // Pareto (complete plans only): sort by cost, wsum, ids; keep strictly decreasing wsum -> non-dominated, equal pairs collapsed
      const withIds = front.map(([c, w, m]) => [c, w, m, null]);
      withIds.sort((a, b) => a[0] - b[0] || a[1] - b[1] || cmpIds(a[3] || (a[3] = idsOf(a[2])), b[3] || (b[3] = idsOf(b[2]))));
      const pareto = []; let bestW = Infinity;
      for (const [c, w, m] of withIds) if (w < bestW) { pareto.push({ ids: idsOf(m), cost: c, weighted_sum_mm: w }); bestW = w; }
      return { ...base, status: "optimal", reasons: [], objectives, pareto, pareto_excluded_unknown: feasible - front.length,
        evaluated: examined, total_subsets: total, feasible_count: feasible };
    }
    return { get total() { return total; }, get examined() { return examined; }, step, cancel: () => { cancelled = true; }, result, request_id };
  }
  // Public entry points validate every input themselves (round 9, K12 r8 F1): an unchecked object with 20+ candidates
  // used to run 2^20+ subsets and report "optimal". Limits are checked before precomputation; the validated copy is used,
  // so mutating the caller's object afterwards cannot bypass them.
  function evaluatePlan(ctx, sc, selectedIds) { return evaluateInternal(ctx, validatePlanScenario(sc, ctx), selectedIds); }
  function createSearch(ctx, sc, opts) { return createSearchInternal(ctx, validatePlanScenario(sc, ctx), opts); }
  function optimizePlans(ctx, sc, opts) { const s = createSearch(ctx, sc, opts); while (!s.step(1 << 20)); return s.result(); }
  // Budgets [0, floor(B/2), B] without duplicates; everything else unchanged.
  function sensitivity(ctx, sc, opts) {
    const bs = [...new Set([0, Math.floor(sc.budget / 2), sc.budget])].sort((a, b) => a - b);
    return bs.map((b) => { const r = optimizePlans(ctx, { ...sc, budget: b }, opts); return { budget: b, status: r.status, reasons: r.reasons, objectives: r.objectives, feasible_count: r.feasible_count }; });
  }


  // ---------- files: strict export / import (city-plan-v2); derived_results are checked against a recomputation ----------
  function derivedOf(ctx, sc, F) {
    const ev = evaluateInternal(ctx, sc, sc.selected_ids);
    return { note: "производные значения; при импорте пересчитываются и сверяются, из файла не принимаются", metric_version: METRIC,
      problem_digest: problemDigest(sc, F), scenario_digest: scenarioDigest(sc, F),
      manual: { selected_ids: ev.selected_ids, feasible: ev.feasibility.feasible,
        metrics: { unknown_count: ev.metrics.unknown_count, weighted_sum_mm: ev.metrics.weighted_sum_mm, max_mm: ev.metrics.max_mm, covered_weight: ev.metrics.covered_weight, cost: ev.metrics.cost },
        rows: ev.rows.map((r) => ({ id: r.id, before_mm: r.before_mm, after_mm: r.after_mm, delta_mm: r.delta_mm, nearest_before: r.nearest_before, nearest_after: r.nearest_after })) } };
  }
  function exportPlanScenario(ctx, sc, F) {
    const clean = validatePlanScenario(sc, ctx);
    return JSON.stringify({ ...clean, derived_results: derivedOf(ctx, clean, F) }, null, 1) + "\n";
  }
  // Canonical JSON for comparison (keys sorted; the strict parser returns null-prototype objects)
  const canon = (v) => (Array.isArray(v) ? "[" + v.map(canon).join(",") + "]" : v && typeof v === "object"
    ? "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}" : JSON.stringify(v));
  /* importPlanScenario(text, ctxFor(city) -> context, F) -> { scenario, evaluation, ctx }. Nothing is applied here;
   * the caller applies the returned scenario only on success (atomic). derived_results, if present, must equal a recomputation. */
  function importPlanScenario(text, ctxFor, F) {
    let obj;
    try { obj = X.parseStrict(text); } catch (e) { throw new PlanError(e.code === "too_large" || e.code === "bad_encoding" ? e.code : "bad_json", e.detail || e.message); }
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) fail("bad_shape", "ожидается объект");
    if (obj.schema_version === X.SCHEMA) fail("wrong_version", "это сценарий city-whatif-v1 (один объект) — загрузите его в режиме «Один объект (v1)»; перенос в v2 без ваших стоимостей и бюджета не делается");
    if (obj.schema_version !== SCHEMA) fail("bad_version", `версия ${String(obj.schema_version).slice(0, 40)} не поддерживается`);
    if (obj.city_id !== "shymkent" && obj.city_id !== "astana") fail("bad_city", String(obj.city_id).slice(0, 40));
    const ctx = ctxFor(obj.city_id);
    const sc = validatePlanScenario(obj, ctx);
    if ("derived_results" in obj) {
      const want = canon(derivedOf(ctx, sc, F)), got = canon(obj.derived_results);
      if (want !== got) fail("forged_derived", "derived_results в файле не совпадают с пересчётом — файл изменён вручную или сделан другой версией; не принят");
    }
    return { scenario: sc, evaluation: evaluateInternal(ctx, sc, sc.selected_ids), ctx };
  }

  // ---------- template explanation over computed facts (not an LLM); digest covers problem, scenario and values ----------
  const mText = (mm) => (mm === null || mm === undefined ? "нет данных" : mm >= 1e6 ? (mm / 1e6).toFixed(2).replace(".", ",") + " км" : Math.round(mm / 1000) + " м");
  const idsText = (ids) => (ids.length ? ids.join(", ") : "без новых объектов");
  const OBJ_LABEL = { mean: "Среднее", minimax: "Худшая точка", coverage: "Охват" };
  function explanationDigest(sc, manual, result, sens, F) {
    const facts = [problemDigest(sc, F), scenarioDigest(sc, F), manual ? [manual.selected_ids, manual.metrics] : null,
      result ? [result.status, result.objectives, result.pareto, result.feasible_count] : null,
      sens ? sens.map((x) => [x.budget, x.status, x.objectives && Object.values(x.objectives).map((o) => [o.ids, o.cost])]) : null];
    return F.sha256hex(JSON.stringify(facts)).slice(0, 16);
  }
  function explainPlans(sc, manual, result, sens, digestAtRequest, F) {
    const cur = explanationDigest(sc, manual, result, sens, F);
    if (digestAtRequest !== cur) fail("stale_explanation", "сценарий или результаты изменились после запроса — объяснение отклонено");
    const tw = sc.control_points.reduce((t, p) => t + p.weight, 0);
    const mean = (o) => (o.unknown_count ? null : o.weighted_sum_mm / tw);
    const L = [`Шаблонное объяснение по вычисленным фактам (не LLM). Категория: ${CATEGORIES[sc.category]}; ${sc.control_points.length} контрольных точек (сумма весов ${tw}), ${sc.candidates.length} кандидатных мест, бюджет ${sc.budget} усл. ед., не больше ${sc.max_selected} объектов, радиус охвата ${sc.coverage_radius_m} м по прямой. Отпечаток ${cur}.`];
    if (manual) {
      const m = manual.metrics;
      L.push(`Ручной план (${idsText(manual.selected_ids)}): ${manual.feasibility.feasible ? "допустим" : "недопустим — " + manual.feasibility.reasons.map((r) => r.text).join("; ")}; стоимость ${m.cost} усл. ед.; взвешенное среднее ${mText(m.weighted_mean_mm)}, худшая точка ${mText(m.max_mm)}, охват ${m.covered_weight} из ${m.total_weight} по весу.`);
      if (m.unknown_count) L.push(`У ${m.unknown_count} точек нет ни одной записи категории в срезе и ни одного выбранного кандидата — расстояние неизвестно, а не равно нулю.`);
    }
    if (result && result.status === "infeasible") L.push("Допустимых планов нет: " + result.reasons.map((r) => r.text).join("; ") + ". Ограничения не снимались автоматически.");
    if (result && result.status === "optimal") {
      const O = result.objectives;
      L.push(`Точный перебор: просмотрено ${result.evaluated} наборов, допустимых ${result.feasible_count}. Оптимум — только среди введённых мест и условий.`);
      for (const k of ["mean", "minimax", "coverage"]) L.push(`«${OBJ_LABEL[k]}»: ${idsText(O[k].ids)} — стоимость ${O[k].cost}, среднее ${mText(mean(O[k]))}, худшая точка ${mText(O[k].max_mm)}, охват ${O[k].covered_weight} из ${tw}.`);
      const same = (a, b) => O[a].ids.join() === O[b].ids.join();
      if (same("mean", "minimax") && same("mean", "coverage")) L.push("Все три цели выбрали один и тот же план: здесь нет трёх разных решений, критерии не конфликтуют.");
      else {
        if (!same("mean", "minimax")) {
          const a = O.mean, b = O.minimax;
          L.push(`Почему планы разные: «Худшая точка» уменьшает самое большое расстояние (${mText(a.max_mm)} → ${mText(b.max_mm)}), но жертвует средним (${mText(mean(a))} → ${mText(mean(b))}).`);
        } else L.push("«Среднее» и «Худшая точка» совпали.");
        if (!same("mean", "coverage")) {
          const a = O.mean, c = O.coverage;
          L.push(`«Охват» максимизирует вес точек в радиусе ${sc.coverage_radius_m} м (${a.covered_weight} → ${c.covered_weight}); среднее при этом ${mText(mean(a))} → ${mText(mean(c))}.`);
        } else L.push("«Охват» совпал со «Средним».");
      }
      if (result.pareto.length) L.push(`Граница стоимость → сумма расстояний: ${result.pareto.length} недоминируемых планов, от ${result.pareto[0].cost} до ${result.pareto[result.pareto.length - 1].cost} усл. ед.`);
      if (result.pareto_excluded_unknown) L.push(`${result.pareto_excluded_unknown} допустимых планов оставляют точки без расстояния и в границу не входят.`);
    }
    if (sens && sens.length) L.push("Изменение бюджета: " + sens.map((x) => `${x.budget} усл. ед. — ${x.status === "optimal" ? "«Среднее»: " + idsText(x.objectives.mean.ids) + ", среднее " + mText(mean(x.objectives.mean)) : x.status === "infeasible" ? "нет допустимых планов" : x.status}`).join("; ") + ". Это перебор параметров, а не прогноз экономии реальных расходов.");
    L.push("Нельзя сделать вывод о вместимости, нагрузке, населении, пешем пути или пользе для здоровья/образования: считаются только расстояния по прямой до выбранных точек в квадрате среза. Стоимости — условные единицы, не тенге и не смета. Ближайшая запись в срезе — не обязательно ближайшее учреждение в городе.");
    return { text: L.join("\n"), digest: cur };
  }

  // ---------- self-contained HTML report: data inlined as escaped text, no scripts, no external resources ----------
  const esc = (v) => String(v === null || v === undefined ? "нет данных" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  function reportHtml(m) {
    const tr = (cells, th) => "<tr>" + cells.map((c) => (th ? "<th>" : "<td>") + esc(c) + (th ? "</th>" : "</td>")).join("") + "</tr>";
    const table = (head, rows) => "<table>" + tr(head, true) + rows.map((r) => tr(r)).join("") + "</table>";
    const sc = m.scenario, tw = sc.control_points.reduce((t, p) => t + p.weight, 0);
    const parts = [`<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">`,
      `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">`,
      `<title>Отчёт: план объектов (${esc(m.city_label)})</title><style>body{font:14px/1.45 system-ui,sans-serif;margin:16px;max-width:980px;color:#111;background:#fff}`,
      `table{border-collapse:collapse;margin:8px 0;font-size:12.5px}td,th{border:1px solid #ccc;padding:3px 6px;text-align:left;vertical-align:top}th{background:#f3f2ee}`,
      `.warn{border-left:3px solid #fab219;padding-left:8px}.muted{color:#666}pre{white-space:pre-wrap;background:#f6f6f4;padding:8px}</style></head><body>`,
      `<h1>Условный план объектов: ${esc(CATEGORIES[sc.category])}, ${esc(m.city_label)}</h1>`,
      `<p class="warn">Гипотеза для обсуждения, не решение акимата и не рекомендация строить. Расстояния — по прямой в квадрате среза ~2×2 км. Стоимости и бюджет — условные единицы, не тенге и не смета. Нет населения, вместимости, пеших маршрутов и трафика.${m.demo ? " Места, стоимости и веса — синтетический демо-набор." : ""}</p>`,
      `<h2>Параметры</h2>` + table(["Параметр", "Значение"], [["Схема", sc.schema_version], ["Город", m.city_label], ["Срез", m.release], ["source_snapshot", sc.source_snapshot], ["Метрика", METRIC],
        ["Бюджет, усл. ед.", sc.budget], ["Максимум объектов", sc.max_selected], ["Радиус охвата, м (не норматив)", sc.coverage_radius_m], ["Обязательные", idsText(sc.required_ids)], ["Исключённые", idsText(sc.excluded_ids)],
        ["problem_digest", m.problem_digest], ["scenario_digest", m.scenario_digest], ["Сформирован", m.generated]]),
      `<h2>Кандидатные места (гипотеза)</h2>` + table(["ID", "Широта", "Долгота", "Стоимость, усл. ед."], sc.candidates.map((c) => [c.id, c.lat.toFixed(6), c.lon.toFixed(6), c.cost])),
      `<h2>Контрольные точки</h2><p class="muted">Вес — приоритет пользователя, не число жителей.</p>` + table(["ID", "Широта", "Долгота", "Вес"], sc.control_points.map((p) => [p.id, p.lat.toFixed(6), p.lon.toFixed(6), p.weight]))];
    if (m.manual) {
      const mm = m.manual.metrics;
      parts.push(`<h2>Ручной план: ${esc(idsText(m.manual.selected_ids))} (${m.manual.feasibility.feasible ? "допустим" : "недопустим"})</h2>`,
        table(["Показатель", "До (только срез)", "После"], [["Взвешенное среднее", mText(m.manual.baseline.weighted_mean_mm), mText(mm.weighted_mean_mm)], ["Худшая точка", mText(m.manual.baseline.max_mm), mText(mm.max_mm)],
          ["Охват (вес)", `${m.manual.baseline.covered_weight} из ${tw}`, `${mm.covered_weight} из ${tw}`], ["Точек без расстояния", m.manual.baseline.unknown_count, mm.unknown_count], ["Стоимость, усл. ед.", 0, mm.cost]]),
        table(["Точка", "Вес", "До", "После", "Ближайший после", "Разница"], m.manual.rows.map((r) => [r.id, r.weight, mText(r.before_mm), mText(r.after_mm),
          r.nearest_after ? `${r.nearest_after.kind === "source" ? "запись среза " + (m.names[r.nearest_after.id] || r.nearest_after.id) : "кандидат " + r.nearest_after.id}` : "нет", r.delta_mm === null ? "не вычисляется" : mText(r.delta_mm)])));
    }
    if (m.result && m.result.status === "optimal") {
      const O = m.result.objectives;
      parts.push(`<h2>Точный перебор (${esc(m.result.evaluated)} наборов, допустимых ${esc(m.result.feasible_count)})</h2>`,
        table(["Цель", "Объекты", "Стоимость", "Среднее", "Худшая точка", "Охват (вес)"], ["mean", "minimax", "coverage"].map((k) => [OBJ_LABEL[k], idsText(O[k].ids), O[k].cost,
          mText(O[k].unknown_count ? null : O[k].weighted_sum_mm / tw), mText(O[k].max_mm), `${O[k].covered_weight} из ${tw}`])),
        `<h3>Парето: стоимость → сумма взвешенных расстояний</h3>` + table(["Объекты", "Стоимость", "Среднее"], m.result.pareto.map((p) => [idsText(p.ids), p.cost, mText(p.weighted_sum_mm / tw)])));
    } else if (m.result && m.result.status === "infeasible") parts.push(`<h2>Точный перебор</h2><p>Допустимых планов нет: ${esc(m.result.reasons.map((r) => r.text).join("; "))}</p>`);
    else parts.push(`<h2>Точный перебор</h2><p class="muted">Не запускался для текущих параметров.</p>`);
    if (m.sens && m.sens.length) parts.push(`<h3>Изменение бюджета</h3>` + table(["Бюджет", "Статус", "«Среднее»", "«Худшая точка»", "«Охват»"], m.sens.map((x) => [x.budget, x.status,
      ...["mean", "minimax", "coverage"].map((k) => (x.objectives ? idsText(x.objectives[k].ids) : "—"))])));
    if (m.explanation) parts.push(`<h2>Объяснение (шаблон, не LLM)</h2><pre>${esc(m.explanation)}</pre>`);
    parts.push(`<h2>Источники и ограничения</h2><p>${esc(m.attribution)}</p><p class="muted">Записи Overture/OSM — вторичные данные, не официальный реестр; QA-метки показывают совпадающие координаты, возможные дубли и сомнения в категории. Ближайшая запись в срезе — не обязательно ближайшее учреждение в городе. Отчёт создан локально прототипом city-evidence; в нём нет скриптов и внешних ссылок.</p></body></html>`);
    return parts.join("\n") + "\n";
  }

  const api = { SCHEMA, METRIC, CATEGORIES, LIMITS, PlanError, mmOf, sourceSnapshot, makeContext, validatePlanScenario, problemDigest, scenarioDigest,
    precompute, precomputeFromMatrix, feasibility, metricsOf, evaluatePlan, createSearch, optimizePlans, sensitivity, KEYS, cmpIds, isId: (v) => ID_RE.test(v), popcount,
    internal: { evaluate: evaluateInternal, createSearch: createSearchInternal }, derivedOf: (ctx, sc, F) => derivedOf(ctx, validatePlanScenario(sc, ctx), F), exportPlanScenario, importPlanScenario,
    explanationDigest, explainPlans, reportHtml, esc };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN = api;
})(typeof window !== "undefined" ? window : globalThis);
