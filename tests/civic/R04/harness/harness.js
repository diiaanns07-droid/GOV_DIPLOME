/* R04 test stand: what R01 is expected to provide — api.request with cookies + X-CSRF-Token, one map, a root element.
 * ?nomap=1 mounts without a map. ?latemap=1 passes a getter that returns the map only after window.__mapReady = true
 * (as R01 currentMap() does before the map has loaded). Counters of map listeners let tests check that destroy/close remove them.
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
  function mountWith(map) {
    window.__editor = window.CivicEditor.mount({
      root: document.getElementById("panel"), map, api,
      onPublished: (item, info) => window.__published.push({ item, info }),
    });
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
  mountWith(map);
})();
