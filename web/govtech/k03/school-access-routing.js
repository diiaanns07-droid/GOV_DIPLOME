/* K03 r10: небольшой адаптер school-access-case-v1 → матрица расстояний CONTRACT r10 поверх routing.js. Без DOM и сети.
 * Не планировщик и не compareCase: только строки {origin_id, target_id, distance_mm, status, method, policy_id, route_edge_ids,
 * geometry, assumptions} для каждой точки × (школы + кандидаты) и слои GeoJSON для MapLibre, привязанные к этим строкам.
 * Браузер: window.K03_SCHOOL_ROUTING (после routing.js); Node: require("./school-access-routing.js").
 */
(function (root) {
  "use strict";
  const R = typeof module !== "undefined" && module.exports ? require("./routing.js") : root.K03_ROUTING;
  const MATRIX_SCHEMA = "k03-distance-matrix-v1";
  const LIMITS = { origins: 25, candidates: 16 };  // безопасный лимит CONTRACT r10
  const STATUS_RU = {
    ok: "путь найден",
    access_unknown: "пешеходный доступ на пути не подтверждён данными",
    disconnected: "в модельной сети среза пути нет (это не доказательство физической недоступности)",
    outside_coverage: "путь вне среза не проверен",
    unsnappable: "точка дальше 100 м от сети — к сети не привязана",
  };
  const ASSUMPTION_RU = {
    foot_access_unknown: "доступ для пешеходов на части пути не отмечен в данных",
    cycleway_foot_unknown: "часть пути — велодорожка, доступ для пешеходов не отмечен",
    vehicle_oneway_not_applied_to_foot: "одностороннее движение OSM считается автомобильным",
    conditional_foot_rule: "на части пути есть условное ограничение (время/вид)",
    snap_model_connection: "от точки до сети — модельный отрезок по прямой",
    boundary_unverified: "более короткий путь за краем среза не исключён",
    route_partly_outside_slice: "путь частично выходит за край среза",
    straight_line_not_route: "прямая, не маршрут",
  };
  class AdapterError extends Error { constructor(code, detail) { super(code + ": " + detail); this.code = code; this.detail = detail; } }
  const fail = (c, d) => { throw new AdapterError(c, d); };
  const within = (inner, outer) => outer[0] <= inner[0] && outer[1] <= inner[1] && inner[2] <= outer[2] && inner[3] <= outer[3];

  /* distanceMatrix(case, G) — G = K03_ROUTING.prepare(graph города). Метод и политика берутся из case.parameters:
   * distance_method "geodesic" (routing_policy_id = null) или "pedestrian-v1" (routing_policy_id = pedestrian-v1-strict | -exploratory). */
  function distanceMatrix(c, G) {
    if (!c || c.schema_version !== "school-access-case-v1") fail("bad_case", "ожидается school-access-case-v1");
    if (c.city_id !== G.g.city) fail("other_city", `кейс ${String(c.city_id).slice(0, 20)}, граф ${G.g.city}`);
    if (!Array.isArray(c.bbox) || c.bbox.length !== 4 || !within(c.bbox, G.g.bbox)) fail("bbox_mismatch", "bbox кейса должен лежать в срезе графа");
    const p = c.parameters || {};
    const method = p.distance_method;
    if (method !== "geodesic" && method !== "pedestrian-v1") fail("bad_method", String(method));
    if (method === "geodesic" && p.routing_policy_id !== null) fail("bad_policy", "для прямой routing_policy_id = null");
    if (method === "pedestrian-v1" && !(p.routing_policy_id in R.POLICIES)) fail("bad_policy", String(p.routing_policy_id));
    const origins = c.origins || [], schools = c.schools || [], cands = c.candidates || [];
    if (origins.length > LIMITS.origins || cands.length > LIMITS.candidates) fail("too_many_points", `не больше ${LIMITS.origins} точек и ${LIMITS.candidates} кандидатов`);
    const targets = schools.map((s) => ({ ...s, role: "school" })).concat(cands.map((x) => ({ ...x, role: "candidate" })));
    const ids = new Set();
    for (const x of origins.concat(targets)) { if (ids.has(x.id)) fail("duplicate_id", String(x.id).slice(0, 64)); ids.add(x.id); }
    const rows = [];
    for (const o of origins) for (const t of targets) {
      const r = method === "geodesic" ? R.geodesic(G, o, t) : R.route(G, o, t, p.routing_policy_id);
      rows.push({ origin_id: o.id, target_id: t.id, target_role: t.role, distance_mm: r.distance_mm, status: r.status, method: r.method,
        policy_id: r.policy_id, route_edge_ids: r.route_edge_ids, geometry: r.geometry, assumptions: r.assumptions,
        reason: r.reason, label: r.label, parts: r.parts });
    }
    return { schema_version: MATRIX_SCHEMA, city_id: c.city_id, method, policy_id: method === "geodesic" ? null : p.routing_policy_id,
      graph_sha256: G.g.graph_sha256, policy_sha256: method === "geodesic" ? null : G.g.policy_sha256, max_snap_m: G.g.max_snap_m,
      license: G.g.license, rows };
  }

  /* routeLayers(matrix, {origin_id?, target_ids?}) → FeatureCollection для одного источника MapLibre: сеть сплошной линией,
   * модельные отрезки привязки и прямая — отдельные объекты (part = network | snap | geodesic). Линии только из строк ok. */
  function routeLayers(m, filter) {
    const f = filter || {}, feats = [];
    for (const r of m.rows) {
      if (r.status !== "ok" || (f.origin_id && r.origin_id !== f.origin_id) || (f.target_ids && !f.target_ids.includes(r.target_id))) continue;
      const base = { origin_id: r.origin_id, target_id: r.target_id, target_role: r.target_role, policy_id: r.policy_id, distance_mm: r.distance_mm,
        incomplete: r.assumptions.some((a) => a !== "snap_model_connection" && a !== "straight_line_not_route") };
      const cs = r.geometry.coordinates;
      if (r.method === "geodesic") { feats.push({ type: "Feature", properties: { ...base, part: "geodesic" }, geometry: r.geometry }); continue; }
      const so = r.parts[0].length_mm, st = r.parts[2].length_mm;
      const i0 = so > 0 ? 1 : 0, i1 = st > 0 ? cs.length - 2 : cs.length - 1;
      if (so > 0) feats.push({ type: "Feature", properties: { ...base, part: "snap", role: "origin" }, geometry: { type: "LineString", coordinates: cs.slice(0, 2) } });
      if (i1 > i0) feats.push({ type: "Feature", properties: { ...base, part: "network" }, geometry: { type: "LineString", coordinates: cs.slice(i0, i1 + 1) } });
      if (st > 0) feats.push({ type: "Feature", properties: { ...base, part: "snap", role: "target" }, geometry: { type: "LineString", coordinates: cs.slice(-2) } });
    }
    return { type: "FeatureCollection", features: feats };
  }

  /* explainRow(row) → короткий русский текст для карточки (только из полей строки; числа не придумываются). */
  function explainRow(r) {
    const head = r.status === "ok" ? `${(r.distance_mm / 1000).toFixed(0)} м — ${r.label}` : STATUS_RU[r.status];
    return [head, ...r.assumptions.filter((a) => a !== "straight_line_not_route").map((a) => ASSUMPTION_RU[a] || a)].join("; ");
  }

  const api = { MATRIX_SCHEMA, LIMITS, STATUS_RU, ASSUMPTION_RU, AdapterError, distanceMatrix, routeLayers, explainRow };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.K03_SCHOOL_ROUTING = api;
})(typeof window !== "undefined" ? window : globalThis);
