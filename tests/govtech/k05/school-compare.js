/* school-compare.js — school-access-case-v1 comparison adapter (research/round-10/CONTRACT.txt), K05 round 10.
 * Proposed location: web/govtech/school-compare.js (next to core/). Pure module, no DOM. Node: module.exports;
 * browser: window.CITY_SCHOOL_COMPARE (needs core/facts.js, core/whatif.js, core/plan.js loaded first).
 *
 * It is NOT a new optimiser. Nearest-target rows come from the BUILD's exact planner (core/plan.js) through the
 * minimal patch precomputeFromMatrix(); this module only
 *   - validates the case and a precomputed distance matrix (geodesic or pedestrian-v1, explicit status per pair),
 *   - enumerates the allowed sets (empty + every set of <= max_new_objects candidates; 1 in the main path),
 *   - computes CONTRACT metrics, the default lexicographic choice, a separately labelled minimax choice,
 *   - emits deterministic facts (for the AI/explanation layer) and limitations, and a canonical case_digest.
 * Distances are geometric/model path lengths in integer mm. Points are equal-weight analysis points, NOT residents or
 * pupils; "share" is a share of points. No budget is invented: missing costs disable money optimisation only.
 */
(function (root) {
  "use strict";
  const isNode = typeof module !== "undefined" && module.exports;
  const PL = isNode ? require("./core/plan.js") : root.CITY_PLAN;
  const F = isNode ? require("./core/facts.js") : root.CITY_FACTS;
  const SCHEMA = "school-access-case-v1";
  const OUT_SCHEMA = "school-access-compare-v1";
  const CANON = "k05-school-access-canon-v1";
  const METHODS = ["geodesic", "pedestrian-v1"];
  const STATUSES = ["ok", "disconnected", "outside_coverage", "access_unknown", "unsnappable"];
  const KINDS = ["observed", "observed_secondary", "derived", "hypothesis", "synthetic"];
  const ELIG = ["known_public", "known_restricted", "unknown"];
  const LIMITS = { origins: 25, candidates: 16, schools: 200, max_new_objects: 3, threshold_m: [1, 100000] };
  // K05 policy (documented, part of the digest): restricted schools are not targets; schools with unknown access
  // eligibility ARE targets but every row that relies on one is flagged.
  const ELIGIBILITY_POLICY = "public_and_unknown_flagged-v1";
  const OBJECTIVE = "contract-lex-v1: unknown_count, sum_distance_mm, max_distance_mm, sorted IDs (empty first)";
  const MINIMAX = "minimax-v1 (другая цель): unknown_count, max_distance_mm, sum_distance_mm, sorted IDs";

  class CompareError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const fail = (code, d) => { throw new CompareError(code, d); };
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
  const finite = (v) => typeof v === "number" && Number.isFinite(v);
  const isMm = (v) => Number.isSafeInteger(v) && v >= 0;

  function keysExactly(o, what, req, opt) {
    if (!isObj(o)) fail("bad_shape", what + ": ожидается объект");
    for (const k of Object.keys(o)) if (!req.includes(k) && !(opt || []).includes(k)) fail("unknown_field", `${what}.${k}`);
    for (const k of req) if (!(k in o)) fail("missing_field", `${what}.${k}`);
  }
  function checkEntity(e, what, bbox, sourceIds, inBbox) {
    if (!PL.isId(e.id)) fail("bad_id", `${what}: ${JSON.stringify(e.id)}`);
    if (typeof e.label !== "string") fail("bad_label", `${what} ${e.id}`);
    if (!finite(e.lon) || !finite(e.lat) || e.lon < -180 || e.lon > 180 || e.lat < -90 || e.lat > 90) fail("bad_coordinate", `${what} ${e.id}`);
    if (inBbox && !(e.lon >= bbox[0] && e.lon <= bbox[2] && e.lat >= bbox[1] && e.lat <= bbox[3])) fail("outside_bbox", `${what} ${e.id}`);
    if (!KINDS.includes(e.kind)) fail("bad_kind", `${what} ${e.id}`);
    if (!Array.isArray(e.source_ids) || e.source_ids.some((s) => !sourceIds.has(s))) fail("unknown_source", `${what} ${e.id}`);
    if (!isObj(e.field_provenance) || !Array.isArray(e.qa)) fail("bad_shape", `${what} ${e.id}: field_provenance/qa`);
  }

  /* validateCase(input) -> clean normalised case (deep copy) or CompareError. Order of arrays is irrelevant later. */
  function validateCase(c) {
    keysExactly(c, "case", ["schema_version", "case_id", "city_id", "title", "bbox", "snapshot_id", "sources", "schools", "origins",
      "candidates", "selected_candidate_ids", "parameters", "model_assumptions"]);
    if (c.schema_version !== SCHEMA) fail("bad_version", String(c.schema_version).slice(0, 40));
    if (c.city_id !== "shymkent" && c.city_id !== "astana") fail("bad_city", String(c.city_id).slice(0, 40));
    if (typeof c.case_id !== "string" || !c.case_id || typeof c.title !== "string" || typeof c.snapshot_id !== "string" || !c.snapshot_id) fail("bad_shape", "case_id/title/snapshot_id");
    const bb = c.bbox;
    if (!Array.isArray(bb) || bb.length !== 4 || !bb.every(finite) || !(bb[0] < bb[2] && bb[1] < bb[3])) fail("bad_bbox", "bbox [west,south,east,north]");
    for (const k of ["sources", "schools", "origins", "candidates", "selected_candidate_ids", "model_assumptions"]) if (!Array.isArray(c[k])) fail("bad_shape", k);
    const srcIds = new Set();
    for (const s of c.sources) {
      keysExactly(s, "source", ["id", "url", "publisher", "title", "retrieved_at", "verification_status", "license"],
        ["published_at", "data_period", "content_sha256"]);
      if (typeof s.id !== "string" || !s.id || srcIds.has(s.id)) fail("bad_source", String(s.id));
      if (!["primary_checked", "secondary_only", "conflict", "not_fetched"].includes(s.verification_status)) fail("bad_source", s.id + ": verification_status");
      srcIds.add(s.id);
    }
    if (c.origins.length > LIMITS.origins) fail("too_many_origins", `${c.origins.length} > ${LIMITS.origins}`);
    if (c.candidates.length > LIMITS.candidates) fail("too_many_candidates", `${c.candidates.length} > ${LIMITS.candidates}`);
    if (c.schools.length > LIMITS.schools) fail("too_many_schools", String(c.schools.length));
    const ids = new Set(), seen = (id) => { if (ids.has(id)) fail("duplicate_id", id); ids.add(id); };
    const base = ["id", "label", "lon", "lat", "kind", "source_ids", "field_provenance", "qa"];
    for (const s of c.schools) {
      keysExactly(s, "school", [...base, "category", "access_eligibility", "capacity", "capacity_source_ids"]);
      checkEntity(s, "school", bb, srcIds, false);           // documented buffer: schools may lie outside the bbox
      if (!ELIG.includes(s.access_eligibility)) fail("bad_eligibility", s.id);
      if (s.capacity !== null && !(finite(s.capacity) && s.capacity >= 0)) fail("bad_capacity", s.id);
      seen(s.id);
    }
    for (const o of c.origins) {
      keysExactly(o, "origin", base, ["parent_source_id", "method"]);
      checkEntity(o, "origin", bb, srcIds, true); seen(o.id);
    }
    for (const k of c.candidates) {
      keysExactly(k, "candidate", [...base, "cost", "land_status"]);
      checkEntity(k, "candidate", bb, srcIds, true);
      if (k.kind !== "hypothesis" && k.kind !== "synthetic") fail("bad_candidate_kind", k.id);
      if (k.cost !== null) {
        keysExactly(k.cost, "candidate.cost", ["value", "currency", "period", "kind", "source_ids"]);
        if (!(finite(k.cost.value) && k.cost.value >= 0) || typeof k.cost.currency !== "string" || typeof k.cost.kind !== "string") fail("bad_cost", k.id);
      }
      if (typeof k.land_status !== "string") fail("bad_land_status", k.id);
      seen(k.id);
    }
    const cand = new Set(c.candidates.map((k) => k.id));
    if (new Set(c.selected_candidate_ids).size !== c.selected_candidate_ids.length || c.selected_candidate_ids.some((x) => !cand.has(x))) fail("bad_selection", "selected_candidate_ids");
    const p = c.parameters;
    keysExactly(p, "parameters", ["distance_method", "routing_policy_id", "threshold_m", "max_new_objects"]);
    if (!METHODS.includes(p.distance_method)) fail("bad_method", String(p.distance_method));
    if (!(p.routing_policy_id === null || (typeof p.routing_policy_id === "string" && p.routing_policy_id))) fail("bad_policy", "routing_policy_id");
    if (p.distance_method === "pedestrian-v1" && p.routing_policy_id === null) fail("bad_policy", "pedestrian-v1 needs routing_policy_id");
    if (!finite(p.threshold_m) || p.threshold_m < LIMITS.threshold_m[0] || p.threshold_m > LIMITS.threshold_m[1]) fail("bad_threshold", String(p.threshold_m));
    if (!Number.isInteger(p.max_new_objects) || p.max_new_objects < 0 || p.max_new_objects > LIMITS.max_new_objects) fail("bad_max_new_objects", String(p.max_new_objects));
    return JSON.parse(JSON.stringify(c));
  }

  /* validateMatrix(case, matrix) -> Map "origin\u0000target" -> entry. matrix = {method, policy_id, entries:[...]} where each
   * entry is a CONTRACT matrix record. Exactly one entry per (origin, school or candidate) pair; nothing else. */
  function validateMatrix(c, m) {
    keysExactly(m, "matrix", ["method", "policy_id", "entries"]);
    if (m.method !== c.parameters.distance_method) fail("matrix_method_mismatch", `${m.method} ≠ ${c.parameters.distance_method}`);
    if (m.policy_id !== c.parameters.routing_policy_id) fail("matrix_policy_mismatch", `${m.policy_id} ≠ ${c.parameters.routing_policy_id}`);
    if (!Array.isArray(m.entries)) fail("bad_shape", "matrix.entries");
    const origins = new Set(c.origins.map((o) => o.id)), targets = new Set([...c.schools, ...c.candidates].map((t) => t.id));
    const out = new Map();
    for (const e of m.entries) {
      keysExactly(e, "matrix entry", ["origin_id", "target_id", "distance_mm", "status", "method", "policy_id", "route_edge_ids", "geometry", "assumptions"]);
      if (!origins.has(e.origin_id) || !targets.has(e.target_id)) fail("matrix_unknown_ref", `${e.origin_id} → ${e.target_id}`);
      if (e.method !== m.method || e.policy_id !== m.policy_id) fail("matrix_mixed_method", `${e.origin_id} → ${e.target_id}`);
      if (!STATUSES.includes(e.status)) fail("matrix_bad_status", String(e.status));
      if (e.status === "ok" ? !isMm(e.distance_mm) : e.distance_mm !== null) fail("matrix_bad_distance", `${e.origin_id} → ${e.target_id}: status ${e.status}, distance ${e.distance_mm}`);
      if (!Array.isArray(e.route_edge_ids) || !Array.isArray(e.assumptions)) fail("bad_shape", "matrix entry arrays");
      const k = e.origin_id + "\u0000" + e.target_id;
      if (out.has(k)) fail("matrix_duplicate_pair", `${e.origin_id} → ${e.target_id}`);
      out.set(k, e);
    }
    if (out.size !== origins.size * targets.size) fail("matrix_incomplete", `${out.size} of ${origins.size * targets.size} pairs`);
    return out;
  }

  // ---------- canonical digest: arrays of entities sorted by id, matrix by (origin, target); keys sorted ----------
  const canon = (v) => (Array.isArray(v) ? "[" + v.map(canon).join(",") + "]" : isObj(v)
    ? "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}" : JSON.stringify(v));
  const byId = (a, b) => cmpStr(a.id, b.id);
  function caseDigest(c, m) {
    const sortIds = (e) => ({ ...e, source_ids: e.source_ids.slice().sort(cmpStr) });
    const body = { canon: CANON, objective: OBJECTIVE, eligibility_policy: ELIGIBILITY_POLICY,
      case: { ...c, sources: c.sources.slice().sort(byId), schools: c.schools.map(sortIds).sort(byId), origins: c.origins.map(sortIds).sort(byId),
        candidates: c.candidates.map(sortIds).sort(byId), selected_candidate_ids: c.selected_candidate_ids.slice().sort(cmpStr),
        model_assumptions: c.model_assumptions.slice().sort((a, b) => cmpStr(canon(a), canon(b))) },
      matrix: { method: m.method, policy_id: m.policy_id,
        entries: m.entries.slice().sort((a, b) => cmpStr(a.origin_id, b.origin_id) || cmpStr(a.target_id, b.target_id)) } };
    return "sha256:" + F.sha256hex(canon(body));
  }

  // ---------- metrics (CONTRACT) from rows ----------
  function metricsOf(rows, thresholdMm) {
    const known = rows.filter((r) => r.after_mm !== null);
    const sum = known.reduce((s, r) => s + r.after_mm, 0);
    const within = known.filter((r) => r.after_mm <= thresholdMm).length;
    return { total_origins: rows.length, known_count: known.length, unknown_count: rows.length - known.length,
      partial_count: rows.filter((r) => r.status === "partial").length,
      sum_distance_mm: sum, mean_distance_mm: known.length ? sum / known.length : null,
      max_distance_mm: known.length ? Math.max(...known.map((r) => r.after_mm)) : null,
      within_threshold_count: within, within_threshold_share_of_all_points: rows.length ? within / rows.length : null };
  }
  const keyLex = (m) => [m.unknown_count, m.sum_distance_mm, m.max_distance_mm === null ? -1 : m.max_distance_mm];   // max null only if all unknown: equal for all sets
  const keyMinimax = (m) => [m.unknown_count, m.max_distance_mm === null ? -1 : m.max_distance_mm, m.sum_distance_mm];
  const cmpKey = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; return 0; };
  const cmpIds = (a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) { const x = cmpStr(a[i], b[i]); if (x) return x; } return a.length - b.length; };

  function subsets(ids, k) {
    const out = [[]];
    const rec = (start, cur) => { for (let i = start; i < ids.length; i++) { const nx = [...cur, ids[i]]; out.push(nx); if (nx.length < k) rec(i + 1, nx); } };
    if (k > 0) rec(0, []);
    return out;
  }

  function costSummary(c) {
    if (!c.candidates.length) return { mode: "no_candidates", note: "кандидатов нет" };
    if (c.candidates.some((k) => k.cost === null)) return { mode: "no_cost_data", note: "стоимость хотя бы одного кандидата неизвестна — денежная оптимизация отключена, географическое сравнение работает" };
    const u = new Set(c.candidates.map((k) => [k.cost.currency, k.cost.period, k.cost.kind].join("|")));
    if (u.size > 1) return { mode: "mixed_units_not_comparable", note: "стоимости в разных единицах/периодах/видах — не суммируются" };
    const [currency, period, kind] = [...u][0].split("|");
    return { mode: "homogeneous", currency, period, kind, note: "стоимости показываются справочно; бюджет в основном кейсе не задаётся" };
  }

  /* compareCase(case, matrix) -> CONTRACT output. Throws CompareError on invalid input (atomic: nothing partial). */
  function compareCase(caseIn, matrixIn) {
    const c = validateCase(caseIn);
    const M = validateMatrix(c, matrixIn);
    const thr = Math.round(c.parameters.threshold_m * 1000);
    const targets = c.schools.filter((s) => s.access_eligibility !== "known_restricted");
    const eligUnknown = new Set(targets.filter((s) => s.access_eligibility === "unknown").map((s) => s.id));
    const ent = new Map([...c.schools, ...c.candidates, ...c.origins].map((e) => [e.id, e]));
    const lookup = (o, t) => { const e = M.get(o + "\u0000" + t); return e.status === "ok" ? e.distance_mm : null; };
    const sc = { control_points: c.origins.map((o) => ({ id: o.id, lon: o.lon, lat: o.lat, weight: 1 })),
      candidates: c.candidates.map((k) => ({ id: k.id })), sources: targets.map((s) => ({ id: s.id })),
      // plan.js evaluate() also returns its own budget/feasibility/metric fields: they are NOT used here (no budget in this case)
      coverage_radius_m: c.parameters.threshold_m, required_ids: [], excluded_ids: [], budget: 0, max_selected: c.parameters.max_new_objects };
    const P = PL.precomputeFromMatrix(sc, lookup);
    const costs = costSummary(c);

    function plan(planId, ids, label) {
      const ev = PL.internal.evaluate(null, sc, ids, P);
      const used = [...targets.map((s) => s.id), ...ev.selected_ids];
      const rows = ev.rows.map((r) => {
        const unknownTargets = used.filter((t) => M.get(r.id + "\u0000" + t).status !== "ok");
        const status = r.after_mm === null ? "unknown" : unknownTargets.length ? "partial" : "ok";
        const nt = r.nearest_after ? r.nearest_after.id : null;
        const src = new Set([...(ent.get(r.id).source_ids || []), ...(nt ? ent.get(nt).source_ids : [])]);
        return { origin_id: r.id, before_mm: r.before_mm, after_mm: r.after_mm,
          delta_mm: r.before_mm !== null && r.after_mm !== null ? r.after_mm - r.before_mm : null,
          status, nearest_target_id: nt, nearest_target_kind: r.nearest_after ? (r.nearest_after.kind === "source" ? "school" : "candidate") : null,
          nearest_access_eligibility_unknown: nt !== null && eligUnknown.has(nt),
          unknown_target_ids: unknownTargets.sort(cmpStr), source_ids: [...src].sort(cmpStr) };
      });
      const metrics = metricsOf(rows, thr);
      const lim = [];
      if (metrics.unknown_count) lim.push("unknown_paths");
      if (metrics.partial_count) lim.push("some_targets_without_known_path");
      if (rows.some((r) => r.nearest_access_eligibility_unknown)) lim.push("nearest_school_access_eligibility_unknown");
      let cost = null;
      if (costs.mode === "homogeneous") cost = { value: ids.reduce((s, id) => s + ent.get(id).cost.value, 0), currency: costs.currency, period: costs.period, kind: costs.kind };
      return { plan_id: planId, label, selected_candidate_ids: ev.selected_ids, rows, metrics, cost, limitations: lim };
    }

    const plans = [plan("current", [], "Сейчас: существующие школы")];
    for (const id of c.selected_candidate_ids) plans.push(plan("candidate:" + id, [id], `Вариант ${id}`));
    // exact enumeration of allowed sets (main path: empty + each single candidate). No cost/budget constraint.
    const all = subsets(c.candidates.map((k) => k.id).sort(cmpStr), c.parameters.max_new_objects).map((ids) => plan("set:" + (ids.join("+") || "empty"), ids, ""));
    const pick = (key) => all.slice().sort((a, b) => cmpKey(key(a.metrics), key(b.metrics)) || cmpIds(a.selected_candidate_ids, b.selected_candidate_ids))[0];
    const auto = pick(keyLex), mm = pick(keyMinimax);
    plans.push({ ...auto, plan_id: "auto:contract-lex", label: "Предложение по правилу контракта (лучшее среди введённых кандидатов)", objective: OBJECTIVE });
    plans.push({ ...mm, plan_id: "auto:minimax", label: "Другая цель: минимум худшего пути", objective: MINIMAX });

    const digest = caseDigest(c, matrixIn);
    const facts = [];
    const fact = (planId, metric, value, unit, originId, srcIds, assumptions) =>
      facts.push({ id: `${planId}/${originId ? "origin:" + originId + "/" : ""}${metric}`, metric, value, unit, plan_id: planId, origin_id: originId || null,
        kind: "derived", source_ids: srcIds, assumptions });
    const matrixSrc = `matrix:${c.parameters.distance_method}/${c.parameters.routing_policy_id === null ? "none" : c.parameters.routing_policy_id}`;
    const baseAssume = [c.parameters.distance_method === "geodesic" ? "geodesic: прямая линия, не путь по улицам" : "pedestrian-v1: путь модельной сети по политике " + c.parameters.routing_policy_id,
      "точки анализа равновесные; доля — доля точек, не жителей и не учеников"];
    const caseSrc = [...new Set([...c.schools, ...c.origins, ...c.candidates].flatMap((e) => e.source_ids))].sort(cmpStr);
    for (const p of plans) {
      const s = [matrixSrc, ...caseSrc];
      const m = p.metrics;
      fact(p.plan_id, "total_origins", m.total_origins, "points", null, s, baseAssume);
      fact(p.plan_id, "known_count", m.known_count, "points", null, s, baseAssume);
      fact(p.plan_id, "unknown_count", m.unknown_count, "points", null, s, baseAssume);
      fact(p.plan_id, "mean_distance_mm", m.mean_distance_mm, "mm", null, s, [...baseAssume, "среднее только среди известных путей"]);
      fact(p.plan_id, "max_distance_mm", m.max_distance_mm, "mm", null, s, [...baseAssume, "максимум только среди известных путей"]);
      fact(p.plan_id, "within_threshold_count", m.within_threshold_count, "points", null, s, [...baseAssume, `порог ${c.parameters.threshold_m} м — параметр пользователя, не норматив`]);
      fact(p.plan_id, "within_threshold_share_of_all_points", m.within_threshold_share_of_all_points, "share", null, s, [...baseAssume, "знаменатель — все точки, неизвестные не покрыты"]);
      fact(p.plan_id, "selected_candidate_ids", p.selected_candidate_ids, "ids", null, s, []);
      if (p.plan_id !== "current") for (const r of p.rows) fact(p.plan_id, "delta_mm", r.delta_mm, "mm", r.origin_id, [matrixSrc, ...r.source_ids], [...baseAssume, "delta = после − до; отрицательное — ближе"]);
    }
    const limitations = [
      { code: "analysis_points_not_population", text: "Точки равновесные: это не жители, не ученики и не спрос." },
      { code: "candidates_hypothetical", text: "Кандидаты — гипотезы; статус земли не подтверждён, проект не обещается." },
      { code: "no_capacity_claim", text: "Вместимость и дефицит мест не оцениваются." },
      { code: "best_among_entered", text: "«Лучшее» — только среди введённых кандидатов и при текущих допущениях." },
      c.parameters.distance_method === "geodesic"
        ? { code: "geodesic_straight_line", text: "Расстояние по прямой — нижняя граница пешего пути, не маршрут." }
        : { code: "model_network", text: "Нет пути в срезе — ограничение модельной сети, не доказанная физическая недоступность." },
      { code: "cost", text: costs.note, cost_mode: costs.mode },
    ];
    if (eligUnknown.size) limitations.push({ code: "eligibility_unknown", text: "У части школ доступ (общедоступная/ограниченная) неизвестен; такие школы учитываются, строки помечены." });
    return { schema_version: OUT_SCHEMA, case_id: c.case_id, city_id: c.city_id, case_digest: digest, method: c.parameters.distance_method,
      policy_id: c.parameters.routing_policy_id, threshold_mm: thr, eligibility_policy: ELIGIBILITY_POLICY, objective: OBJECTIVE,
      cost_mode: costs.mode, evaluated_sets: all.length, plans, facts, limitations };
  }

  const api = { SCHEMA, OUT_SCHEMA, CANON, ELIGIBILITY_POLICY, OBJECTIVE, MINIMAX, LIMITS, CompareError, validateCase, validateMatrix, caseDigest, compareCase };
  if (isNode) module.exports = api; else root.CITY_SCHOOL_COMPARE = api;
})(typeof window !== "undefined" ? window : globalThis);
