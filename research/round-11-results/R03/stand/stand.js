/* R03 stand bootstrap. Query parameters (all optional):
 *   basemap=offline     skip OpenFreeMap and use the honest plain fallback
 *   delay=ms            mock latency (default 80)
 *   fail=list|card|all  first request of that kind answers 500
 *   empty=1             server has no published objects
 *   hostile=1           add malformed/hostile records (tests)
 *   today=YYYY-MM-DD    fixed "today" for screenshots and tests
 *   mobile tools: none; the page is responsive via CSS.
 */
(async function () {
  "use strict";
  const q = new URLSearchParams(location.search);
  const status = document.getElementById("stand-status");
  const say = (text) => { status.textContent = text; status.classList.toggle("hidden", !text); };
  const OFFLINE_STYLE = { version: 8, sources: {}, layers: [{ id: "offline-bg", type: "background", paint: { "background-color": "#eef1ea" } }] };
  const fixed = q.get("today");
  const now = fixed ? () => new Date(fixed + "T12:00:00") : () => new Date();

  const get = (p) => fetch(p).then((r) => { if (!r.ok) throw new Error(p + " " + r.status); return r.json(); });
  const [objs, hist, hostile] = await Promise.all([
    get("/tests/civic/R03/fixtures/objects.json"),
    get("/tests/civic/R03/fixtures/history.json"),
    q.get("hostile") ? get("/tests/civic/R03/fixtures/hostile.json") : Promise.resolve({ items: [] }),
  ]);
  const fail = q.get("fail") || "";
  const api = window.R03CreateMockApi({
    items: q.get("empty") ? [] : objs.items.concat(hostile.items),
    history: hist.history,
    delay: Number(q.get("delay") || 80),
    failList: fail === "list" || fail === "all" ? 1 : 0,
    failCard: fail === "card" || fail === "all" ? 1 : 0,
    leakDrafts: q.get("leak") === "1",
  });

  const stand = { api, instance: null, map: null, mounts: 0, destroys: 0, basemap: "pending", feedback: [], selects: [] };
  window.__stand = stand;

  function mount() {
    stand.instance = window.CivicMap.mount({
      root: document.getElementById("civic-public"),
      map: stand.map,
      api,
      now,
      permalink: q.get("permalink") === "1",
      persistFilters: q.get("persist") !== "0",
      fitOnLoad: q.get("fit") !== "0",
      onSelect: (obj, meta) => stand.selects.push({ id: obj && obj.id, source: meta.source }),
      onFeedback: (payload) => { stand.feedback.push(payload); say("onFeedback вызван для «" + payload.title + "» — форму обращения подключает R06/R01."); },
    });
    stand.mounts++;
    return stand.instance;
  }
  stand.mount = mount;
  stand.destroy = () => { if (stand.instance) { stand.instance.destroy(); stand.instance = null; stand.destroys++; } };
  document.getElementById("dev-refresh").onclick = () => stand.instance && stand.instance.refresh();
  document.getElementById("dev-remount").onclick = () => { stand.destroy(); mount(); };
  document.getElementById("dev-destroy").onclick = () => stand.destroy();

  if (!window.maplibregl) { stand.basemap = "no-maplibre"; say("MapLibre не загрузился: список и карточки работают без карты."); mount(); return; }
  let map;
  try {
    map = new maplibregl.Map({
      container: "map",
      style: q.get("basemap") === "offline" ? OFFLINE_STYLE : "https://tiles.openfreemap.org/styles/liberty",
      center: [71.43, 51.135],
      zoom: 11.4,
      maxPitch: 65,
      minZoom: 8,
      maxZoom: 18,
      attributionControl: false,
      renderWorldCopies: false,
    });
  } catch (e) {
    stand.basemap = "no-webgl"; say("WebGL недоступен: список и карточки работают без карты."); mount(); return;
  }
  stand.rawMap = map;
  map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "MapLibre" }), "bottom-right");
  let fallback = q.get("basemap") === "offline";
  map.on("error", (e) => {
    // Same honest fallback as web/map.js: plain background, no streets, no 3D buildings.
    if (!map.isStyleLoaded() && !fallback) { fallback = true; map.setStyle(OFFLINE_STYLE); }
    console.warn("map:", e && e.error && e.error.message);
  });
  map.once("load", () => {
    stand.map = map;
    stand.basemap = fallback ? "offline-fallback" : "openfreemap";
    if (fallback) say("Подложка OpenFreeMap недоступна: простой фон без улиц и 3D-зданий. Объекты и карточки работают.");
    mount();
  });
  const tilt = document.getElementById("toggle-3d");
  tilt.onclick = () => {
    const on = map.getPitch() < 5;
    map.easeTo({ pitch: on ? 50 : 0, bearing: on ? -15 : 0, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 600 });
    tilt.setAttribute("aria-pressed", String(on));
    tilt.classList.toggle("active", on);
    if (on && fallback) say("3D-здания появятся, когда загрузится подложка OpenFreeMap. Сейчас наклоняется только камера.");
  };
  document.getElementById("zoom-in").onclick = () => map.zoomIn();
  document.getElementById("zoom-out").onclick = () => map.zoomOut();
  document.getElementById("overview-map").onclick = () => map.fitBounds([[71.33, 51.06], [71.55, 51.2]], { padding: 60, duration: 0 });
})();
