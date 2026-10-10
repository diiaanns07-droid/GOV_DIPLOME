/* R04 test stand: what R01 is expected to provide — api.request with cookies + X-CSRF-Token, one map, a root element.
 * ?nomap=1 mounts without a map. ?latemap=1 passes a getter that returns the map only after window.__mapReady = true
 * (as R01 currentMap() does before the map has loaded); ?latemap=never never returns it (window.__getterCalls counts
 * look-ups). ?open=<id> calls openObject(id) right after mount, before the editor's GET /session has answered
 * (window.__openDone gets the result). Counters of map listeners let tests check that destroy/close remove them.
 * R12: the editor gets a TEST geo client (СИНТЕТИКА, не улицы OSM): one straight «улица Стендовая» along lat 51.13 with
 * a vertex every 0.002° lon, one stop «Стенд» near [71.435, 51.1302], one yard [71.425..71.428]×[51.131..51.133].
 * ?geo=off -> geo:false; ?geo=fail -> every call answers 404 (route not wired); ?geodelay=ms -> slower answers.
 * window.__geoCalls logs the calls. The real contract is tested in tests/civic/R12/test_civic_geo.py and e2e_r12_real.
 */
(function () {
  "use strict";
  const params = new URLSearchParams(location.search);
  let csrf = null;
  const api = {
    async request(method, path, body, opts) {
      const headers = { Accept: "application/json" };
      if (opts && opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;
      const res = await fetch("/api/civic/v1" + path, { method, headers, credentials: "same-origin", body: body === undefined ? undefined : JSON.stringify(body) });
      let json = null;
      try { json = await res.json(); } catch (e) { json = null; }
      if (!json || typeof json !== "object" || typeof json.ok !== "boolean") { const e = new Error("HTTP " + res.status); e.status = res.status; throw e; }
      if (!json.ok) {
        const er = json.error || {};
        const e = new Error(er.message || "error");
        Object.assign(e, { status: res.status, code: er.code, fields: er.fields });
        throw e;
      }
      return json.data;
    },
    setCsrfToken(t) { csrf = t || null; },
  };
  window.__published = [];
  window.__toolEvents = [];
  window.__mapCounts = {};
  document.addEventListener("civic-editor:tool", (e) => window.__toolEvents.push(e.detail));
  // ---- R12 test geo client (synthetic) ----
  window.__geoCalls = [];
  const STREET_LAT = 51.13, M = Math.PI / 180 * 6371008.8;
  const dist = (a, b) => Math.hypot((a[0] - b[0]) * M * Math.cos(51.13 * Math.PI / 180), (a[1] - b[1]) * M);
  const wait = () => new Promise((r) => setTimeout(r, Number(params.get("geodelay") || 30)));
  const fail400 = (msg, code) => Object.assign(new Error(msg), { status: 400, code });
  async function geoCall(name, args, fn) {
    window.__geoCalls.push({ name, args });
    await wait();
    if (params.get("geo") === "fail") throw Object.assign(new Error("HTTP 404"), { status: 404 });
    return fn();
  }
  const mockGeo = {
    snap: (p, kind) => geoCall("snap", [p, kind], () => {
      if (dist(p, [p[0], STREET_LAT]) > 60) throw fail400("Рядом нет улицы (дальше 60 м). Нажмите на саму улицу.", "not_on_street");
      return { point: [p[0], STREET_LAT], edge_id: "stand-e1", distance_m: dist(p, [p[0], STREET_LAT]), street_ru: "улица Стендовая", label_ru: "Участок: улица Стендовая" };
    }),
    segment: (a, b, kind) => geoCall("segment", [a, b, kind], () => {
      if (dist(b, [b[0], STREET_LAT]) > 60) throw fail400("Точка дальше 60 м от улицы. Нажмите ближе к улице.", "not_on_street");
      const [x0, x1] = a[0] <= b[0] ? [a[0], b[0]] : [b[0], a[0]];
      const coords = [[x0, STREET_LAT]];
      for (let x = Math.ceil(x0 / 0.002) * 0.002; x < x1; x += 0.002) if (x > x0) coords.push([+x.toFixed(6), STREET_LAT]);
      coords.push([x1, STREET_LAT]);
      if (a[0] > b[0]) coords.reverse();
      if (coords.length < 3) coords.splice(1, 0, [+((x0 + x1) / 2).toFixed(6), STREET_LAT]);
      return { geometry: { type: "LineString", coordinates: coords }, length_m: dist(coords[0], coords[coords.length - 1]),
        names: ["улица Стендовая"], street_ru: "улица Стендовая", same_street: true, edge_ids: ["stand-e1"] };
    }),
    near: (p) => geoCall("near", [p], () => ({ objects: dist(p, [71.435, 51.1302]) < 60
      ? [{ id: "stand-node-1", kind: "bus_stop", label_ru: "Остановка «Стенд»", point: [71.435, 51.1302], distance_m: dist(p, [71.435, 51.1302]) }] : [] })),
    yard: (p) => geoCall("yard", [p], () => (p[0] > 71.425 && p[0] < 71.428 && p[1] > 51.131 && p[1] < 51.133
      ? { yard: { id: "yard-stand", label_ru: "Двор — улица Стендовая", geometry: { type: "Polygon",
        coordinates: [[[71.425, 51.131], [71.428, 51.131], [71.428, 51.133], [71.425, 51.133], [71.425, 51.131]]] } }, reason: null }
      : { yard: null, reason: "not_in_yard" })),
  };
  function mountWith(map) {
    window.__editor = window.CivicEditor.mount({
      root: document.getElementById("panel"), map, api,
      // ?geo=real&geoPrefix=<url> — настоящий engine/civic_geo (tests/civic/R12/geo_api_server.py)
      geo: params.get("geo") === "off" ? false : params.get("geo") === "real" ? undefined : mockGeo,
      geoPrefix: params.get("geoPrefix") || undefined,
      onPublished: (item, info) => window.__published.push({ item, info }),
    });
    if (params.get("open")) { window.__openDone = undefined; window.__editor.openObject(params.get("open")).then((r) => { window.__openDone = r; }); }
  }
  window.__remount = () => { if (window.__editor) window.__editor.destroy(); mountWith(window.__map || null); };
  if (params.get("nomap") === "1" || !window.maplibregl) { window.__mapState = "none"; mountWith(null); return; }
  let map;
  try {
    map = new maplibregl.Map({
      container: "map", center: [71.43, 51.13], zoom: 12, attributionControl: false,
      style: { version: 8, sources: {}, layers: [{ id: "stand-bg", type: "background", paint: { "background-color": "#e9efe4" } }] },
    });
  } catch (e) { window.__mapState = "error: " + e.message; mountWith(null); return; }
  const on = map.on.bind(map), off = map.off.bind(map);
  map.on = function (type, ...rest) { if (typeof rest[0] === "function") window.__mapCounts[type] = (window.__mapCounts[type] || 0) + 1; return on(type, ...rest); };
  map.off = function (type, ...rest) { if (typeof rest[0] === "function") window.__mapCounts[type] = (window.__mapCounts[type] || 0) - 1; return off(type, ...rest); };
  window.__map = map;
  map.once("load", () => { window.__mapState = "loaded"; });
  if (params.get("latemap") === "1") { window.__mapReady = false; mountWith(() => (window.__mapReady ? map : null)); return; }
  if (params.get("latemap") === "never") { window.__getterCalls = 0; mountWith(() => { window.__getterCalls++; return null; }); return; }
  mountWith(map);
})();
