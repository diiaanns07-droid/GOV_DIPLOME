/* R03 stand bootstrap. Query parameters (all optional):
 *   basemap=offline     skip OpenFreeMap and use the honest plain fallback
 *   delay=ms            mock latency (default 80)
 *   fail=list|card|all  first request of that kind answers 500
 *   empty=1             server has no published objects
 *   hostile=1           add malformed/hostile records (tests)
 *   today=YYYY-MM-DD    fixed "today" for screenshots and tests
 *   objects=URL         R12: load records from this civic-v1 file instead of the fixtures (e.g. the R05 demo slice)
 *   snapped=URL         R12: demo_snapped.json for the map module (off by default)
 *   streets=URL         R12: GeoJSON of OSM graph edges drawn as a plain street backdrop (no OpenFreeMap in the cloud)
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
  const real0 = q.get("api") === "real";
  const [objs, hist, hostile] = real0 ? [{ items: [] }, { history: {} }, { items: [] }] : await Promise.all([
    get(q.get("objects") || "/tests/civic/R12/map/fixtures/objects.json"),
    get("/tests/civic/R12/map/fixtures/history.json"),
    q.get("hostile") ? get("/tests/civic/R12/map/fixtures/hostile.json") : Promise.resolve({ items: [] }),
  ]);
  // extra=format: test-only fixture for money/basis/source formatting (labelled as a fixture).
  if (!real0 && q.get("extra") === "format") hostile.items = hostile.items.concat((await get("/tests/civic/R12/map/fixtures/format.json")).items);
  const fail = q.get("fail") || "";
  // api=real: same-origin /api/civic/v1 (R02 read-only harness); otherwise the contract mock.
  const real = q.get("api") === "real";
  const api = real ? window.R03CreateFetchApi("/api/civic/v1") : window.R03CreateMockApi({
    items: q.get("empty") ? [] : objs.items.concat(hostile.items),
    history: hist.history,
    delay: Number(q.get("delay") || 80),
    failList: fail === "list" || fail === "all" ? 1 : 0,
    failCard: fail === "card" || fail === "all" ? 1 : 0,
    leakDrafts: q.get("leak") === "1",
    // server-side page cap (R02: 100); small by default so paging stays exercised
    maxPage: Number(q.get("maxpage") || 5),
  });

  if (real) document.getElementById("stand-flag").textContent = "СТЕНД · R02 CivicService (read-only) · без оболочки R01";
  const stand = { api, instance: null, map: null, mounts: 0, destroys: 0, basemap: "pending", feedback: [], selects: [], data: [] };
  window.__stand = stand;

  // host=r01: imitate the R01 shell panel (positioned host + own scroll), module embedded in a slot.
  let mountRoot = document.getElementById("civic-public");
  if (q.get("host") === "r01") {
    const panel = document.createElement("div");
    panel.className = "stand-host-panel";
    const head = document.createElement("header");
    head.className = "stand-host-head";
    head.textContent = "Что меняется в городе (шапка хоста R01)";
    const scroll = document.createElement("div");
    scroll.className = "stand-host-scroll";
    const slot = document.createElement("div");
    slot.id = "civic-map-root";
    scroll.append(slot);
    panel.append(head, scroll);
    mountRoot.replaceWith(panel);
    mountRoot = slot;
  }
  function mount() {
    stand.instance = window.CivicMap.mount({
      root: mountRoot,
      map: stand.map,
      api,
      now,
      permalink: q.get("permalink") === "1",
      persistFilters: q.get("persist") !== "0",
      fitOnLoad: q.get("fit") !== "0",
      // R12: привязка демо-линий (по умолчанию выключена, чтобы старые проверки шли на исходной геометрии).
      snappedUrl: q.get("snapped") ? q.get("snapped") : false,
      onSelect: (obj, meta) => stand.selects.push({ id: obj && obj.id, source: meta.source }),
      onData: (items) => stand.data.push(items),
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
  map.once("load", async () => {
    if (q.get("streets")) {
      // Подложка-заменитель: настоящие оси улиц OSM (рёбра графа), чтобы на скриншоте было видно, идёт ли линия по улице.
      try {
        map.addSource("stand-streets", { type: "geojson", data: await get(q.get("streets")) });
        map.addLayer({ id: "stand-streets", type: "line", source: "stand-streets", layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": ["match", ["get", "g"], "road", "#b9c2b8", "service", "#d3d9d1", "#dfe4dc"],
            "line-width": ["interpolate", ["linear"], ["zoom"], 13, ["match", ["get", "g"], "road", 2, 1], 17, ["match", ["get", "g"], "road", 14, "service", 6, 2.5]] } });
      } catch (e) { console.warn("stand streets:", e.message); }
    }
    stand.map = map;
    stand.basemap = fallback ? "offline-fallback" : "openfreemap";
    if (fallback) say(q.get("streets") ? "Подложка OpenFreeMap недоступна: показаны только оси улиц OSM, без домов и 3D-зданий."
      : "Подложка OpenFreeMap недоступна: простой фон без улиц и 3D-зданий. Объекты и карточки работают.");
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
