/*
 * Birge · стиль подложки (R01, раунд 14, решение владельца 11 окт): одна палитра для онлайн-слоя (web/map.js, OpenFreeMap)
 * и офлайн-стиля Codex (web/civic/offline/: style.json + boot.js buildingLayer).
 *
 *  - здания — тёплые светло-серые, цвет по высоте: 0 м #ECE9E2 → 60 м #DEDAD2 → 150 м+ #D2CDC4; боковые грани темнее
 *    (fill-extrusion-vertical-gradient), мягкий свет;
 *  - ориентиры (Хан Шатыр, Бәйтерек, Ақорда, Хазрет Султан, Дворец мира и согласия, Нұр Әлем/ЭКСПО) — «белый макет»
 *    (поправка П1): тон чуть светлее соседних зданий (#F6F4EF) и спокойная подпись ru/kk, без отдельной краски;
 *    центры, радиусы и названия — из web/civic/build3d/data/landmarks.json (R05, один источник с поиском); где стоит
 *    3D-модель ориентира (build3d.js, setHiddenLandmarks), здание подложки не рисуется;
 *  - парки #DFECD5, вода #C3DFEC; насыщенного зелёного на подложке нет — зелёный значит «исправлено/проверено»
 *    (research/round-14/categories_v2.json → heat_states; токены ui-kit R11 --fixed).
 * MapLibre не читает CSS-переменные, поэтому значения здесь; те же значения переданы R11 как токены --map-*.
 */
