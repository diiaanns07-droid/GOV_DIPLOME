/* Original light MapLibre shell + pinned city-plan-v2 / city-resilience-v1.
 * Only the adapter owns map/mode switching. Calculations remain in core/.
 * Training state and city planning state never share scores, budgets or objects.
 */
(function () {
  "use strict";
  const D = window.CITY_EVIDENCE, F = window.CITY_FACTS;
  const $g = (id) => document.getElementById(id);
  const el = (tag, attrs, text) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, v);
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  };
  const sv = (tag, attrs) => {
    const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, v);
    return e;
  };
  const EXT = { layers: [], tools: [], onCity: [], onTool: [], cards: [], onMap: [], onActive: [], onMode: [] };
  const S = { city: "shymkent", tool: "inactive" };
  // school: the short school-access case is the main view; the older v2 planner/resilience panel is the advanced mode.
  const G = { active: false, page: "plan", camera: null, boundMap: null, dataKey: null, pending: false, school: true };
  const PLUI = () => window.CITY_PLAN_UI;
  const RSUI = () => window.CITY_RESILIENCE_UI;
  const qaOf = (p) => F.qaOf ? F.qaOf(S.city, p) : [];
  const fmtM = (v) => v == null ? "нет данных" : Math.round(v).toLocaleString("ru-RU") + " м";
  const originalTitle = document.title;
  const originalBrand = document.querySelector(".brand-title").innerHTML;
  const originalSub = document.querySelector(".brand-sub").textContent;
  const panel = el("aside", { id: "gov-panel", "aria-label": "Городское планирование", hidden: "" });
  panel.innerHTML = `
    <div class="gov-heading"><span class="eyebrow">Городская лаборатория</span><h1 id="gov-city-title">Шымкент</h1>
      <p>Где новый объект принесёт больше пользы?</p>
      <div class="gov-cities" role="group" aria-label="Город планирования">
        <button data-city="shymkent" aria-pressed="true">Шымкент</button><button data-city="astana" aria-pressed="false">Астана</button>
      </div><div class="gov-scope">Открытые данные · участок ≈2×2 км</div>
    </div>
    <nav class="gov-tabs" aria-label="Разделы планирования">
      <button data-page="plan" aria-pressed="true">План</button><button data-page="resilience" aria-pressed="false">Устойчивость</button><button data-page="data" aria-pressed="false">Данные</button>
    </nav>
    <div id="gov-scroll">
      <section id="planCard" class="gov-card" hidden><h2>Ваш план развития</h2><div class="gov-quickstart"><b>Начните с примера</b><span>Загрузите демо-набор ниже или добавьте свои точки на карту.</span></div><div id="planBody"></div></section>
      <section id="resCard" class="gov-card" hidden><h2>Проверка устойчивости</h2><p>Сравните обычный план с тем, который лучше выдерживает ваши допущения о данных.</p><div id="resBody"></div></section>
      <section id="gov-data" class="gov-card"><h2>Что мы знаем о городе</h2><div id="gov-data-body"></div><div id="gov-selection" role="status"></div></section>
    </div>
    <div class="gov-bottom"><span class="gov-dot"></span><span id="gov-status" role="status" aria-live="polite">Выберите категорию и добавьте точки.</span></div>`;
  document.body.append(panel);
  const legend = el("div", { id: "gov-legend", hidden: "" });
  legend.innerHTML = `<b>Планирование по открытым данным</b><span><i class="gov-source-dot"></i>Запись источника</span><span><i class="gov-point-dot"></i>Контрольная точка</span><span><i class="gov-candidate-dot"></i>Проектный объект</span><small>Рамка — граница доступного среза. Расстояния по прямой, стоимости условные.</small>`;
  document.body.append(legend);
  const attribution = el("div", { id: "gov-attribution", hidden: "" });
  attribution.append(document.createTextNode("Данные: Overture Maps · OSM · Meta · TomTom · "), el("a", { href: "/govtech/core/attribution/ATTRIBUTION.md", target: "_blank", rel: "noopener" }, "Источники и лицензии"));
  document.body.append(attribution);
  const overlay = sv("svg", { id: "gov-overlay", "aria-hidden": "true" });
  const shapes = sv("g"), labels = sv("g"); overlay.append(shapes, labels); $g("map").append(overlay);
  const issues = F.evidenceProblems ? F.evidenceProblems(D, window.CITY_OBS) : [];

  function setPage(page) {
    if (!["plan", "resilience", "data"].includes(page)) return;
    G.page = page; panel.dataset.page = page;
    panel.querySelectorAll("[data-page]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.page === page)));
    $g("gov-scroll").scrollTop = 0;
  }
  panel.querySelectorAll("[data-page]").forEach((b) => b.addEventListener("click", () => setPage(b.dataset.page)));
  panel.querySelectorAll("[data-city]").forEach((b) => b.addEventListener("click", () => switchCity(b.dataset.city)));
  setPage("plan");

  function updateStatus() {
    const t = EXT.tools.find((x) => x.placing());
    $g("gov-status").textContent = t ? t.statusText().replace("Enter — центр", "Enter — центр участка") : "Школы и поликлиники · расчёт в браузере · без API-ключа";
    if (map) map.getCanvas().style.cursor = G.active && t ? "crosshair" : "";
    scheduleMap();
  }
  function dataPanel() {
    const c = D.cities[S.city], box = $g("gov-data-body"); box.replaceChildren();
    box.append(el("p", null, `Срез ${c.label}: ${c.places.length} записей. Overture ${c.release}. Это вторичные данные, не официальный реестр и не весь город.`));
    box.append(el("p", { class: "muted" }, "Исходные записи не доказывают вместимость или доступность учреждения. QA отмечает сомнения, а не закрытие. Веса точек — ваши приоритеты, не жители; результаты — не прогноз трафика."));
    const cat = PLUI()?.state.category || "school";
    const list = el("ul", { class: "gov-sources" });
    for (const p of c.places.filter((p) => p.group === cat)) {
      const b = el("button", { type: "button" }, `${qaOf(p).length ? "⚠ " : ""}${p.name || p.id}`);
      b.addEventListener("click", () => selectPlace(p.id)); const li = el("li"); li.append(b); list.append(li);
    }
    box.append(el("h3", null, "Записи выбранной категории"), list);
  }
  function selectPlace(id) {
    const p = D.cities[S.city].places.find((p) => p.id === id); if (!p) return;
    setPage("data"); const out = $g("gov-selection"); out.replaceChildren();
    out.append(el("h3", null, p.name || "Без названия"), el("p", { class: "gov-record-id" }, p.id));
    out.append(el("p", null, `Координаты: ${p.lon}, ${p.lat}. Источник: ${(p.sources || []).map((x) => x.dataset || "не указан").join(", ") || "не указан"}.`));
    for (const q of qaOf(p)) out.append(el("p", { class: "warn" }, q.text || q.reason || q.code));
    out.append(el("p", { class: "muted" }, "Запись источника, не подтверждённый на месте объект. Отсутствие QA-меток не означает проверку."));
    out.scrollIntoView({ block: "nearest" });
  }
  function switchCity(city) {
    if (!D.cities[city] || city === S.city) return;
    PLUI()?.flush();
    for (const f of EXT.onCity) f(city, true);
    S.city = city; G.dataKey = null;
    for (const t of EXT.tools) t.stop();
    panel.querySelectorAll("[data-city]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.city === city)));
    $g("gov-city-title").textContent = D.cities[city].label;
    document.querySelector(".brand-sub").textContent = D.cities[city].label + " · городское планирование";
    document.title = D.cities[city].label + " · Городская лаборатория";
    $g("gov-selection").replaceChildren();
    for (const f of EXT.cards) f();
    dataPanel(); fitSlice(); renderMap(); updateStatus();
  }
  function fitSlice() {
    if (!G.active || !mapReady) return;
    const b = D.cities[S.city].bbox, mobile = innerWidth < 761;
    const pad = mobile ? (G.school ? { top: 250, left: 14, right: 54, bottom: Math.round(104 + innerHeight * .3) + 8 } : { top: 95, left: 20, right: 65, bottom: innerHeight * .5 })
      : G.school ? { top: 200, left: 270, right: 480, bottom: 110 } : { top: 130, left: 495, right: 95, bottom: 65 };
    map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: pad, maxZoom: 15.8, pitch: state.threeD ? 52 : 0, bearing: state.threeD ? -16 : 0, duration: 650 * motion() });
  }
  function modeLayers() {
    if (!mapReady) return;
    for (const id of ["district-fill", "district-outline", "district-selected"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", G.active ? "none" : "visible");
    for (const { el: marker } of markers) marker.style.display = G.active ? "none" : "";
    for (const id of ["gov-area", "gov-boundary"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", G.active ? "visible" : "none");
    if (map.getLayer("gov-sources")) map.setLayoutProperty("gov-sources", "visibility", G.active && !G.school ? "visible" : "none");
    overlay.style.display = G.active && !G.school ? "block" : "none";
    for (const f of EXT.onMode) f(G.active, G.school);
    if (G.active) popup?.remove();
  }
  function scheduleMap() {
    if (G.pending) return; G.pending = true;
    requestAnimationFrame(() => { G.pending = false; renderMap(); });
  }
  function renderMap() {
    if (!G.active || !mapReady || !map.getSource("gov-records")) return;
    const cat = PLUI()?.state.category || "school", key = S.city + "|" + cat;
    if (G.dataKey !== key) {
      G.dataKey = key;
      const c = D.cities[S.city], [w, s, e, n] = c.bbox;
      map.getSource("gov-box").setData({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[w,s],[e,s],[e,n],[w,n],[w,s]]] } });
      map.getSource("gov-records").setData({ type: "FeatureCollection", features: c.places.filter((p) => p.group === cat).map((p) => ({ type: "Feature", properties: { id: p.id, name: p.name || p.id, qa: qaOf(p).length > 0 }, geometry: { type: "Point", coordinates: [p.lon, p.lat] } })) });
      dataPanel();
    }
    shapes.replaceChildren(); labels.replaceChildren();
    for (const f of EXT.layers) f(shapes, labels);
  }
  function onMapReady() {
    if (!mapReady) return;
    if (G.boundMap !== map) {
      G.boundMap = map; G.dataKey = null;
      map.addSource("gov-records", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addSource("gov-box", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "gov-area", type: "fill", source: "gov-box", paint: { "fill-color": "#176b4a", "fill-opacity": .035 } });
      map.addLayer({ id: "gov-boundary", type: "line", source: "gov-box", paint: { "line-color": "#176b4a", "line-width": 2, "line-dasharray": [3, 3] } });
      map.addLayer({ id: "gov-sources", type: "circle", source: "gov-records", paint: { "circle-radius": 6, "circle-color": ["case", ["get", "qa"], "#b07823", "#176b4a"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      map.on("move", scheduleMap);
      map.on("resize", () => { scheduleMap(); if (G.active) fitSlice(); });
      map.on("click", (event) => {
        if (!G.active || G.school) return;
        const tool = EXT.tools.find((t) => t.placing());
        if (tool) { tool.place([event.lngLat.lng, event.lngLat.lat]); return; }
        const hit = map.queryRenderedFeatures(event.point, { layers: ["gov-sources"] })[0];
        if (hit) selectPlace(hit.properties.id);
      });
      map.getCanvas().addEventListener("keydown", (event) => {
        if (!G.active || G.school) return;
        if (event.key === "Escape") { for (const t of EXT.tools) t.stop(); updateStatus(); }
        if (event.key === "Enter") {
          const tool = EXT.tools.find((t) => t.placing());
          if (tool) {
            event.preventDefault();
            // A deterministic keyboard placement inside the known slice, independent of
            // camera padding/orientation. Pointer placement still uses the clicked coordinates.
            const [w, s, e, n] = D.cities[S.city].bbox;
            tool.place([(w + e) / 2, (s + n) / 2]);
          }
        }
      });
    }
    for (const f of EXT.onMap) f(map);
    modeLayers(); if (G.active) { fitSlice(); renderMap(); }
  }
  function setActive(active) {
    if (issues.length && active) { toast("Данные планировщика не согласованы: " + issues.join("; ")); return; }
    if (G.active === active) return;
    PLUI()?.flush();
    if (active && mapReady) G.camera = { center: map.getCenter().toArray(), zoom: map.getZoom(), pitch: map.getPitch(), bearing: map.getBearing() };
    PLUI()?.cancelSearch(); RSUI()?.cancel();
    for (const t of EXT.tools) t.stop();
    G.active = active; S.tool = active ? "v2" : "inactive";
    document.body.classList.toggle("govtech-mode", active);
    panel.hidden = legend.hidden = attribution.hidden = !active;
    $g("govtech-toggle").textContent = active ? "Вернуться к симулятору" : "Городское планирование";
    $g("govtech-toggle").setAttribute("aria-pressed", String(active));
    $g("map").setAttribute("aria-label", active ? "3D-карта городского планирования" : "Интерактивная карта районов Астаны");
    $g("overview-map").setAttribute("aria-label", active ? "Показать участок планирования" : "Показать всю Астану");
    $g("overview-map").title = active ? "Весь участок" : "Вся Астана";
    document.querySelector(".brand-title").textContent = active ? "Городская лаборатория." : "Аким на 5 часов.";
    if (!active) document.querySelector(".brand-title").innerHTML = originalBrand;
    document.querySelector(".brand-sub").textContent = active ? D.cities[S.city].label + " · городское планирование" : originalSub;
    document.title = active ? D.cities[S.city].label + " · Городская лаборатория" : originalTitle;
    for (const f of EXT.onTool) f(S.tool);
    document.body.classList.toggle("sc-advanced", active && !G.school);
    for (const f of EXT.onActive) f(active);
    modeLayers();
    if (active) { closeDrawer(); state.tour = -1; renderTour(); dataPanel(); fitSlice(); renderMap(); updateStatus(); }
    else if (mapReady && G.camera) { map.jumpTo(G.camera); state.threeD = G.camera.pitch > 0; $g("toggle-3d").classList.toggle("active", state.threeD); $g("toggle-3d").setAttribute("aria-pressed", String(state.threeD)); }
    if (active && !G.school) panel.querySelector('[data-city="' + S.city + '"]').focus();
  }
  // Switch between the main school-access case and the advanced v2 planner (same map, same city, separate state).
  function setSchool(on) {
    if (G.school === !!on) return;
    PLUI()?.flush(); PLUI()?.cancelSearch(); RSUI()?.cancel();
    for (const t of EXT.tools) t.stop();
    G.school = !!on;
    document.body.classList.toggle("sc-advanced", G.active && !G.school);
    G.dataKey = null; modeLayers(); fitSlice(); renderMap(); updateStatus();
    if (G.active && !G.school) panel.querySelector('[data-city="' + S.city + '"]').focus();
  }
  $g("govtech-toggle").addEventListener("click", () => setActive(!G.active));
  $g("overview-map").addEventListener("click", (e) => { if (G.active) { e.stopImmediatePropagation(); fitSlice(); } }, true);
  $g("toggle-3d").addEventListener("click", (e) => {
    if (!G.active) return;
    e.stopImmediatePropagation();
    state.threeD = !state.threeD;
    $g("toggle-3d").classList.toggle("active", state.threeD);
    $g("toggle-3d").setAttribute("aria-pressed", String(state.threeD));
    if (mapReady) {
      const [w, s, east, n] = D.cities[S.city].bbox;
      map.easeTo({ center: [(w + east) / 2, (s + n) / 2], pitch: state.threeD ? 52 : 0,
        zoom: state.threeD ? Math.max(15.5, map.getZoom()) : map.getZoom(), duration: 650 * motion() });
    }
  }, true);
  // Preserve the original map and its 3D/zoom controls; expose only the UI seam expected by pinned modules.
  window.CITY_APP = { state: S, switchCity, setTool: () => setActive(true), ui: { el, sv, $: $g, D, F, EXT,
    toScreen: (lon, lat) => { const p = map.project([lon, lat]); return [p.x, p.y]; }, renderMap: scheduleMap, updateStatus, qaOf, selectPlace, fmtM, stopV1: () => {} } };
  const back = el("button", { type: "button", class: "gov-back", id: "gov-back-school" }, "← Доступность школ");
  back.addEventListener("click", () => setSchool(true));
  panel.querySelector(".gov-heading").prepend(back);
  window.GOVTECH = { get active() { return G.active; }, get school() { return G.school; }, setActive, setPage, switchCity, setSchool, fitSlice, onMapReady,
    get map() { return mapReady ? map : null; }, EXT, state: S };
  if (mapReady) onMapReady();
})();
