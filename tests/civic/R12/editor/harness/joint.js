/* Joint stand: R03's public map module (pinned delivery, served from /r03-<variant>/) and the R04 editor on ONE map.
 * ?r03=pinned (R03 as delivered) | patched (with R04's proposed 2-line patch). window.__r03selects records R03 onSelect.
 */
(function () {
  "use strict";
  const params = new URLSearchParams(location.search);
  const variant = params.get("r03") === "patched" ? "patched" : "pinned";
  let csrf = null;
  const api = {
    async request(method, path, body, opts) {
      const headers = { Accept: "application/json" };
      if (opts && opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;
      const res = await fetch("/api/civic/v1" + path, { method, headers, credentials: "same-origin", body: body === undefined ? undefined : JSON.stringify(body), signal: opts && opts.signal });
      let json = null;
      try { json = await res.json(); } catch (e) { json = null; }
      if (!json || typeof json.ok !== "boolean") { const e = new Error("HTTP " + res.status); e.status = res.status; throw e; }
      if (!json.ok) { const er = json.error || {}; throw Object.assign(new Error(er.message || "error"), { status: res.status, code: er.code, fields: er.fields }); }
      return json.data;
    },
    setCsrfToken(t) { csrf = t || null; },
  };
  function load(src) {
    return new Promise((resolve, reject) => { const s = document.createElement("script"); s.src = src; s.onload = resolve; s.onerror = () => reject(new Error(src)); document.head.append(s); });
  }
  window.__r03selects = [];
  window.__toolEvents = [];
  document.addEventListener("civic-editor:tool", (e) => window.__toolEvents.push(e.detail));
  (async () => {
    const dir = "/r03-" + variant + "/";
    await load(dir + "civic-map-core.js");
    await load(dir + "civic-map.js");
    await load("/web/civic/editor/editor-core.js");
    await load("/web/civic/editor/editor.js");
    const map = new maplibregl.Map({
      container: "map", center: [71.43, 51.13], zoom: 13, attributionControl: false,
      style: { version: 8, sources: {}, layers: [{ id: "stand-bg", type: "background", paint: { "background-color": "#e9efe4" } }] },
    });
    window.__map = map;
    await new Promise((r) => map.once("load", r));
    window.__r03 = window.CivicMap.mount({ root: document.getElementById("r03root"), map, api, layout: "embedded",
      onSelect: (item, info) => window.__r03selects.push({ id: item && item.id, source: info && info.source }) });
    window.__editor = window.CivicEditor.mount({ root: document.getElementById("panel"), map, api, onPublished: () => {} });
    window.__variant = variant;
    window.__mapState = "loaded";
  })().catch((e) => { window.__mapState = "error: " + e.message; });
})();
