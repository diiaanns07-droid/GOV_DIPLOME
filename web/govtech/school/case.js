/* school-access-case-v1: one school-accessibility case, its distance matrix and the before/after comparison.
 * Pure functions (no DOM). Browser: window.SCHOOL_CASE (needs whatif.js and facts.js first). Node: module.exports.
 * Distances: straight line (haversine, R=6371008.8), rounded once to whole millimetres. Not a walking route.
 * Unknown distances stay null and are never counted as 0. Numbers shown in the UI and given to AI come only from here.
 */
(function (root) {
  "use strict";
  const NODE = typeof module !== "undefined" && module.exports;
  const X = NODE ? require("../core/whatif.js") : root.CITY_WHATIF;
  const F = NODE ? require("../core/facts.js") : root.CITY_FACTS;

  const SCHEMA = "school-access-case-v1";
  const COMPARE_SCHEMA = "school-access-compare-v1";
  const CANON = "sac-canon-v1";
  const GEODESIC = "geodesic";
  const METRIC = "haversine-mm-v1";
  const LIMITS = { origins: 25, candidates: 16, schools: 200, bytes: 256 * 1024 };
  const CITIES = ["shymkent", "astana"];
  const KINDS = ["observed", "observed_secondary", "derived", "hypothesis", "synthetic"];
  const VERIFICATION = ["primary_checked", "secondary_only", "conflict", "not_fetched"];
  const ELIGIBILITY = ["known_public", "known_restricted", "unknown"];
  const STATUSES = ["ok", "disconnected", "outside_coverage", "access_unknown", "unsnappable"];
  const ID = /^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,79}$/;
  // Default target policy: Overture school categories; records with a QA category doubt are left out.
  const SCHOOL_CATEGORIES = ["elementary_school", "middle_school", "high_school"];
  const TARGET_POLICY = "overture-school-category-v1";

  class CaseError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const fail = (code, detail) => { throw new CaseError(code, detail); };
  const mmOf = (m) => Math.round(m * 1000);
  const finite = (v) => typeof v === "number" && Number.isFinite(v);
  const isInt = (v) => Number.isInteger(v);
  const inBbox = (bb, lon, lat) => bb[0] <= lon && lon <= bb[2] && bb[1] <= lat && lat <= bb[3];
  const byId = (a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const r6 = (v) => Math.round(v * 1e6) / 1e6;

  // ---------- building a case from the pinned city slice ----------
  function sourceOf(city) {
    return {
      id: "overture-places-" + city.key, url: null, publisher: "Overture Maps Foundation (places; meta/Foursquare/OSM contributors)",
      title: "Overture places " + city.release + " — срез " + city.label + " ≈2×2 км",
      published_at: null, data_period: "release " + city.release, retrieved_at: city.retrieved_utc,
      verification_status: "secondary_only", license: "CDLA-Permissive-2.0 / Apache-2.0 / ODbL-1.0 (по записи)",
      content_sha256: city.files && city.files.places_social ? city.files.places_social.sha256 : null,
    };
  }
  function schoolOf(city, place, qaOf, srcId) {
    const qa = (qaOf ? qaOf(city.key, place) : []).map((q) => q.code).sort();
    const ds = (place.sources || []).map((s) => s.dataset).filter(Boolean);
    return {
      id: place.id, label: place.name || place.id, lon: place.lon, lat: place.lat, kind: "observed_secondary", source_ids: [srcId],
      field_provenance: { lon_lat: "overture:" + (ds.join("+") || "unknown"), label: "overture:" + (ds.join("+") || "unknown"), category: "overture category (не официальный тип)" },
      qa, category: place.category || "unknown", confidence: finite(place.confidence) ? place.confidence : null,
      access_eligibility: "unknown", capacity: null, capacity_source_ids: [],
    };
  }
  // Regular grid of analysis points: derived from the slice frame, equal weights, NOT residents or households.
  function gridPoints(bb, rows, cols, prefix, inset) {
    const out = [], [w, s, e, n] = bb;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const fx = (c + inset) / (cols - 1 + 2 * inset), fy = (r + inset) / (rows - 1 + 2 * inset);
      out.push({ id: `${prefix}${r + 1}${String.fromCharCode(97 + c)}`, lon: r6(w + (e - w) * fx), lat: r6(n - (n - s) * fy) });
    }
    return out;
  }
  function buildCase(D, cityId, qaOf, opts) {
    const city = D.cities[cityId];
    if (!city) fail("unknown_city", "нет среза для города " + cityId);
    const o = opts || {}, src = sourceOf(city);
    const schools = city.places.filter((p) => p.group === "school").map((p) => schoolOf(city, p, qaOf, src.id)).sort(byId);
    const origins = gridPoints(city.bbox, 5, 5, "p", 0.5).map((p) => ({ ...p, label: "Точка " + p.id.slice(1), kind: "derived", source_ids: [],
      parent_source_id: null, method: "bbox-grid-5x5-v1 (равномерная сетка внутри рамки среза)", weight: 1,
      field_provenance: { lon_lat: "derived: сетка по рамке среза" }, qa: [] }));
    const candidates = gridPoints(city.bbox, 3, 4, "m", 0.7).map((p) => ({ ...p, label: "Место " + p.id.slice(1).toUpperCase(), kind: "synthetic", source_ids: [],
      field_provenance: { lon_lat: "synthetic: сетка 3×4 для примера" }, qa: [], cost: null, land_status: "unknown" }));
    return {
      schema_version: SCHEMA, case_id: `${cityId}-school-access-${city.release}`, city_id: cityId,
      title: `${city.label}: доступность школ на участке ≈2×2 км`, bbox: city.bbox.slice(), snapshot_id: `overture-${city.release}-${cityId}`,
      sources: [src], schools, origins, candidates, selected_candidate_ids: [], variants: { A: null, B: null },
      parameters: { distance_method: GEODESIC, routing_policy_id: null, threshold_m: o.threshold_m || 500, max_new_objects: 1,
        target_policy: { id: TARGET_POLICY, categories: SCHOOL_CATEGORIES.slice(), exclude_qa: ["CATEGORY_DOUBT"], include_ids: [], exclude_ids: [] } },
      model_assumptions: [
        "Расстояние по прямой (haversine), не пешеходный маршрут и не время в пути.",
        "Точки анализа — равномерная сетка внутри рамки среза с равными весами; это не жители, не дома и не дети.",
        "Школы — вторичные записи Overture; допуск к приёму и вместимость неизвестны.",
        "Школы за пределами рамки среза не загружены: у края участка расстояния могут быть завышены.",
        "Места A/B — гипотезы для сравнения; наличие участка, стоимость и возможность строительства не проверены.",
      ],
    };
  }

  // ---------- validation (also for untrusted imports) ----------
  const KEYS = ["schema_version", "case_id", "city_id", "title", "bbox", "snapshot_id", "sources", "schools", "origins", "candidates",
    "selected_candidate_ids", "variants", "parameters", "model_assumptions"];
  function checkRecord(r, where, kinds) {
    if (!r || typeof r !== "object" || Array.isArray(r)) fail("bad_record", where + ": не объект");
    if (typeof r.id !== "string" || !ID.test(r.id)) fail("bad_id", where + ": недопустимый id");
    if (!finite(r.lon) || !finite(r.lat) || r.lon < -180 || r.lon > 180 || r.lat < -90 || r.lat > 90) fail("bad_coord", `${where} ${r.id}: координаты`);
    if (!kinds.includes(r.kind)) fail("bad_kind", `${where} ${r.id}: kind=${r.kind}`);
    if (!Array.isArray(r.source_ids) || !r.source_ids.every((s) => typeof s === "string")) fail("bad_sources", `${where} ${r.id}: source_ids`);
    if (r.qa !== undefined && !Array.isArray(r.qa)) fail("bad_qa", `${where} ${r.id}: qa`);
    if (typeof r.label !== "string" || r.label.length > 300) fail("bad_label", `${where} ${r.id}: label`);
  }
  function validateCase(c) {
    if (!c || typeof c !== "object" || Array.isArray(c)) fail("not_object", "кейс должен быть объектом");
    if (c.schema_version !== SCHEMA) fail("schema_version", "ожидается " + SCHEMA + ", получено " + c.schema_version);
    for (const k of Object.keys(c)) if (!KEYS.includes(k)) fail("unknown_field", "неизвестное поле " + k);
    for (const k of KEYS) if (!(k in c)) fail("missing_field", "нет поля " + k);
    if (!CITIES.includes(c.city_id)) fail("city", "city_id должен быть shymkent или astana");
    const bb = c.bbox;
    if (!Array.isArray(bb) || bb.length !== 4 || !bb.every(finite) || !(bb[0] < bb[2] && bb[1] < bb[3])) fail("bbox", "bbox [west,south,east,north]");
    if ((bb[2] - bb[0]) > 0.2 || (bb[3] - bb[1]) > 0.2) fail("bbox_size", "рамка больше допустимого участка");
    if (typeof c.snapshot_id !== "string" || !c.snapshot_id) fail("snapshot", "нет snapshot_id");
    if (!Array.isArray(c.sources) || !c.sources.length) fail("sources", "нужен хотя бы один источник");
    const srcIds = new Set();
    for (const s of c.sources) {
      if (!s || typeof s.id !== "string" || !ID.test(s.id)) fail("source_id", "источник без допустимого id");
      if (!VERIFICATION.includes(s.verification_status)) fail("verification_status", s.id + ": " + s.verification_status);
      srcIds.add(s.id);
    }
    for (const [name, lim] of [["schools", LIMITS.schools], ["origins", LIMITS.origins], ["candidates", LIMITS.candidates]]) {
      if (!Array.isArray(c[name])) fail(name, name + " должен быть массивом");
      if (c[name].length > lim) fail("limit_" + name, `${name}: ${c[name].length} > ${lim}`);
    }
    const seen = new Set();
    const uniq = (r, where) => { if (seen.has(r.id)) fail("duplicate_id", `${where}: повтор id ${r.id}`); seen.add(r.id); };
    for (const s of c.schools) {
      checkRecord(s, "school", KINDS); uniq(s, "school");
      if (!ELIGIBILITY.includes(s.access_eligibility)) fail("eligibility", s.id + ": access_eligibility");
      if (s.capacity !== null && !(isInt(s.capacity) && s.capacity >= 0)) fail("capacity", s.id + ": capacity число или null");
      for (const id of s.source_ids) if (!srcIds.has(id)) fail("unknown_source", `${s.id}: источник ${id} не описан`);
    }
    for (const o of c.origins) {
      checkRecord(o, "origin", ["observed", "observed_secondary", "derived", "synthetic"]); uniq(o, "origin");
      if (!inBbox(bb, o.lon, o.lat)) fail("origin_outside", `${o.id}: точка вне рамки участка`);
      if (o.weight !== 1) fail("weight", `${o.id}: в первом сценарии веса равны 1`);
    }
    for (const k of c.candidates) {
      checkRecord(k, "candidate", ["hypothesis", "synthetic"]); uniq(k, "candidate");
      if (!inBbox(bb, k.lon, k.lat)) fail("candidate_outside", `${k.id}: место вне рамки участка`);
      if (k.land_status !== "unknown" && k.land_status !== "confirmed") fail("land_status", k.id + ": land_status");
      if (k.cost !== null && (typeof k.cost !== "object" || !finite(k.cost.value) || k.cost.value <= 0 || !Array.isArray(k.cost.source_ids))) fail("cost", k.id + ": cost null или {value,currency,period,kind,source_ids}");
    }
    const cand = new Set(c.candidates.map((k) => k.id));
    if (!Array.isArray(c.selected_candidate_ids) || !c.selected_candidate_ids.every((id) => cand.has(id))) fail("selected", "selected_candidate_ids ссылаются на неизвестные места");
    if (!c.variants || typeof c.variants !== "object") fail("variants", "нет variants {A,B}");
    for (const v of ["A", "B"]) if (c.variants[v] !== null && !cand.has(c.variants[v])) fail("variants", `вариант ${v} ссылается на неизвестное место`);
    for (const k of Object.keys(c.variants)) if (k !== "A" && k !== "B") fail("variants", "допустимы только A и B");
    const p = c.parameters || fail("parameters", "нет parameters");
    if (p.distance_method !== GEODESIC) fail("method", "в этой сборке доступен только geodesic (по прямой); pedestrian-v1 не подключён");
    if (p.routing_policy_id !== null) fail("policy", "для прямой routing_policy_id = null");
    if (!isInt(p.threshold_m) || p.threshold_m < 50 || p.threshold_m > 5000) fail("threshold", "threshold_m — целое 50…5000");
    if (p.max_new_objects !== 1) fail("max_new_objects", "в основном кейсе max_new_objects = 1");
    const tp = p.target_policy;
    if (!tp || tp.id !== TARGET_POLICY || !Array.isArray(tp.categories) || !Array.isArray(tp.exclude_qa) || !Array.isArray(tp.include_ids) || !Array.isArray(tp.exclude_ids)) fail("target_policy", "target_policy " + TARGET_POLICY);
    const sch = new Set(c.schools.map((s) => s.id));
    for (const id of [...tp.include_ids, ...tp.exclude_ids]) if (!sch.has(id)) fail("target_policy", "ручной выбор ссылается на неизвестную школу " + id);
    if (!Array.isArray(c.model_assumptions) || !c.model_assumptions.every((s) => typeof s === "string")) fail("assumptions", "model_assumptions — строки");
    return c;
  }

  // ---------- target policy ----------
  function targetStatus(c, s) {
    const tp = c.parameters.target_policy;
    if (tp.exclude_ids.includes(s.id)) return { eligible: false, reason: "исключено пользователем" };
    if (tp.include_ids.includes(s.id)) return { eligible: true, reason: "включено пользователем" };
    if (!tp.categories.includes(s.category)) return { eligible: false, reason: `категория «${s.category}» — не школа по правилу ${tp.id}` };
    const q = (s.qa || []).find((x) => tp.exclude_qa.includes(x));
    if (q) return { eligible: false, reason: "QA: " + q };
    return { eligible: true, reason: "категория школы, QA без сомнений в категории" };
  }

  // ---------- canonical form + digest ----------
  function canon(v) {
    if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
    if (v && typeof v === "object") return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}";
    if (typeof v === "number" && !Number.isFinite(v)) fail("canon", "нечисловое значение");
    return JSON.stringify(v === undefined ? null : v);
  }
  function semantic(c) {
    const sortStr = (a) => a.slice().sort();
    return {
      canon: CANON, schema_version: c.schema_version, city_id: c.city_id, snapshot_id: c.snapshot_id, bbox: c.bbox,
      sources: c.sources.map((s) => ({ id: s.id, verification_status: s.verification_status, content_sha256: s.content_sha256 || null })).sort(byId),
      schools: c.schools.map((s) => ({ id: s.id, lon: s.lon, lat: s.lat, kind: s.kind, source_ids: sortStr(s.source_ids), qa: sortStr(s.qa || []),
        category: s.category, access_eligibility: s.access_eligibility, capacity: s.capacity })).sort(byId),
      origins: c.origins.map((o) => ({ id: o.id, lon: o.lon, lat: o.lat, kind: o.kind, weight: o.weight })).sort(byId),
      candidates: c.candidates.map((k) => ({ id: k.id, lon: k.lon, lat: k.lat, kind: k.kind, cost: k.cost, land_status: k.land_status })).sort(byId),
      selected_candidate_ids: sortStr(c.selected_candidate_ids), variants: { A: c.variants.A, B: c.variants.B },
      parameters: { ...c.parameters, target_policy: { ...c.parameters.target_policy, categories: sortStr(c.parameters.target_policy.categories),
        exclude_qa: sortStr(c.parameters.target_policy.exclude_qa), include_ids: sortStr(c.parameters.target_policy.include_ids), exclude_ids: sortStr(c.parameters.target_policy.exclude_ids) } },
      metric: METRIC,
    };
  }
  const caseDigest = (c) => "sha256:" + F.sha256hex(canon(semantic(c)));

  // ---------- distance matrix (straight line) ----------
  function geodesicMatrix(c) {
    const targets = [...c.schools.filter((s) => targetStatus(c, s).eligible), ...c.candidates];
    const rows = [];
    for (const o of c.origins) for (const t of targets) {
      const m = X.haversine(o.lon, o.lat, t.lon, t.lat);
      rows.push({ origin_id: o.id, target_id: t.id, distance_mm: mmOf(m), status: "ok", method: GEODESIC, policy_id: null, route_edge_ids: [],
        geometry: { type: "LineString", coordinates: [[o.lon, o.lat], [t.lon, t.lat]] }, assumptions: ["straight_line_not_route"] });
    }
    return { method: GEODESIC, metric: METRIC, policy_id: null, rows };
  }
  function checkMatrix(c, mx) {
    if (!mx || !Array.isArray(mx.rows)) fail("matrix", "нет строк матрицы");
    if (mx.method !== c.parameters.distance_method) fail("matrix_method", "метод матрицы не совпадает с кейсом");
    for (const r of mx.rows) {
      if (!STATUSES.includes(r.status)) fail("matrix_status", r.status);
      if (r.status === "ok" ? !(isInt(r.distance_mm) && r.distance_mm >= 0) : r.distance_mm !== null) fail("matrix_distance", `${r.origin_id}→${r.target_id}: distance_mm при status=${r.status}`);
    }
  }

  // ---------- comparison ----------
  function nearestOf(index, oid, targets) {
    let best = null;
    for (const t of targets) {
      const r = index.get(oid + "\u0000" + t.id);
      if (!r || r.status !== "ok") continue;
      if (!best || r.distance_mm < best.mm || (r.distance_mm === best.mm && t.id < best.t.id)) best = { mm: r.distance_mm, t };
    }
    return best;
  }
  function planOf(c, index, eligible, id, selected, label) {
    const extra = c.candidates.filter((k) => selected.includes(k.id));
    const thr = c.parameters.threshold_m * 1000;
    const rows = c.origins.slice().sort(byId).map((o) => {
      const b = nearestOf(index, o.id, eligible), a = nearestOf(index, o.id, [...eligible, ...extra]);
      return { origin_id: o.id, before_mm: b ? b.mm : null, after_mm: a ? a.mm : null, delta_mm: a && b ? a.mm - b.mm : null,
        status: a ? "ok" : "unknown", nearest_target_id: a ? a.t.id : null, source_ids: a ? a.t.source_ids.slice() : [] };
    });
    const known = rows.filter((r) => r.after_mm !== null);
    const sum = known.reduce((s, r) => s + r.after_mm, 0);
    const metrics = { total_origins: rows.length, known_count: known.length, unknown_count: rows.length - known.length,
      sum_distance_mm: known.length ? sum : null, mean_distance_mm: known.length ? Math.round(sum / known.length) : null,
      max_distance_mm: known.length ? Math.max(...known.map((r) => r.after_mm)) : null,
      within_threshold_count: known.filter((r) => r.after_mm <= thr).length,
      within_threshold_share_of_all_points: rows.length ? known.filter((r) => r.after_mm <= thr).length / rows.length : null };
    const closer = rows.filter((r) => r.delta_mm !== null && r.delta_mm < 0).length;
    const limitations = [];
    if (!eligible.length) limitations.push("no_eligible_school");
    if (metrics.unknown_count) limitations.push("unknown_distances");
    return { id, label, selected_candidate_ids: selected.slice().sort(), rows, metrics, closer_count: closer, limitations };
  }
  const rankKey = (m) => [m.unknown_count, m.sum_distance_mm === null ? Infinity : m.sum_distance_mm, m.max_distance_mm === null ? Infinity : m.max_distance_mm];
  function cmpPlans(a, b) {
    const ka = rankKey(a.metrics), kb = rankKey(b.metrics);
    for (let i = 0; i < 3; i++) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
    const ia = a.selected_candidate_ids.join(","), ib = b.selected_candidate_ids.join(",");
    if (a.selected_candidate_ids.length !== b.selected_candidate_ids.length) return a.selected_candidate_ids.length - b.selected_candidate_ids.length;
    return ia < ib ? -1 : ia > ib ? 1 : 0;
  }
  function compareCase(c, mx) {
    validateCase(c); checkMatrix(c, mx);
    const index = new Map(mx.rows.map((r) => [r.origin_id + "\u0000" + r.target_id, r]));
    const eligible = c.schools.filter((s) => targetStatus(c, s).eligible);
    const plans = [planOf(c, index, eligible, "current", [], "Сейчас")];
    for (const v of ["A", "B"]) if (c.variants[v]) plans.push(planOf(c, index, eligible, v, [c.variants[v]], "Вариант " + v));
    // Default auto-choice among the empty set and every single candidate (max_new_objects = 1).
    const options = [plans[0], ...c.candidates.map((k) => planOf(c, index, eligible, "auto", [k.id], ""))].sort(cmpPlans);
    const best = options[0];
    plans.push({ ...best, id: "auto", label: "Лучшее по правилу", rule: "lexicographic_min[unknown_count,sum_distance_mm,max_distance_mm]; затем ID; пустой набор при равенстве" });
    const facts = [];
    const fact = (plan, metric, value, unit, origin, extraAssumptions) => facts.push({ id: `${plan.id}/${origin ? origin + "/" : ""}${metric}`, metric, value, unit,
      plan_id: plan.id, origin_id: origin || null, kind: "derived", source_ids: origin ? (plan.rows.find((r) => r.origin_id === origin) || { source_ids: [] }).source_ids : c.sources.map((s) => s.id),
      assumptions: ["straight_line_not_route", ...(extraAssumptions || [])] });
    for (const p of plans) {
      for (const [k, v] of Object.entries(p.metrics)) fact(p, k, v, k.endsWith("_mm") ? "mm" : k.endsWith("share_of_all_points") ? "share" : "points");
      fact(p, "closer_count", p.closer_count, "points");
      if (p.id !== "current") for (const r of p.rows) fact(p, "delta_mm", r.delta_mm, "mm", r.origin_id);
    }
    const limitations = ["straight_line_not_route", "schools_outside_slice_not_loaded", "access_eligibility_unknown", "capacity_unknown",
      "secondary_source_not_registry", "grid_points_not_population", "candidates_hypothetical_land_unknown", "no_cost_data"];
    return { schema_version: COMPARE_SCHEMA, case_digest: caseDigest(c), method: mx.method, metric: METRIC, policy_id: mx.policy_id,
      threshold_m: c.parameters.threshold_m, eligible_school_ids: eligible.map((s) => s.id).sort(), plans, facts, limitations };
  }

  // A short verdict between two plans, built from computed metrics only.
  function verdict(cmp, aId, bId) {
    const a = cmp.plans.find((p) => p.id === aId), b = cmp.plans.find((p) => p.id === bId);
    if (!a || !b) return { code: "incomplete", winner: null };
    const cur = cmp.plans[0];
    const gainA = a.metrics.sum_distance_mm !== null && cur.metrics.sum_distance_mm !== null && a.metrics.sum_distance_mm < cur.metrics.sum_distance_mm;
    const gainB = b.metrics.sum_distance_mm !== null && cur.metrics.sum_distance_mm !== null && b.metrics.sum_distance_mm < cur.metrics.sum_distance_mm;
    if (!gainA && !gainB) return { code: "no_gain", winner: null };
    const o = cmpPlans({ ...a, selected_candidate_ids: [] }, { ...b, selected_candidate_ids: [] });
    if (o === 0) return { code: "tie", winner: null };
    return { code: "better", winner: o < 0 ? aId : bId };
  }

  // ---------- import / export (untrusted input) ----------
  function exportCase(c) { validateCase(c); return JSON.stringify({ ...c, case_digest: caseDigest(c) }, null, 2); }
  function importCase(text, D) {
    if (typeof text !== "string") fail("import_type", "ожидается текст JSON");
    if (text.length > LIMITS.bytes) fail("import_size", `файл больше ${LIMITS.bytes / 1024} КБ`);
    let raw;
    try { raw = JSON.parse(text); } catch (e) { fail("import_json", "файл не является JSON"); }
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) fail("import_type", "ожидается объект кейса");
    const claimed = raw.case_digest;
    const c = { ...raw }; delete c.case_digest;
    validateCase(c);
    const city = D && D.cities[c.city_id];
    if (!city) fail("import_city", "нет загруженного среза для " + c.city_id);
    if (c.snapshot_id !== `overture-${city.release}-${c.city_id}`) fail("import_snapshot", `кейс построен на ${c.snapshot_id}; загружен срез ${city.release}. Другой снимок не подставляется.`);
    const digest = caseDigest(c);
    if (claimed !== undefined && claimed !== digest) fail("import_digest", "case_digest файла не совпадает с пересчитанным: файл изменён");
    return c;
  }

  const api = { SCHEMA, COMPARE_SCHEMA, CANON, METRIC, LIMITS, TARGET_POLICY, SCHOOL_CATEGORIES, CaseError, buildCase, validateCase, targetStatus,
    canon, caseDigest, geodesicMatrix, compareCase, verdict, cmpPlans, exportCase, importCase };
  if (NODE) module.exports = api;
  else root.SCHOOL_CASE = api;
})(typeof window !== "undefined" ? window : globalThis);
