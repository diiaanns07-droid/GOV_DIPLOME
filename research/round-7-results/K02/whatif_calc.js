/* K02 r7: эталонный расчётный модуль «Если добавить объект» (city-whatif-v1), строго по FEATURE_SPEC r7.
 * Изолирован: не меняет prototypes/city-evidence. Сборщик может заменить его своим модулем — адаптер
 * whatif_facts.js принимает любой результат той же формы и сам проверяет его инварианты.
 * Расстояние ПО ПРЯМОЙ (гаверсинус), не время пешком и не доступность. Работает в браузере и Node.
 */
(function (root) {
  "use strict";
  const SCHEMA = "city-whatif-v1";
  const R_EARTH_M = 6371008.8;
  const CATEGORIES = ["school", "outpatient_clinic"];
  const CITIES = ["shymkent", "astana"];
  const MAX_POINTS = 10, MAX_ID_LEN = 64;
  const PARAMS = { formula: "haversine", earth_radius_m: R_EARTH_M, input_order: "lon,lat", clamp: "[0,1]" };

  class WhatifError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }

  // Гаверсинус, вход [lon, lat] в градусах; промежуточное значение зажато в [0,1]; без округления.
  function haversineM(a, b) {
    const rad = Math.PI / 180;
    const dLat = (b[1] - a[1]) * rad, dLon = (b[0] - a[0]) * rad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
    const hc = Math.min(1, Math.max(0, h));
    return 2 * R_EARTH_M * Math.asin(Math.sqrt(hc));
  }

  const finite = (v) => typeof v === "number" && Number.isFinite(v);
  function inBbox(p, bbox) { return p.lon >= bbox[0] && p.lon <= bbox[2] && p.lat >= bbox[1] && p.lat <= bbox[3]; }

  function checkPoint(p, bbox, what) {
    if (!p || typeof p !== "object") throw new WhatifError("bad_point", `${what}: ожидается {id, lon, lat}`);
    if (typeof p.id !== "string" || !p.id.length || p.id.length > MAX_ID_LEN) throw new WhatifError("bad_id", `${what}: id — строка 1..${MAX_ID_LEN}`);
    if (!finite(p.lon) || !finite(p.lat) || p.lon < -180 || p.lon > 180 || p.lat < -90 || p.lat > 90)
      throw new WhatifError("bad_coordinates", `${what} ${p.id}: координаты должны быть конечными числами в диапазоне`);
    if (!inBbox(p, bbox)) throw new WhatifError("outside_bbox", `${what} ${p.id} вне сохранённого квадрата города — расчёт только внутри среза`);
  }

  // Исходные записи выбранной категории в срезе города (одинаковая выборка до/после).
  function sourceRecords(data, city, category) {
    const c = data.cities[city];
    return c.places.filter((p) => p.group === category && finite(p.lon) && finite(p.lat) && inBbox(p, c.bbox))
      .map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, name: p.name, category: p.category }))
      .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  }

  // Отпечаток среза: из актуальных записей и параметров расчёта, не из имени файла.
  function sourceSnapshot(data, city, category, sha256hex) {
    const c = data.cities[city];
    const recs = sourceRecords(data, city, category).map((r) => [r.id, r.lon, r.lat]);
    const payload = JSON.stringify([SCHEMA, city, c.release, c.bbox, category, PARAMS, recs]);
    return "sha256:" + sha256hex(payload);
  }

  function nearest(point, recs) {
    let best = null;
    for (const r of recs) {  // recs отсортированы по id: при равенстве остаётся меньший id
      const d = haversineM([point.lon, point.lat], [r.lon, r.lat]);
      if (best === null || d < best.d) best = { d, rec: r };
    }
    return best;
  }

  /** scenario: {city_id, category, control_points:[{id,lon,lat}], proposed_object|null}. Импортированные
   *  distances/delta игнорируются: значения всегда пересчитываются здесь. */
  function compute(data, scenario, sha256hex) {
    const city = scenario.city_id, category = scenario.category;
    if (!CITIES.includes(city) || !data.cities[city]) throw new WhatifError("bad_city", `город ${city} не поддержан`);
    if (!CATEGORIES.includes(category)) throw new WhatifError("bad_category", `категория ${category} не поддержана`);
    const bbox = data.cities[city].bbox, pts = scenario.control_points;
    if (!Array.isArray(pts) || pts.length < 1 || pts.length > MAX_POINTS) throw new WhatifError("bad_points", `нужно 1..${MAX_POINTS} контрольных точек`);
    const ids = new Set();
    for (const p of pts) { checkPoint(p, bbox, "контрольная точка"); if (ids.has(p.id)) throw new WhatifError("duplicate_id", `id ${p.id} повторяется`); ids.add(p.id); }
    const proj = scenario.proposed_object ?? null;
    if (proj !== null) {
      checkPoint(proj, bbox, "проектный объект");
      if (proj.kind !== "hypothetical") throw new WhatifError("bad_project", "проект должен иметь kind=hypothetical");
      if (proj.category !== category) throw new WhatifError("bad_project", `категория проекта ${proj.category} ≠ ${category}`);
      if (ids.has(proj.id)) throw new WhatifError("duplicate_id", `id ${proj.id} повторяется`);
    }
    const recs = sourceRecords(data, city, category);
    const rows = pts.map((p) => {
      const nb = nearest(p, recs);
      const before = nb ? nb.d : null;
      const dProj = proj ? haversineM([p.lon, p.lat], [proj.lon, proj.lat]) : null;
      let after, delta, nearestAfter;
      if (before !== null) {
        after = proj ? Math.min(before, dProj) : before;
        delta = before - after;
        nearestAfter = proj && dProj < before ? "proposed" : "source";
      } else {
        after = proj ? dProj : null; delta = null; nearestAfter = proj ? "proposed" : null;
      }
      return { point_id: p.id, before_m: before, after_m: after, delta_m: delta, distance_to_proposed_m: dProj,
        nearest_source: nb ? { id: nb.rec.id, name: nb.rec.name, lon: nb.rec.lon, lat: nb.rec.lat } : null, nearest_after: nearestAfter };
    });
    return {
      schema_version: SCHEMA, city_id: city, category, release: data.cities[city].release, bbox,
      source_snapshot: sourceSnapshot(data, city, category, sha256hex), source_record_count: recs.length, params: PARAMS,
      control_points: pts.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat })),
      proposed_object: proj && { id: proj.id, lon: proj.lon, lat: proj.lat, category: proj.category, kind: "hypothetical" },
      rows,
    };
  }

  const api = { SCHEMA, R_EARTH_M, CATEGORIES, PARAMS, WhatifError, haversineM, sourceRecords, sourceSnapshot, compute };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_WHATIF_CALC = api;
})(typeof window !== "undefined" ? window : globalThis);
