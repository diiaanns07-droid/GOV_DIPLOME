/* «Если добавить объект» — pure what-if module (contract city-whatif-v1, research/round-7/FEATURE_SPEC.txt).
 * Straight-line (haversine) distance from user control points to the nearest record of one category in the current
 * slice, before / after one hypothetical object. No walking time, no population, no provision.
 * Pure functions only (no DOM); the UI is in app.js. Works in the browser (window.CITY_WHATIF) and in Node.
 * Python reference with the same rules: tools/whatif_ref.py (cross-checked by tests/whatif.cjs).
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-whatif-v1";
  const R_EARTH = 6371008.8;
  const FORMULA = "haversine:R=6371008.8";
  const CATEGORIES = { school: "Школа", outpatient_clinic: "Поликлиника" };
  const CITIES = ["shymkent", "astana"];
  const MAX_POINTS = 10, MAX_BYTES = 256 * 1024, ID_RE = /^[A-Za-z0-9_-]{1,32}$/;
  const TOP_KEYS = new Set(["schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object", "derived_results"]);

  class WhatIfError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }

  // Haversine in metres; input [longitude, latitude]; intermediate value clamped to [0, 1]; no rounding.
  function haversine(lon1, lat1, lon2, lat2) {
    const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r, dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
    let a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    a = Math.min(1, Math.max(0, a));
    return 2 * R_EARTH * Math.asin(Math.sqrt(a));
  }

  const inBbox = (bb, lon, lat) => bb[0] <= lon && lon <= bb[2] && bb[1] <= lat && lat <= bb[3];
  const finite = (v) => typeof v === "number" && Number.isFinite(v);

  // Nearest candidate: minimum distance, ties broken by the smaller ID (stable; the length does not depend on it).
  function nearest(cands, lon, lat) {
    let best = null;
    for (const p of cands) {
      const d = haversine(lon, lat, p.lon, p.lat);
      if (best === null || d < best.d || (d === best.d && p.id < best.p.id)) best = { p, d };
    }
    return best;
  }

  /* places: data.js records of the city; category: school|outpatient_clinic; points: [{id, lon, lat}];
   * proposed: null | {id, lon, lat, category, kind}. Returns rows with unrounded metres. */
  function compute(places, category, points, proposed) {
    if (!CATEGORIES[category]) throw new WhatIfError("bad_category", String(category));
    if (proposed && proposed.category !== category) throw new WhatIfError("bad_category", "категория проекта ≠ выбранной");
    const cands = places.filter((p) => p.group === category).slice().sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    const rows = points.map((cp) => {
      const nb = nearest(cands, cp.lon, cp.lat);
      const before = nb ? nb.d : null;
      const dp = proposed ? haversine(cp.lon, cp.lat, proposed.lon, proposed.lat) : null;
      let after, nearestAfter;
      if (before === null) { after = dp; nearestAfter = dp === null ? null : "proposed"; }
      else if (dp === null || dp >= before) { after = before; nearestAfter = "source"; }
      else { after = dp; nearestAfter = "proposed"; }
      const delta = before !== null && after !== null ? before - after : null;
      return { id: cp.id, lon: cp.lon, lat: cp.lat, before, after, delta, nearest_before: nb ? nb.p.id : null,
        nearest_after: nearestAfter, proposed_distance: dp };
    });
    return { category, candidates: cands.length, rows };
  }

  // Fingerprint of the slice used: city, release, sha256 of the places file, digest of all places, formula.
  function sourceSnapshot(data, city, F) {
    const c = data.cities[city];
    if (!c) throw new WhatIfError("bad_city", String(city));
    const fsha = c.files && c.files.places_social && c.files.places_social.sha256;
    return "sha256:" + F.sha256hex(JSON.stringify([SCHEMA, city, c.release, fsha || null, F.placesDigest(data, city), FORMULA]));
  }

  // ---------- strict JSON: rejects NaN/Infinity tokens, numbers that overflow (1e999), duplicate keys, trailing data ----------
  function parseStrict(text) {
    if (typeof text !== "string") throw new WhatIfError("bad_json", "ожидается текст");
    let bytes = 0;
    for (const ch of text) { const c = ch.codePointAt(0); bytes += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4; }
    if (bytes > MAX_BYTES) throw new WhatIfError("too_large", `${bytes} байт > ${MAX_BYTES}`);
    let i = 0;
    const err = (m) => { throw new WhatIfError("bad_json", `${m} (позиция ${i})`); };
    const ws = () => { while (i < text.length && " \t\n\r".includes(text[i])) i++; };
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
      if (!m) err("недопустимый токен (NaN/Infinity и прочее не допускаются)");
      i += m[0].length;
      const v = Number(m[0]);
      if (!Number.isFinite(v)) err(`число ${m[0]} не конечно`);
      return v;
    }
    function str() {
      i++; let out = "";
      while (i < text.length) {
        const ch = text[i];
        if (ch === '"') { i++; return out; }
        if (ch === "\\") {
          const e = text[i + 1];
          const map = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
          if (e in map) { out += map[e]; i += 2; continue; }
          if (e === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) { out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16)); i += 6; continue; }
          err("неверная escape-последовательность");
        }
        if (ch < " ") err("управляющий символ в строке");
        out += ch; i++;
      }
      err("незакрытая строка");
    }
    const v = value(0); ws();
    if (i !== text.length) err("лишние данные после JSON");
    return v;
  }

  // ---------- scenario validation (city-whatif-v1); returns a clean copy, never the parsed object itself ----------
  function validateScenario(obj, data, F, { requirePoints = true } = {}) {
    const fail = (code, d) => { throw new WhatIfError(code, d); };
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) fail("bad_shape", "ожидается объект");
    for (const k of Object.keys(obj)) if (!TOP_KEYS.has(k)) fail("unknown_field", `поле ${JSON.stringify(k).slice(0, 40)} не допускается`);
    for (const k of ["schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object"])
      if (!(k in obj)) fail("missing_field", k);
    if (obj.schema_version !== SCHEMA) fail("bad_version", `версия ${String(obj.schema_version).slice(0, 40)} ≠ ${SCHEMA}`);
    if (!CITIES.includes(obj.city_id) || !data.cities[obj.city_id]) fail("bad_city", String(obj.city_id).slice(0, 40));
    const city = obj.city_id, bb = data.cities[city].bbox;
    const snap = sourceSnapshot(data, city, F);
    if (obj.source_snapshot !== snap) fail("foreign_snapshot", "сценарий сделан на другом срезе данных (source_snapshot не совпадает)");
    if (!CATEGORIES[obj.category]) fail("bad_category", String(obj.category).slice(0, 40));
    const cps = obj.control_points;
    if (!Array.isArray(cps)) fail("bad_shape", "control_points — массив");
    if (cps.length > MAX_POINTS || (requirePoints && cps.length < 1)) fail("bad_points", `контрольных точек должно быть 1..${MAX_POINTS}, получено ${cps.length}`);
    const ids = new Set();
    const point = (p, what, keys) => {
      if (!p || typeof p !== "object" || Array.isArray(p)) fail("bad_shape", `${what}: ожидается объект`);
      const ks = Object.keys(p).sort().join(",");
      if (ks !== keys.slice().sort().join(",")) fail("bad_shape", `${what}: поля ${ks} ≠ ${keys.join(",")}`);
      if (typeof p.id !== "string" || !ID_RE.test(p.id)) fail("bad_id", `${what}: id ${JSON.stringify(p.id).slice(0, 40)} (A–Z, 0–9, _-, до 32 символов)`);
      if (ids.has(p.id)) fail("duplicate_id", p.id);
      ids.add(p.id);
      if (!finite(p.lon) || !finite(p.lat) || Math.abs(p.lon) > 180 || Math.abs(p.lat) > 90) fail("bad_coord", `${p.id}: координаты не конечны или вне диапазона`);
      if (!inBbox(bb, p.lon, p.lat)) fail("outside_bbox", `${p.id}: вне квадрата среза ${city}`);
      return p;
    };
    const control_points = cps.map((p, k) => { const q = point(p, `control_points[${k}]`, ["id", "lon", "lat"]); return { id: q.id, lon: q.lon, lat: q.lat }; });
    let proposed_object = null;
    const po = obj.proposed_object;
    if (po !== null) {
      if (Array.isArray(po)) fail("too_many_proposed", "допускается не более одного проектного объекта");
      const q = point(po, "proposed_object", ["id", "lon", "lat", "category", "kind"]);
      if (q.kind !== "hypothetical") fail("bad_kind", "proposed_object.kind должен быть hypothetical");
      if (q.category !== obj.category) fail("bad_category", "категория проектного объекта ≠ category сценария");
      proposed_object = { id: q.id, lon: q.lon, lat: q.lat, category: q.category, kind: "hypothetical" };
    }
    return { schema_version: SCHEMA, city_id: city, source_snapshot: snap, category: obj.category, control_points, proposed_object };
  }

  // Import: size + strict JSON + validation; derived_results in the file are ignored and recomputed.
  function importScenario(text, data, F) {
    const sc = validateScenario(parseStrict(text), data, F);
    return { scenario: sc, result: compute(data.cities[sc.city_id].places, sc.category, sc.control_points, sc.proposed_object) };
  }

  // Export: input fields first, derived values in a separate, labelled block (recomputed on import, never trusted).
  function exportScenario(sc, data, F) {
    const clean = validateScenario(sc, data, F);
    const res = compute(data.cities[clean.city_id].places, clean.category, clean.control_points, clean.proposed_object);
    const out = { ...clean, derived_results: { note: "производные значения; при импорте пересчитываются и не принимаются из файла",
      formula: FORMULA, unit: "m", rows: res.rows.map((r) => ({ id: r.id, before_m: r.before, after_m: r.after, delta_m: r.delta,
        nearest_before: r.nearest_before, nearest_after: r.nearest_after })) } };
    return JSON.stringify(out, null, 1) + "\n";
  }

  // ---------- template explanation over computed facts; digest covers snapshot, category, points, project and values ----------
  function scenarioDigest(sc, res, F) {
    const facts = [sc.source_snapshot, sc.category, sc.control_points.map((p) => [p.id, p.lon, p.lat]),
      sc.proposed_object ? [sc.proposed_object.id, sc.proposed_object.lon, sc.proposed_object.lat, sc.proposed_object.category] : null,
      res.rows.map((r) => [r.id, r.before, r.after, r.delta, r.nearest_before, r.nearest_after])];
    return F.sha256hex(JSON.stringify(facts)).slice(0, 16);
  }
  const m = (v) => (v === null ? "нет данных" : Math.round(v) + " м");
  function explain(sc, res, names, digestAtRequest, F) {
    const cur = scenarioDigest(sc, res, F);
    if (digestAtRequest !== cur) throw new WhatIfError("stale_scenario", "сценарий изменился после запроса — объяснение отклонено");
    const cat = CATEGORIES[sc.category];
    const lines = [`Шаблонное объяснение (не LLM). Категория: ${cat}. Расстояния по прямой в пределах среза, отпечаток ${cur}.`];
    if (!sc.proposed_object) lines.push("Проектный объект не поставлен: «после» равно «до».");
    if (res.candidates === 0) lines.push("В срезе нет исходных записей этой категории; улучшение не вычисляется.");
    for (const r of res.rows) {
      const nb = r.nearest_before ? `ближайшая запись «${names[r.nearest_before] || r.nearest_before}»` : "исходных записей в срезе нет";
      const after = r.nearest_after === "proposed" ? "ближе проектный объект" : r.nearest_after === "source" ? "ближайшая запись та же" : "";
      lines.push(`${r.id}: до ${m(r.before)} (${nb}); после ${m(r.after)}${after ? " (" + after + ")" : ""}; разница ${r.delta === null ? "не вычисляется" : m(r.delta)}.`);
    }
    lines.push("Положительная разница — только уменьшение геометрического расстояния, не время пешком и не обеспеченность местами.");
    return { text: lines.join("\n"), digest: cur };
  }

  const api = { SCHEMA, R_EARTH, FORMULA, CATEGORIES, MAX_POINTS, MAX_BYTES, WhatIfError, haversine, inBbox, compute, sourceSnapshot,
    parseStrict, validateScenario, importScenario, exportScenario, scenarioDigest, explain };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_WHATIF = api;
})(typeof window !== "undefined" ? window : globalThis);
