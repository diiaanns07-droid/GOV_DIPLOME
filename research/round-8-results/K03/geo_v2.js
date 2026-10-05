/* K03 round 8 — geo adapter for city-plan-v2 (research/round-8/CORE_SPEC.txt). Pure functions, no DOM.
 * Browser: window.CITY_PLAN_GEO; Node: require(). Independent Python oracle: geo_v2_ref.py (not a translation).
 *
 * Scope (K03): slice bbox and fingerprint, input places (control points / hypothetical candidates), category sources
 * with provenance and QA, distances in integer millimetres (metric_version haversine-mm-v1) with a stable tie key.
 * Not in scope: budget/max_selected/required/excluded/optimisation (other modules use distanceTable()).
 * No district is required: a place on a disputed district border inside the bbox is valid.
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-plan-v2";
  const METRIC_VERSION = "haversine-mm-v1";
  const ADAPTER_VERSION = "k03-geo-v2.1";
  const R_EARTH = 6371008.8;
  const CATEGORIES = ["school", "outpatient_clinic"];
  const LIMITS = { control_points: [1, 25], candidates: [0, 16], weight: [1, 100], cost: [1, 1000000], id_max: 64 };
  const CONTROL_KEYS = ["id", "lat", "lon", "weight"];
  const CANDIDATE_KEYS = ["category", "cost", "id", "kind", "lat", "lon"];
  const KIND_RANK = { source: 0, hypothetical: 1 };

  class GeoError extends Error {
    constructor(code, path, detail) { super(`${code} @ ${path}: ${detail}`); this.code = code; this.path = path; this.detail = detail; }
  }

  // Haversine, metres, input [lon, lat], intermediate clamped to [0, 1]; then rounded once to integer mm.
  function haversineM(lon1, lat1, lon2, lat2) {
    const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r, dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
    let a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    a = Math.min(1, Math.max(0, a));
    return 2 * R_EARTH * Math.asin(Math.sqrt(a));
  }
  const toMm = (m) => Math.round(m * 1000);
  const distMm = (a, b) => toMm(haversineM(a.lon, a.lat, b.lon, b.lat));

  const isNum = (v) => typeof v === "number";
  const isInt = (v) => isNum(v) && Number.isInteger(v);
  const r7 = (x) => Math.round(x * 1e7) / 1e7;
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  // Stable order of reachable objects: distance, then source before hypothetical, then ID (code-unit order).
  const cmpNear = (a, b) => a.mm - b.mm || KIND_RANK[a.kind] - KIND_RANK[b.kind] || cmpStr(a.id, b.id);

  function sha256Default() {
    if (typeof require === "function") {
      const c = require("crypto");
      return (s) => c.createHash("sha256").update(s, "utf8").digest("hex");
    }
    return null;
  }

  function validBbox(b) {
    return Array.isArray(b) && b.length === 4 && b.every((x) => isNum(x) && Number.isFinite(x)) &&
      -180 <= b[0] && b[0] < b[2] && b[2] <= 180 && -90 <= b[1] && b[1] < b[3] && b[3] <= 90;
  }
  function inBox(b, lon, lat, inclusive) {
    return inclusive ? b[0] <= lon && lon <= b[2] && b[1] <= lat && lat <= b[3]
      : b[0] < lon && lon < b[2] && b[1] < lat && lat < b[3];
  }

  /* data = window.CITY_EVIDENCE (web/data.js), evidence = window.CITY_OBS (web/evidence.js).
   * opts.sha256hex(str) -> hex (browser: CITY_FACTS.sha256hex; Node: crypto by default). */
  function buildGeoContext(data, evidence, city, category, opts = {}) {
    const sha = opts.sha256hex || sha256Default();
    if (!sha) throw new GeoError("no_hash", "opts.sha256hex", "нужна функция sha256");
    const c = data && data.cities && data.cities[city];
    if (!c) throw new GeoError("bad_city", "city", String(city).slice(0, 40));
    if (!CATEGORIES.includes(category)) throw new GeoError("bad_category", "category", String(category).slice(0, 40));
    const su = evidence && evidence.cities && evidence.cities[city] && evidence.cities[city].spatial_unit;
    const bbox = su && su.bbox ? su.bbox : c.bbox;
    if (!validBbox(bbox) || (su && JSON.stringify(su.bbox) !== JSON.stringify(c.bbox)))
      throw new GeoError("bad_slice", "bbox", "bbox среза некорректен или различается в data.js и evidence.js");
    const inclusive = su ? su.edges_inclusive === true : true;
    const placesFile = c.files && c.files.places_social ? c.files.places_social.sha256 || null : null;
    const allRows = c.places.map((p) => [p.id, r7(p.lon), r7(p.lat)]).sort((a, b) => cmpStr(a[0], b[0]));
    const placesDigest = sha(JSON.stringify(allRows));
    const source_snapshot = "sha256:" + sha(JSON.stringify([SCHEMA, city, c.release || null, placesFile, placesDigest,
      bbox, inclusive, METRIC_VERSION]));
    const qa = (evidence && evidence.cities && evidence.cities[city] && evidence.cities[city].qa) || null;
    const coloc = new Map(), dups = new Map();
    if (qa) {
      for (const g of qa.colocated || []) for (const id of g.ids) coloc.set(id, { size: g.ids.length, lon: g.lon, lat: g.lat });
      for (const d of qa.possible_duplicates || []) {
        for (const [x, y] of [[d.a, d.b], [d.b, d.a]]) {
          if (!dups.has(x)) dups.set(x, []);
          dups.get(x).push({ other: y, rule: d.rule, distance_m: d.distance_m });
        }
      }
    }
    const exact = new Map();
    for (const p of c.places) {
      const k = JSON.stringify([p.lon, p.lat]);
      exact.set(k, (exact.get(k) || 0) + 1);
    }
    const sources = c.places.filter((p) => p.group === category).map((p) => ({
      key: "source:" + p.id, kind: "source", id: p.id, lon: p.lon, lat: p.lat, group: p.group, name: p.name ?? null,
      provenance: {
        overture_id: p.id, overture_version: p.overture_version ?? null, confidence: p.confidence ?? null,
        records: (p.sources || []).map((s) => ({ dataset: s.dataset ?? null, record_id: s.record_id ?? null,
          license: s.license ?? null, update_time: s.update_time ?? null })),
      },
      qa: {
        available: !!qa,
        colocated_group: coloc.get(p.id) || null,
        possible_duplicates: (dups.get(p.id) || []).slice().sort((a, b) => cmpStr(a.other, b.other)),
        category_doubt: (qa && qa.category_doubt && qa.category_doubt[p.id]) || null,
        same_exact_coordinates: exact.get(JSON.stringify([p.lon, p.lat])) - 1,
      },
    })).sort((a, b) => cmpStr(a.id, b.id));
    const sources_digest = "sha256:" + sha(JSON.stringify([source_snapshot, category, sources.map((s) => [s.id, s.lon, s.lat])]));
    const others = Object.keys(data.cities).filter((x) => x !== city).map((x) => {
      const ou = evidence && evidence.cities && evidence.cities[x] && evidence.cities[x].spatial_unit;
      return { city_id: x, bbox: data.cities[x].bbox, edges_inclusive: ou ? ou.edges_inclusive === true : true };
    });
    return { schema: SCHEMA, adapter_version: ADAPTER_VERSION, metric_version: METRIC_VERSION, city_id: city, category,
      bbox: bbox.slice(), edges_inclusive: inclusive, release: c.release || null, places_file_sha256: placesFile,
      source_snapshot, sources_digest, sources, other_slices: others };
  }

  // ---------- coordinates of one input place (same rules as K03 r7 point_check, typed errors) ----------
  function checkCoord(ctx, lon, lat, path) {
    if (!isNum(lon) || !isNum(lat)) throw new GeoError("not_number", path, "координаты должны быть числами");
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) throw new GeoError("not_finite", path, "NaN/Infinity не принимаются");
    if (Math.abs(lon) > 180 || Math.abs(lat) > 90) throw new GeoError("out_of_range", path, "долгота/широта вне диапазона");
    if (inBox(ctx.bbox, lon, lat, ctx.edges_inclusive)) return;
    if (inBox(ctx.bbox, lat, lon, ctx.edges_inclusive)) throw new GeoError("lon_lat_swapped", path, "похоже, перепутаны долгота и широта ([lon, lat])");
    for (const o of ctx.other_slices || []) {
      if (validBbox(o.bbox) && inBox(o.bbox, lon, lat, o.edges_inclusive)) throw new GeoError("other_city", path, `точка в квадрате города ${o.city_id}; не переносится`);
    }
    throw new GeoError("outside_bbox", path, `вне квадрата среза ${ctx.city_id}`);
  }

  function checkObject(o, keys, path) {
    if (!o || typeof o !== "object" || Array.isArray(o)) throw new GeoError("bad_shape", path, "ожидается объект");
    const ks = Object.keys(o).sort();
    if (ks.join(",") !== keys.join(",")) throw new GeoError("bad_shape", path, `поля ${ks.join(",").slice(0, 80)} ≠ ${keys.join(",")}`);
    if (typeof o.id !== "string" || o.id.length < 1 || o.id.length > LIMITS.id_max || /[\u0000-\u001f\u007f]/.test(o.id))
      throw new GeoError("bad_id", path + ".id", `id — строка 1..${LIMITS.id_max} без управляющих символов`);
  }

  /* places = {control_points: [{id, lon, lat, weight}], candidates: [{id, lon, lat, category, kind, cost}]}.
   * Returns clean copies; throws GeoError (code, path) on the first problem. opts.allowEmptyPoints for an empty UI state. */
  function validatePlaces(ctx, places, opts = {}) {
    if (!places || typeof places !== "object") throw new GeoError("bad_shape", "$", "ожидается объект");
    const cps = places.control_points, cands = places.candidates;
    if (!Array.isArray(cps)) throw new GeoError("bad_shape", "control_points", "ожидается массив");
    if (!Array.isArray(cands)) throw new GeoError("bad_shape", "candidates", "ожидается массив");
    const [pmin, pmax] = LIMITS.control_points, [cmin, cmax] = LIMITS.candidates;
    if (cps.length > pmax || (cps.length < pmin && !opts.allowEmptyPoints))
      throw new GeoError("too_many_points", "control_points", `нужно ${pmin}..${pmax}, получено ${cps.length}`);
    if (cands.length > cmax || cands.length < cmin)
      throw new GeoError("too_many_candidates", "candidates", `нужно ${cmin}..${cmax}, получено ${cands.length}`);
    const seenP = new Set(), seenC = new Set();
    const control_points = cps.map((p, i) => {
      const path = `control_points[${i}]`;
      checkObject(p, CONTROL_KEYS, path);
      if (seenP.has(p.id)) throw new GeoError("duplicate_id", path + ".id", p.id.slice(0, 64));
      seenP.add(p.id);
      if (!isInt(p.weight) || p.weight < LIMITS.weight[0] || p.weight > LIMITS.weight[1])
        throw new GeoError("bad_weight", path + ".weight", "вес — целое 1..100 (приоритет пользователя, не численность)");
      checkCoord(ctx, p.lon, p.lat, path);
      return { key: "control:" + p.id, kind: "control", id: p.id, lon: p.lon, lat: p.lat, weight: p.weight };
    });
    const candidates = cands.map((q, i) => {
      const path = `candidates[${i}]`;
      checkObject(q, CANDIDATE_KEYS, path);
      if (seenC.has(q.id)) throw new GeoError("duplicate_id", path + ".id", q.id.slice(0, 64));
      seenC.add(q.id);
      if (q.kind !== "hypothetical") throw new GeoError("bad_kind", path + ".kind", "кандидат только kind=hypothetical; исходные записи не изменяются");
      if (q.category !== ctx.category) throw new GeoError("bad_category", path + ".category", "категория кандидата ≠ категории сценария");
      if (!isInt(q.cost) || q.cost < LIMITS.cost[0] || q.cost > LIMITS.cost[1])
        throw new GeoError("bad_cost", path + ".cost", "стоимость — целое 1..1000000 условных единиц");
      checkCoord(ctx, q.lon, q.lat, path);
      return { key: "hypothetical:" + q.id, kind: "hypothetical", id: q.id, lon: q.lon, lat: q.lat, category: q.category,
        cost: q.cost, coincides_with_sources: [] };
    });
    // Coordinate coincidence is recorded, never treated as "this place already exists" (stage 3 rule).
    for (const q of candidates) {
      q.coincides_with_sources = ctx.sources.filter((s) => s.lon === q.lon && s.lat === q.lat).map((s) => s.key);
    }
    return { control_points, candidates };
  }

  /* Precomputed integer-mm distances. baseline[i] = nearest source of the category (or null when there are none),
   * with all tied keys; to_candidates[i][j] = mm from point i to candidate j (candidates in the given order). */
  function distanceTable(ctx, controlPoints, candidates) {
    const baseline = controlPoints.map((p) => {
      let best = null;
      const tied = [];
      for (const s of ctx.sources) {
        const o = { kind: "source", id: s.id, key: s.key, mm: distMm(p, s) };
        if (best === null || cmpNear(o, best) < 0) best = o;
      }
      if (best) for (const s of ctx.sources) if (distMm(p, s) === best.mm) tied.push(s.key);
      return best ? { key: best.key, id: best.id, mm: best.mm, tied_keys: tied.sort(cmpStr) } : null;
    });
    const to_candidates = controlPoints.map((p) => candidates.map((q) => distMm(p, q)));
    return { metric_version: METRIC_VERSION, source_snapshot: ctx.source_snapshot, point_keys: controlPoints.map((p) => p.key),
      candidate_keys: candidates.map((q) => q.key), baseline, to_candidates };
  }

  /* Nearest object after selecting candidates (indices into table.candidate_keys). Ties: source before hypothetical,
   * then ID. Returns {key, kind, mm} or null when nothing is available (distance null, never 0). */
  function nearestAfter(table, i, selected, candidates) {
    let best = table.baseline[i] ? { kind: "source", id: table.baseline[i].id, key: table.baseline[i].key, mm: table.baseline[i].mm } : null;
    for (const j of selected) {
      const o = { kind: "hypothetical", id: candidates[j].id, key: candidates[j].key, mm: table.to_candidates[i][j] };
      if (best === null || cmpNear(o, best) < 0) best = o;
    }
    return best ? { key: best.key, kind: best.kind, mm: best.mm } : null;
  }

  // ---------- stage 3: nearest source → provenance/QA; coordinates never confirm a place ----------
  const POSITION_STATUS = { source: "source_reported_unverified", hypothetical: "hypothetical" };
  const MESSAGES_RU = {
    source_reported_unverified: "координаты из записи Overture (вторичный источник); положение на месте не подтверждено",
    hypothetical: "условное место пользователя; не существующее учреждение",
    not_confirmed: "совпадение координат или отсутствие QA-замечаний не подтверждает учреждение",
    colocated: "координаты общие с группой записей (COLOCATED): возможно геокодирование по умолчанию",
    shared_coordinates: "те же координаты у других записей среза",
    possible_duplicate: "возможный дубль другой записи",
    category_doubt: "сомнение в категории записи",
    qa_unavailable: "QA-метки для среза не загружены — это не «замечаний нет»",
    no_provenance_records: "у записи нет sources[] — происхождение не подтверждено",
    record_id_missing: "у источника записи нет record_id",
    tie_shared_coordinates: "ничья в одних координатах: выбрана запись с меньшим ID, это не подтверждение места",
    tie_equal_distance: "ничья по расстоянию: выбрана запись с меньшим ID",
    coincides_with_source: "кандидат в координатах исходной записи; кандидат остаётся условным",
  };
  const byCode = (a, b) => cmpStr(a.code, b.code) || cmpStr(a.other || "", b.other || "");

  /* Provenance and QA of one source key of the context. Throws unknown_source for anything not in ctx.sources
   * (including hypothetical keys). Flags are codes; MESSAGES_RU gives UI text. No field ever says "confirmed". */
  function sourceEvidence(ctx, key) {
    const s = typeof key === "string" && key.startsWith("source:") ? ctx.sources.find((x) => x.key === key) : null;
    if (!s) throw new GeoError("unknown_source", "key", String(key).slice(0, 80));
    const flags = [];
    const recs = s.provenance.records;
    if (!recs.length) flags.push({ code: "no_provenance_records" });
    else if (recs.some((r) => !r.record_id)) flags.push({ code: "record_id_missing" });
    if (!s.qa.available) flags.push({ code: "qa_unavailable" });
    if (s.qa.colocated_group) flags.push({ code: "colocated", size: s.qa.colocated_group.size });
    if (s.qa.same_exact_coordinates > 0) flags.push({ code: "shared_coordinates", count: s.qa.same_exact_coordinates });
    for (const d of s.qa.possible_duplicates) flags.push({ code: "possible_duplicate", other: "source:" + d.other, rule: d.rule, distance_m: d.distance_m });
    if (s.qa.category_doubt) flags.push({ code: "category_doubt", rule: s.qa.category_doubt.rule });
    return { key: s.key, kind: "source", id: s.id, lon: s.lon, lat: s.lat, name: s.name,
      position_status: POSITION_STATUS.source, confirmation: "not_confirmed",
      provenance: { overture_id: s.provenance.overture_id, overture_version: s.provenance.overture_version,
        confidence: s.provenance.confidence, records: recs.map((r) => ({ ...r })) },
      flags: flags.sort(byCode) };
  }

  // A hypothetical candidate stays hypothetical even on top of a source record.
  function candidateEvidence(ctx, cand) {
    if (!cand || cand.kind !== "hypothetical" || typeof cand.key !== "string" || !cand.key.startsWith("hypothetical:"))
      throw new GeoError("bad_kind", "candidate", "ожидается проверенный кандидат validatePlaces()");
    const same = ctx.sources.filter((s) => s.lon === cand.lon && s.lat === cand.lat).map((s) => s.key).sort(cmpStr);
    return { key: cand.key, kind: "hypothetical", id: cand.id, position_status: POSITION_STATUS.hypothetical,
      confirmation: "not_confirmed", flags: same.length ? [{ code: "coincides_with_source", sources: same }] : [] };
  }

  /* Bind every baseline nearest of a distance table to source evidence. The table must come from this context
   * (same source_snapshot), otherwise stale_table. Ties are reported, never resolved into a "confirmed" place. */
  function bindNearestSources(ctx, table) {
    if (!table || table.source_snapshot !== ctx.source_snapshot || table.metric_version !== METRIC_VERSION)
      throw new GeoError("stale_table", "table.source_snapshot", "таблица расстояний построена на другом срезе или версии метрики");
    return table.point_keys.map((pk, i) => {
      const b = table.baseline[i];
      if (!b) return { point_key: pk, status: "no_sources", nearest: null, tied_count: 0, tie: null };
      const ev = sourceEvidence(ctx, b.key);
      for (const k of b.tied_keys) sourceEvidence(ctx, k);
      let tie = null;
      if (b.tied_keys.length > 1) {
        const sameXY = b.tied_keys.every((k) => { const s = ctx.sources.find((x) => x.key === k); return s.lon === ev.lon && s.lat === ev.lat; });
        tie = { code: sameXY ? "tie_shared_coordinates" : "tie_equal_distance", keys: b.tied_keys.slice() };
      }
      return { point_key: pk, status: "ok", nearest: ev, tied_count: b.tied_keys.length, tie };
    });
  }

  const api = { SCHEMA, METRIC_VERSION, ADAPTER_VERSION, R_EARTH, CATEGORIES, LIMITS, GeoError, haversineM, toMm, distMm,
    cmpNear, buildGeoContext, validatePlaces, checkCoord, distanceTable, nearestAfter,
    POSITION_STATUS, MESSAGES_RU, sourceEvidence, candidateEvidence, bindNearestSources };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN_GEO = api;
})(typeof window !== "undefined" ? window : globalThis);
