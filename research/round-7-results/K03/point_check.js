/* K03 round 7: проверка координат контрольной точки / проектного объекта по bbox среза (city-whatif-v1).
   Те же правила, что point_check.py (эталон); общие fixtures — fixtures.json. Без зависимостей; браузер и node.
   checkPoint(slice, point, otherSlices) -> {ok, code, message, point, on_edge[, other_city_id]}
   slice = {city_id, bbox: [W, S, E, N], edges_inclusive}; point = [lon, lat] или {lon, lat}.
   Район не проверяется и не требуется: это сведения K03, а не условие приёма точки. */
(function (root) {
  "use strict";
  const MESSAGES = {
    inside: "точка внутри квадрата среза",
    on_edge: "точка на границе квадрата среза (границы включены)",
    bad_slice: "у среза нет корректного bbox [W, S, E, N]",
    bad_shape: "ожидается [долгота, широта] или {lon, lat}",
    not_number: "координата должна быть числом",
    not_finite: "координата должна быть конечным числом (NaN/Infinity не принимаются)",
    out_of_range: "долгота вне [-180, 180] или широта вне [-90, 90]",
    lon_lat_swapped: "похоже, перепутаны долгота и широта: ожидается порядок [долгота, широта]",
    other_city: "точка в квадрате другого города; точки между городами не переносятся",
    outside_bbox: "точка вне квадрата среза: объекты за его пределами в срез не входили",
  };
  const ALLOWED_KEYS = new Set(["id", "lon", "lat", "category", "kind"]);
  const num = (v) => typeof v === "number";
  const validBbox = (b) => Array.isArray(b) && b.length === 4 && b.every((x) => num(x) && Number.isFinite(x)) &&
    -180 <= b[0] && b[0] < b[2] && b[2] <= 180 && -90 <= b[1] && b[1] < b[3] && b[3] <= 90;
  const within = (b, lon, lat, inc) => inc ? b[0] <= lon && lon <= b[2] && b[1] <= lat && lat <= b[3]
    : b[0] < lon && lon < b[2] && b[1] < lat && lat < b[3];
  const res = (code, ok = false, point = null, onEdge = false) => ({ ok, code, message: MESSAGES[code], point, on_edge: onEdge });

  function checkPoint(slice, point, otherSlices) {
    const b = slice && slice.bbox;
    if (!validBbox(b)) return res("bad_slice");
    const inc = slice.edges_inclusive === true;
    let lon, lat;
    if (point !== null && typeof point === "object" && !Array.isArray(point)) {
      const keys = Object.keys(point);
      if (keys.some((k) => !ALLOWED_KEYS.has(k)) || !("lon" in point) || !("lat" in point)) return res("bad_shape");
      ({ lon, lat } = point);
    } else if (Array.isArray(point) && point.length === 2) {
      [lon, lat] = point;
    } else {
      return res("bad_shape");
    }
    if (!(num(lon) && num(lat))) return res("not_number");
    if (!(Number.isFinite(lon) && Number.isFinite(lat))) return res("not_finite");
    if (!(-180 <= lon && lon <= 180 && -90 <= lat && lat <= 90)) return res("out_of_range");
    if (within(b, lon, lat, inc)) {
      const edge = lon === b[0] || lon === b[2] || lat === b[1] || lat === b[3];
      return res(edge ? "on_edge" : "inside", true, [lon, lat], edge);
    }
    if (within(b, lat, lon, inc)) return res("lon_lat_swapped");
    for (const o of otherSlices || []) {
      const ob = o && o.bbox;
      if (validBbox(ob) && o.city_id !== slice.city_id && within(ob, lon, lat, o.edges_inclusive === true)) {
        return Object.assign(res("other_city"), { other_city_id: o.city_id });
      }
    }
    return res("outside_bbox");
  }

  const api = { checkPoint, MESSAGES };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.K03_POINT_CHECK = api;
})(typeof window !== "undefined" ? window : globalThis);