(function () {
  "use strict";

  const palette = {
    building0: "#ECE9E2", building60: "#DEDAD2", building150: "#D2CDC4",
    buildingOutline: "#D9D4CB", landmark: "#F6F4EF", landmarkText: "#4B5752",
    park: "#DFECD5", water: "#C3DFEC", land: "#F4F3EF", landuse: "#EEECE6",
  };
  // Мягкий тёплый свет сбоку-сверху: боковые грани зданий чуть темнее крыш.
  const light = { anchor: "viewport", color: "#fffaf0", intensity: 0.32, position: [1.2, 200, 40] };

  const buildingColor = (height) =>
    ["interpolate", ["linear"], height, 0, palette.building0, 60, palette.building60, 150, palette.building150];

  // Ориентиры: опорный центр [lon, lat] и допуск (м): здание выше 15 м, которое ближе допуска к центру (обычно центр внутри
  // здания — расстояние 0), — ориентир. Выражение "distance" (MapLibre 5): "within" полигоны зданий не проверяет.
  // Центры, радиусы и названия — из landmarks.json R05 (applyLandmarksFile: центры по кольцам дорожек OSM); значения ниже —
  // запасные, пока файл не пришёл. Без файла центр уточняется по POI самой подложки (refine): то же имя ближе 500 м.
  // Дворец мира и согласия — узел OSM 5009488810 (data/civic/astana/osm-walking).
  const landmarks = [
    { id: "khan-shatyr", center: [71.4030, 51.1323], radius: 60, ru: "Хан Шатыр", kk: "Хан Шатыр",
      match: /хан[\s-]*шатыр|khan[\s-]*shatyr/i },
    { id: "baiterek", center: [71.4303, 51.1283], radius: 40, ru: "Байтерек", kk: "Бәйтерек",
      match: /^(монумент\s+)?б[аә]йтерек$|^baiterek|^bayterek/i },
    { id: "akorda", center: [71.4463, 51.1257], radius: 60, ru: "Ақорда", kk: "Ақорда",
      match: /^[аa][кқk][оo]рд[аa]|ak[\s-]?orda|резиденция президента/i },
    { id: "hazrat-sultan", center: [71.4718, 51.1254], radius: 60, ru: "Мечеть Хазрет Султан", kk: "Әзірет Сұлтан мешіті",
      match: /хазрет|хазірет|әзірет|hazrat|hazret/i },
    { id: "palace-peace", center: [71.4635865, 51.1231163], radius: 40, ru: "Дворец мира и согласия", kk: "Бейбітшілік және келісім сарайы",
      match: /мира и согласия|бейбітшілік және келісім|peace and (reconciliation|accord)/i },
    { id: "nur-alem", center: [71.4158, 51.0889], radius: 50, ru: "Нур Алем · ЭКСПО", kk: "Нұр Әлем · ЭКСПО",
      match: /н[уұ]р[\s-]*[аә]л[еә]м|nur[\s-]*alem/i },
  ];
  const LANDMARK_MIN_HEIGHT = 15;  // ларьки и навесы рядом с ориентиром не подсвечиваются

  // Здание — ориентир, если оно ближе допуска к одному из центров.
  const near = (list) => ["any", ...list.map((l) => ["<", ["distance", { type: "Point", coordinates: l.center }], l.radius])];
  const landmarkNear = () => near(landmarks);
  // Ориентиры, которые сейчас рисует 3D-модель R05 (build3d.js, владелец 19 окт): их здания подложки не рисуем, иначе
  // они прорастают сквозь модель. Список помнится и при смене стиля (install применяет его заново).
  let hiddenLandmarks = new Set();
  const landmarkPoints = () => ({
    type: "FeatureCollection",
    features: landmarks.map((l) => ({ type: "Feature", properties: { id: l.id, name_ru: l.ru, name_kk: l.kk },
      geometry: { type: "Point", coordinates: l.center } })),
  });

  // POI подложки (владелец, читаемость карты п. 4): коммерческие точки (магазины, отели, кафе, банки…) скрыты; остаются
  // ориентиры и культура, остановки и транспорт, школы и детсады, больницы. Значения kind (Protomaps, офлайн) и
  // class/subclass (OpenMapTiles, онлайн OpenFreeMap).
  const POI_KEEP = ["attraction", "monument", "memorial", "artwork", "museum", "theatre", "place_of_worship", "mosque",
    "church", "townhall", "town_hall", "stadium", "landmark", "castle", "viewpoint",
    "bus_stop", "bus_station", "bus", "station", "train_station", "railway", "tram_stop", "subway", "aerodrome", "airport",
    "school", "kindergarten", "university", "college", "hospital", "clinic"];
  const poiKeep = () => ["any", ...["kind", "class", "subclass"].map((k) => ["match", ["coalesce", ["get", k], ""], POI_KEEP, true, false])];
  function filterPois(map) {
    for (const layer of map.getStyle().layers || []) {
      if (layer.type !== "symbol" || !/^pois?$/.test(layer["source-layer"] || "")) continue;
      try { map.setFilter(layer.id, layer.filter ? ["all", layer.filter, poiKeep()] : poiKeep()); } catch (e) { /* фильтр старого вида */ }
    }
  }

  // Цвета слоёв подложки по смыслу слоя (OpenFreeMap liberty и офлайн-стиль): парки, вода, плоские здания, фон.
  const PARK = /park|wood|forest|grass|scrub|meadow|garden|nature|landcover|cemetery|pitch|golf|recreation|playground/i;
  function recolorBasemap(map) {
    for (const layer of map.getStyle().layers || []) {
      const id = layer.id;
      if (/^(akim|birge|civic|district|r0\d|r1\d|b3d|offline-(nura|city|bg))/.test(id) || layer.id === "offline-landuse") continue;
      try {
        if (layer.type === "background") map.setPaintProperty(id, "background-color", palette.land);
        else if (layer.type === "fill" && /water|ocean|lake|river|basin|reservoir/i.test(id)) map.setPaintProperty(id, "fill-color", palette.water);
        else if (layer.type === "line" && /water|river|canal|stream|drain/i.test(id)) map.setPaintProperty(id, "line-color", palette.water);
        else if (layer.type === "fill" && /^building|buildings-flat/.test(id)) {
          map.setPaintProperty(id, "fill-color", palette.building0);
          map.setPaintProperty(id, "fill-outline-color", palette.buildingOutline);
        } else if (layer.type === "fill" && PARK.test(id + " " + (layer["source-layer"] || ""))) {
          map.setPaintProperty(id, "fill-color", palette.park);
          if (layer.paint && "fill-outline-color" in layer.paint) map.setPaintProperty(id, "fill-outline-color", palette.park);
        }
      } catch (e) { /* слой без этого свойства — пропускаем */ }
    }
  }

  // Слой 3D-зданий akim-3d уже добавлен (онлайн — web/map.js, офлайн — BirgeOffline.buildingLayer): тёплая палитра,
  // ориентиры отдельным слоем с тем же источником (без двойной отрисовки: основной слой их исключает), подписи.
  const state = { map: null, base: null, refineLeft: 0 };
  function landmarkFilters(baseFilter, height) {
    const inside = landmarkNear();
    const tall = [">=", height, LANDMARK_MIN_HEIGHT];
    const base = baseFilter ? [baseFilter] : [];
    const shown = landmarks.filter((l) => !hiddenLandmarks.has(l.id));
    return {
      main: ["all", ...base, ["!", ["all", inside, tall]]],
      // Все ориентиры под моделями — слой ориентиров пуст (выражение "any" без условий MapLibre не принимает).
      landmark: shown.length ? ["all", ...base, near(shown), tall] : ["==", ["literal", 1], 0],
    };
  }
  // build3d.js R05: ids ориентиров, чьи модели сейчас на карте (пустой список — вернуть здания подложки).
  function setHiddenLandmarks(map, ids) {
    const next = new Set(Array.isArray(ids) ? ids : []);
    if (next.size === hiddenLandmarks.size && [...next].every((id) => hiddenLandmarks.has(id))) return;
    hiddenLandmarks = next;
    if (!map || state.map !== map || !state.base) return;
    try {
      if (map.getLayer("akim-3d-landmark")) map.setFilter("akim-3d-landmark", landmarkFilters(state.base.filter, state.base.height).landmark);
    } catch (e) { /* стиль меняется — install применит список заново */ }
  }
  function install(map) {
    if (!map || typeof map.getLayer !== "function") return false;
    try { map.setLight(light); } catch (e) { /* свет — украшение */ }
    recolorBasemap(map);
    filterPois(map);
    const layer = map.getLayer("akim-3d");
    if (!layer) return false;
    const spec = map.getStyle().layers.find((l) => l.id === "akim-3d");
    const height = spec.paint?.["fill-extrusion-height"];
    // Высота для цвета и порога — то же выражение, что у высоты на крупном масштабе (последний аргумент интерполяции).
    const h = Array.isArray(height) && height[0] === "interpolate" ? height[height.length - 1] : ["to-number", ["get", "render_height"], 4];
    state.map = map;
    state.base = { filter: spec.filter || null, height: h, spec };
    try {
      map.setPaintProperty("akim-3d", "fill-extrusion-color", buildingColor(h));
      map.setPaintProperty("akim-3d", "fill-extrusion-vertical-gradient", true);
      map.setPaintProperty("akim-3d", "fill-extrusion-opacity", 0.92);
    } catch (e) { console.warn("basemap: building paint", e); }
    const filters = landmarkFilters(state.base.filter, h);
    try {
      map.setFilter("akim-3d", filters.main);
      if (!map.getLayer("akim-3d-landmark")) {
        const style = map.getStyle().layers, i = style.findIndex((l) => l.id === "akim-3d");
        const before = style[i + 1]?.id;
        map.addLayer({ id: "akim-3d-landmark", type: "fill-extrusion", source: spec.source, "source-layer": spec["source-layer"],
          minzoom: spec.minzoom || 14, filter: filters.landmark,
          paint: { ...spec.paint, "fill-extrusion-color": palette.landmark, "fill-extrusion-vertical-gradient": true, "fill-extrusion-opacity": 0.95 } }, before);
      } else map.setFilter("akim-3d-landmark", filters.landmark);
    } catch (e) { console.warn("basemap: landmarks", e); }
    addLabels(map);
    state.refineLeft = 30;
    map.on("idle", refine);
    applyLandmarksFile(map);
    return true;
  }
  // Один источник центров и названий ориентиров с поиском (R05, поправка П1): web/civic/build3d/data/landmarks.json.
  // Пришёл файл — его центры, радиусы и подписи ru/kk (label, иначе name); уточнение по POI подложки больше не нужно.
  function applyLandmarksFile(map) {
    if (typeof fetch !== "function") return;
    fetch("/civic/build3d/data/landmarks.json", { headers: { Accept: "application/json" } }).then((r) => (r.ok ? r.json() : null)).then((data) => {
      const list = Array.isArray(data?.landmarks) ? data.landmarks : [];
      let changed = false;
      for (const l of landmarks) {
        const f = list.find((x) => x.id === l.id && Number.isFinite(x.lon) && Number.isFinite(x.lat));
        if (!f) continue;
        l.center = [f.lon, f.lat];
        if (Number.isFinite(f.radius_m)) l.radius = f.radius_m;
        const label = f.label || f.name;  // подпись на карте («Нур Алем · ЭКСПО»), иначе название
        if (label?.ru) l.ru = label.ru;
        if (label?.kk) l.kk = label.kk;
        l.refined = true;
        changed = true;
      }
      if (!changed || state.map !== map) return;
      const filters = landmarkFilters(state.base.filter, state.base.height);
      try {
        map.setFilter("akim-3d", filters.main);
        map.setFilter("akim-3d-landmark", filters.landmark);
        map.getSource("birge-landmarks")?.setData(landmarkPoints());
      } catch (e) { /* стиль сменился — центры применятся при следующей установке */ }
    }).catch(() => { /* нет файла — запасные центры и refine по POI */ });
  }
  const lang = () => (document.documentElement.lang === "kk" ? "kk" : "ru");
  function addLabels(map) {
    const style = map.getStyle();
    if (!style.glyphs) return;  // запасной фон без шрифтов: подписи не рисуем (иначе ошибка глифов)
    const font = (style.layers.find((l) => l.type === "symbol" && l.layout?.["text-font"])?.layout["text-font"]) || ["Noto Sans Regular"];
    try {
      if (!map.getSource("birge-landmarks")) map.addSource("birge-landmarks", { type: "geojson", data: landmarkPoints() });
      if (!map.getLayer("birge-landmark-label")) {
        map.addLayer({ id: "birge-landmark-label", type: "symbol", source: "birge-landmarks", minzoom: 12.5,
          layout: { "text-field": ["get", "name_" + lang()], "text-font": Array.isArray(font) ? font : ["Noto Sans Regular"],
            "text-size": ["interpolate", ["linear"], ["zoom"], 12.5, 12, 16, 15], "text-anchor": "top", "text-offset": [0, 0.8],
            "text-max-width": 9, "symbol-sort-key": 0 },
          paint: { "text-color": palette.landmarkText, "text-halo-color": "#ffffff", "text-halo-width": 1.6, "text-halo-blur": 0.4 } });
      }
    } catch (e) { console.warn("basemap: landmark labels", e); }
    window.addEventListener("birge:lang", () => {
      try { map.setLayoutProperty("birge-landmark-label", "text-field", ["get", "name_" + lang()]); } catch (e) { /* слой ушёл */ }
    });
  }
  // Уточнение центров по POI подложки: имя совпало и точка ближе 500 м к опорной — берём её (один раз на ориентир).
  const dist = (a, b) => Math.hypot((a[0] - b[0]) * 111320 * Math.cos((a[1] * Math.PI) / 180), (a[1] - b[1]) * 111320);
  function refine() {
    const map = state.map;
    if (!map || state.refineLeft-- <= 0) { map?.off("idle", refine); return; }
    if (map.getZoom() < 12) return;
    const src = state.base.spec.source;
    const layers = ["poi", "pois"];
    let changed = false;
    for (const sourceLayer of layers) {
      let feats = [];
      try { feats = map.querySourceFeatures(src, { sourceLayer }); } catch (e) { continue; }
      for (const l of landmarks) {
        if (l.refined) continue;
        let best = null;
        for (const f of feats) {
          if (f.geometry?.type !== "Point") continue;
          const p = f.properties || {};
          const name = [p["name:ru"], p["name:kk"], p.name, p["name:en"], p.name_int].filter(Boolean).join(" | ");
          if (!l.match.test(name)) continue;
          const d = dist(f.geometry.coordinates, l.center);
          if (d < 500 && (!best || d < best.d)) best = { d, at: f.geometry.coordinates };
        }
        if (best) { l.center = best.at; l.refined = true; changed = true; }
      }
    }
    if (!changed) return;
    const filters = landmarkFilters(state.base.filter, state.base.height);
    try {
      map.setFilter("akim-3d", filters.main);
      map.setFilter("akim-3d-landmark", filters.landmark);
      map.getSource("birge-landmarks")?.setData(landmarkPoints());
    } catch (e) { /* слои ушли со сменой стиля */ }
    if (landmarks.every((l) => l.refined)) map.off("idle", refine);
  }

  window.BirgeBasemapStyle = { palette, light, buildingColor, landmarks, landmarkNear, install, recolorBasemap, filterPois, POI_KEEP,
    setHiddenLandmarks };
})();
