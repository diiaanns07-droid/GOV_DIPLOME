/* R03 · civic-v1 public map and object cards.
 * window.CivicMap.mount({root, map, api, onSelect, onFeedback}) -> {refresh, selectObject, destroy}
 * Uses the existing MapLibre instance (never creates a map), renders untrusted text
 * with textContent only, and removes every civic-r03-* layer, source and listener in destroy().
 * Requires civic-map-core.js (window.CivicMapCore) loaded first.
 */
(function () {
  "use strict";
  const C = window.CivicMapCore;
  const P = "civic-r03-";
  const SRC = P + "objects";
  const L = {
    areaFill: P + "area-fill",
    areaLine: P + "area-line",
    areaLineApprox: P + "area-line-approx",
    lineCasing: P + "line-casing",
    line: P + "line",
    lineApprox: P + "line-approx",
    synthLine: P + "synthetic-outline",
    selLine: P + "selected-line",
    pointHalo: P + "point-halo",
    pointSynth: P + "point-synthetic",
    point: P + "point",
    selPoint: P + "selected-point",
  };
  const BELOW_LABELS = [L.areaFill, L.areaLine, L.areaLineApprox, L.lineCasing, L.line, L.lineApprox, L.synthLine, L.selLine];
  const ON_TOP = [L.pointHalo, L.pointSynth, L.point, L.selPoint];
  const INTERACTIVE = [L.point, L.pointHalo, L.line, L.lineApprox, L.lineCasing, L.areaFill];
  const STORAGE_KEY = "civic-r03:filters:v1";
  const HASH_KEY = "civic-object";
  const SVGNS = "http://www.w3.org/2000/svg";
  const MOBILE_QUERY = "(max-width: 760px)";
  const MAX_PAGES = 20;
  const byMap = new WeakMap();

  // ---------- tiny DOM helpers (textContent only) ----------
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = String(v);
      else if (k === "style") for (const [sk, sv] of Object.entries(v)) e.style.setProperty(sk, sv);
      else e.setAttribute(k, v === true ? "" : String(v));
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    return e;
  }
  function svgIcon(paths, size) {
    const s = document.createElementNS(SVGNS, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    s.setAttribute("class", P + "icon");
    if (size) { s.setAttribute("width", size); s.setAttribute("height", size); }
    for (const d of paths) { const p = document.createElementNS(SVGNS, "path"); p.setAttribute("d", d); s.append(p); }
    return s;
  }
  const ICON = {
    back: ["M19 12H5", "m11 6-6 6 6 6"],
    pin: ["M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z", "M12 12.2a2.6 2.6 0 1 0 0-5.2 2.6 2.6 0 0 0 0 5.2z"],
    chat: ["M20 16h-9l-6 4v-4H3V4h17z", "M7 8h9m-9 4h6"],
    link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
    retry: ["M20 11a8 8 0 1 0-2 7", "M20 4v7h-7"],
    grip: ["M8 9h8M8 13h8"],
    out: ["M14 4h6v6", "M20 4 11 13", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"],
  };
  const reducedMotion = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  function kindColorExpr() {
    const e = ["match", ["get", "kind"]];
    for (const k of C.KIND_ORDER) e.push(k, C.KINDS[k].color);
    e.push(C.OTHER_KIND.color);
    return e;
  }

  function layerDefs() {
    const kc = kindColorExpr();
    const isPoly = ["==", ["geometry-type"], "Polygon"];
    const isLine = ["==", ["geometry-type"], "LineString"];
    const isPoint = ["==", ["geometry-type"], "Point"];
    const exact = ["==", ["get", "exact"], true];
    const approx = ["!=", ["get", "exact"], true];
    const statusOpacity = (inProgress, planned, completed, other) =>
      ["match", ["get", "status"], "in_progress", inProgress, "planned", planned, "completed", completed, other];
    const none = ["==", ["get", "cid"], "\u0000none"];
    return [
      { id: L.areaFill, type: "fill", source: SRC, filter: isPoly,
        paint: { "fill-color": ["match", ["get", "status"], "cancelled", "#8b939c", kc], "fill-opacity": statusOpacity(0.3, 0.18, 0.12, 0.1) } },
      { id: L.areaLine, type: "line", source: SRC, filter: ["all", isPoly, exact],
        paint: { "line-color": kc, "line-width": 2, "line-opacity": statusOpacity(0.95, 0.9, 0.6, 0.55) } },
      { id: L.areaLineApprox, type: "line", source: SRC, filter: ["all", isPoly, approx],
        paint: { "line-color": kc, "line-width": 2, "line-dasharray": [2, 1.6], "line-opacity": statusOpacity(0.95, 0.9, 0.6, 0.55) } },
      { id: L.lineCasing, type: "line", source: SRC, filter: isLine, layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.9 } },
      { id: L.line, type: "line", source: SRC, filter: ["all", isLine, exact], layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["match", ["get", "status"], "cancelled", "#8b939c", kc], "line-width": 5, "line-opacity": statusOpacity(1, 0.9, 0.55, 0.6) } },
      { id: L.lineApprox, type: "line", source: SRC, filter: ["all", isLine, approx], layout: { "line-join": "round" },
        paint: { "line-color": ["match", ["get", "status"], "cancelled", "#8b939c", kc], "line-width": 5, "line-dasharray": [1.4, 1.1], "line-opacity": statusOpacity(1, 0.9, 0.55, 0.6) } },
      { id: L.synthLine, type: "line", source: SRC, filter: ["all", ["!", isPoint], ["==", ["get", "synthetic"], true]],
        paint: { "line-color": "#4f5965", "line-width": 1.2, "line-gap-width": ["case", isLine, 12, 5], "line-dasharray": [1, 2], "line-opacity": 0.85 } },
      { id: L.selLine, type: "line", source: SRC, filter: ["all", ["!", isPoint], none], layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#152c26", "line-width": 3, "line-gap-width": ["case", isLine, 7, 0], "line-opacity": 0.95 } },
      { id: L.pointHalo, type: "circle", source: SRC, filter: ["all", isPoint, approx],
        paint: { "circle-radius": 18, "circle-color": kc, "circle-opacity": 0.13, "circle-stroke-color": kc, "circle-stroke-width": 1, "circle-stroke-opacity": 0.45, "circle-pitch-alignment": "map" } },
      { id: L.pointSynth, type: "circle", source: SRC, filter: ["all", isPoint, ["==", ["get", "synthetic"], true]],
        paint: { "circle-radius": 12.5, "circle-opacity": 0, "circle-stroke-color": "#4f5965", "circle-stroke-width": 1.5, "circle-stroke-opacity": 0.9 } },
      { id: L.point, type: "circle", source: SRC, filter: isPoint,
        paint: {
          "circle-radius": 7.5,
          "circle-color": ["match", ["get", "status"], "in_progress", kc, "completed", kc, "cancelled", "#a3aab3", "#ffffff"],
          "circle-opacity": ["match", ["get", "status"], "completed", 0.6, 1],
          "circle-stroke-color": ["match", ["get", "status"], "planned", kc, "in_progress", "#ffffff", "completed", "#ffffff", "#4f5965"],
          "circle-stroke-width": ["match", ["get", "status"], "planned", 3, "unknown", 2.5, 2],
        } },
      { id: L.selPoint, type: "circle", source: SRC, filter: ["all", isPoint, none],
        paint: { "circle-radius": 13, "circle-opacity": 0, "circle-stroke-color": "#152c26", "circle-stroke-width": 3 } },
    ];
  }

  function mount(options) {
    const opt = options || {};
    if (!C) throw new Error("CivicMap: civic-map-core.js must be loaded before civic-map.js");
    const root = opt.root;
    if (!root || root.nodeType !== 1) throw new Error("CivicMap.mount: root element is required");
    if (!opt.api || typeof opt.api.request !== "function") throw new Error("CivicMap.mount: api.request(method, path, body) is required");
    const api = opt.api;
    const onSelect = typeof opt.onSelect === "function" ? opt.onSelect : null;
    const onFeedback = typeof opt.onFeedback === "function" ? opt.onFeedback : null;
    const now = typeof opt.now === "function" ? opt.now : () => new Date();
    const layout = opt.layout === "embedded" ? "embedded" : "overlay";
    const persist = opt.persistFilters !== false;
    const permalink = opt.permalink === true;
    const region = opt.region === null ? null : (Array.isArray(opt.region) ? opt.region : C.ASTANA_BBOX);
    const basePadding = Object.assign({ top: 110, right: 80, bottom: 40, left: 40 }, opt.mapPadding || {});
    const pathPrefix = typeof opt.pathPrefix === "string" ? opt.pathPrefix : "";
    const title = typeof opt.title === "string" && opt.title ? opt.title : "Что делают рядом";

    let map = null;
    let destroyed = false;
    const mapHandlers = [];
    const cleanups = [];
    const listSeq = C.createSequence();
    const cardSeq = C.createSequence();
    let popup = null, cursorSet = false, hoverRaf = 0, moveTimer = 0, lastHoverPoint = null;
    let addingLayers = false;

    const st = {
      items: [], excluded: 0, truncated: false,
      list: "idle", listError: null,
      filters: C.defaultFilters(), q: "",
      selectedId: null, view: "list",
      detail: { id: null, state: "idle", item: null, history: [], error: null },
      sheet: "peek", viewBox: null,
      compare: { a: null, b: null },
    };
    if (persist) {
      try { const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null"); if (saved) st.filters = C.sanitizeFilters(saved); } catch (e) { /* storage blocked: defaults */ }
    }
    if (opt.filters) st.filters = C.sanitizeFilters(opt.filters);

    // ---------- root setup (restored in destroy) ----------
    const saved = { className: root.className, role: root.getAttribute("role"), label: root.getAttribute("aria-label"), children: [...root.childNodes] };
    root.replaceChildren();
    root.classList.add(P + "root", P + "layout-" + layout);
    if (!saved.role) root.setAttribute("role", "region");
    if (!saved.label) root.setAttribute("aria-label", "Городские работы и события на карте");
    const mql = window.matchMedia ? window.matchMedia(MOBILE_QUERY) : null;
    const isMobile = () => !!(mql && mql.matches);

    // ---------- static skeleton ----------
    const handle = h("button", { type: "button", class: P + "handle", "data-r03-action": "sheet", "aria-label": "Развернуть список" }, h("span", { class: P + "grip", "aria-hidden": "true" }));
    const countEl = h("p", { class: P + "count", role: "status", "aria-live": "polite" });
    const demoNote = h("p", { class: P + "demo-note", hidden: true });
    const head = h("header", { class: P + "head" },
      h("div", { class: P + "head-row" }, h("h2", { class: P + "title", text: title }), h("span", { class: P + "city", text: "Астана" })),
      countEl, demoNote);

    const searchInput = h("input", { type: "search", class: P + "search", id: P + "q", placeholder: "Название или описание", autocomplete: "off", "aria-label": "Поиск по названию и описанию", maxlength: "120" });
    const kindBox = h("div", { class: P + "chips", role: "group", "aria-label": "Вид работ" });
    const statusSel = h("select", { id: P + "status", class: P + "select", "data-r03-filter": "status" },
      h("option", { value: "", text: "Все статусы" }), C.STATUS_ORDER.map((s) => h("option", { value: s, text: C.STATUSES[s] })));
    const periodSel = h("select", { id: P + "period", class: P + "select", "data-r03-filter": "period" },
      Object.entries(C.PERIODS).map(([k, v]) => h("option", { value: k, text: v })));
    const fromInput = h("input", { type: "date", id: P + "from", class: P + "date", "data-r03-filter": "from" });
    const toInput = h("input", { type: "date", id: P + "to", class: P + "date", "data-r03-filter": "to" });
    const customBox = h("div", { class: P + "custom", hidden: true },
      h("label", { for: P + "from" }, "с", fromInput), h("label", { for: P + "to" }, "по", toInput));
    const areaBox = h("input", { type: "checkbox", id: P + "area", "data-r03-filter": "area" });
    const resetBtn = h("button", { type: "button", class: P + "link-btn", "data-r03-action": "reset-filters", text: "Сбросить фильтры" });
    const periodNote = h("p", { class: P + "hint" });
    const filtersSummary = h("summary", { class: P + "filters-summary" }, h("span", { text: "Фильтры" }), h("span", { class: P + "filters-active" }));
    const filters = h("details", { class: P + "filters" }, filtersSummary,
      h("div", { class: P + "filters-body" },
        h("label", { class: P + "field", for: P + "q" }, h("span", { text: "Поиск" }), searchInput),
        h("div", { class: P + "field" }, h("span", { class: P + "field-label", id: P + "kinds-label", text: "Вид" }), kindBox),
        h("div", { class: P + "two" },
          h("label", { class: P + "field", for: P + "status" }, h("span", { text: "Статус" }), statusSel),
          h("label", { class: P + "field", for: P + "period" }, h("span", { text: "Период по плану" }), periodSel)),
        customBox, periodNote,
        h("div", { class: P + "row" },
          h("label", { class: P + "check", for: P + "area" }, areaBox, h("span", { text: "Только видимая часть карты" })),
          resetBtn)));
    kindBox.setAttribute("aria-labelledby", P + "kinds-label");
    for (const k of C.KIND_ORDER) {
      kindBox.append(h("button", { type: "button", class: P + "chip", "data-r03-action": "toggle-kind", "data-kind": k, "aria-pressed": "false", style: { "--civic-r03-k": C.KINDS[k].color } },
        h("i", { class: P + "dot", "aria-hidden": "true" }), h("span", { text: C.KINDS[k].label }), h("span", { class: P + "chip-count" })));
    }

    const statusBox = h("div", { class: P + "state", "aria-live": "polite" });
    const listEl = h("ul", { class: P + "list", "aria-label": "Объекты" });
    const listNotes = h("div", { class: P + "list-notes" });
    const legend = buildLegend();
    const listView = h("section", { class: P + "list-view", "aria-label": "Список объектов" }, filters, statusBox, listEl, listNotes, legend);
    const cardView = h("section", { class: P + "card", "aria-label": "Карточка объекта", hidden: true });
    const scroller = h("div", { class: P + "scroll" }, listView, cardView);
    root.append(handle, head, scroller);

    function buildLegend() {
      const sample = (cls, color, label) => h("li", null, h("span", { class: P + "sw " + cls, style: { "--civic-r03-k": color }, "aria-hidden": "true" }), h("span", { text: label }));
      const g = C.KINDS.roadworks.color;
      return h("details", { class: P + "legend" }, h("summary", { text: "Обозначения на карте" }),
        h("div", { class: P + "legend-body" },
          h("p", { class: P + "legend-h", text: "Цвет — вид" }),
          h("ul", null, C.KIND_ORDER.map((k) => sample(P + "sw-solid", C.KINDS[k].color, C.KINDS[k].label))),
          h("p", { class: P + "legend-h", text: "Заливка точки — статус" }),
          h("ul", null,
            sample(P + "sw-ring", g, "Запланировано — кольцо"),
            sample(P + "sw-solid", g, "Идут работы — заливка"),
            sample(P + "sw-faded", g, "Завершено — бледная заливка"),
            sample(P + "sw-cancel", g, "Отменено — серый"),
            sample(P + "sw-unknown", g, "Статус неизвестен — серое кольцо")),
          h("p", { class: P + "legend-h", text: "Точность места" }),
          h("ul", null,
            sample(P + "sw-solid", g, "Сплошная линия, точка — место по источнику"),
            sample(P + "sw-halo", g, "Пунктир, ореол — примерное место"),
            sample(P + "sw-synth", g, "Серое пунктирное кольцо — демо-запись")),
          h("p", { class: P + "hint", text: "Записи без координат есть только в списке: точку за них не придумываем." })));
    }

    // ---------- listeners on root (delegated; removed in destroy) ----------
    function on(target, type, fn, o) { target.addEventListener(type, fn, o); cleanups.push(() => target.removeEventListener(type, fn, o)); }
    on(root, "click", onRootClick);
    on(root, "change", onRootChange);
    on(root, "input", onRootInput);
    on(root, "keydown", onRootKey);
    on(handle, "pointerdown", onHandleDown);
    if (mql) {
      const f = () => { applySheet(); };
      if (mql.addEventListener) { mql.addEventListener("change", f); cleanups.push(() => mql.removeEventListener("change", f)); }
    }
    if (permalink) on(window, "hashchange", onHash);

    function onRootClick(e) {
      const t = e.target.closest("[data-r03-action]");
      if (!t || !root.contains(t)) return;
      const a = t.getAttribute("data-r03-action");
      if (a === "select") { selectObject(t.getAttribute("data-id"), { source: "list" }); }
      else if (a === "back") closeCard();
      else if (a === "retry-list") refresh();
      else if (a === "retry-card" && st.detail.id) loadDetail(st.detail.id);
      else if (a === "reset-filters") { st.filters = C.defaultFilters(); st.q = ""; searchInput.value = ""; filtersChanged(); }
      else if (a === "toggle-kind") {
        const k = t.getAttribute("data-kind");
        const set = new Set(st.filters.kinds);
        if (set.has(k)) set.delete(k); else set.add(k);
        st.filters.kinds = [...set];
        filtersChanged();
      } else if (a === "fly") { const it = currentItem(); if (it) flyTo(it); }
      else if (a === "feedback") {
        const it = currentItem();
        if (it && onFeedback) onFeedback({ objectId: it.id, title: it.title, geometry: it.geometry, object: publicCopy(it) });
      } else if (a === "sheet") cycleSheet();
      else if (a === "copy-link") copyLink(t);
      else if (a === "show-undated") { st.filters.period = "all"; filtersChanged(); }
    }
    function onRootChange(e) {
      const f = e.target.getAttribute && e.target.getAttribute("data-r03-filter");
      if (f === "status") st.filters.statuses = e.target.value ? [e.target.value] : [];
      else if (f === "period") st.filters.period = e.target.value;
      else if (f === "from") st.filters.from = e.target.value || null;
      else if (f === "to") st.filters.to = e.target.value || null;
      else if (f === "area") { st.filters.area = !!e.target.checked; updateViewBox(); }
      else if (e.target.getAttribute && e.target.getAttribute("data-r03-compare")) {
        st.compare[e.target.getAttribute("data-r03-compare")] = e.target.value ? +e.target.value : null;
        renderCompare();
        return;
      } else return;
      filtersChanged();
    }
    function onRootInput(e) {
      if (e.target === searchInput) { st.q = searchInput.value.slice(0, 120); renderList(); }
    }
    function onRootKey(e) {
      if (e.key === "Escape" && st.view === "card") { e.preventDefault(); closeCard(); }
    }
    // Drag the mobile sheet handle; a tap cycles states.
    let drag = null;
    function onHandleDown(e) {
      if (!isMobile()) return;
      drag = { y: e.clientY, h: root.getBoundingClientRect().height, moved: false, id: e.pointerId };
      try { handle.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      handle.addEventListener("pointermove", onHandleMove);
      handle.addEventListener("pointerup", onHandleUp);
      handle.addEventListener("pointercancel", onHandleUp);
    }
    function onHandleMove(e) {
      if (!drag) return;
      const dy = e.clientY - drag.y;
      if (Math.abs(dy) > 6) drag.moved = true;
      if (drag.moved) root.style.setProperty("--civic-r03-drag-h", Math.max(96, drag.h - dy) + "px");
      if (drag.moved) root.setAttribute("data-civic-r03-dragging", "");
    }
    function onHandleUp(e) {
      handle.removeEventListener("pointermove", onHandleMove);
      handle.removeEventListener("pointerup", onHandleUp);
      handle.removeEventListener("pointercancel", onHandleUp);
      if (!drag) return;
      const d = drag; drag = null;
      root.removeAttribute("data-civic-r03-dragging");
      root.style.removeProperty("--civic-r03-drag-h");
      if (!d.moved) return; // click handler cycles
      const dy = e.clientY - d.y;
      const order = ["peek", "half", "full"];
      let i = order.indexOf(st.sheet);
      if (dy < -40) i = Math.min(2, i + (dy < -220 ? 2 : 1));
      if (dy > 40) i = Math.max(0, i - (dy > 220 ? 2 : 1));
      setSheet(order[i]);
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 0);
    }
    let suppressClick = false;
    function cycleSheet() {
      if (suppressClick) return;
      setSheet(st.sheet === "peek" ? "half" : st.sheet === "half" ? "full" : "peek");
    }
    function setSheet(s) { st.sheet = s; applySheet(); }
    function applySheet() {
      root.setAttribute("data-civic-r03-sheet", st.sheet);
      handle.setAttribute("aria-label", st.sheet === "full" ? "Свернуть панель" : "Развернуть панель");
      handle.setAttribute("aria-expanded", String(st.sheet !== "peek"));
      handle.hidden = !isMobile() || layout !== "overlay";
      if (isMobile() && filters.open && st.sheet === "peek") filters.open = false;
      if (destroyed) return;
      try { root.dispatchEvent(new CustomEvent("civic-r03:layout", { detail: getLayout() })); } catch (e) { /* old browsers */ }
    }
    function getLayout() {
      const r = root.getBoundingClientRect();
      return { mobile: isMobile(), sheet: st.sheet, view: st.view, rect: { left: r.left, top: r.top, width: r.width, height: r.height } };
    }

    // ---------- filters ----------
    function filtersChanged() {
      st.filters = C.sanitizeFilters(st.filters);
      if (persist) { try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(st.filters)); } catch (e) { /* ignore */ } }
      syncFilterControls();
      renderList();
      updateMapData();
    }
    function today() { return C.localDay(now()); }
    function syncFilterControls() {
      const f = st.filters;
      for (const b of kindBox.querySelectorAll("[data-kind]")) b.setAttribute("aria-pressed", String(f.kinds.includes(b.getAttribute("data-kind"))));
      statusSel.value = f.statuses[0] || "";
      periodSel.value = f.period;
      customBox.hidden = f.period !== "custom";
      fromInput.value = f.from || "";
      toInput.value = f.to || "";
      areaBox.checked = f.area;
      areaBox.disabled = !map;
      const active = (f.kinds.length ? 1 : 0) + (f.statuses.length ? 1 : 0) + (f.period !== "all" ? 1 : 0) + (f.area ? 1 : 0) + (st.q ? 1 : 0);
      filtersSummary.lastChild.textContent = active ? "активно: " + active : "";
      resetBtn.hidden = !active;
      const r = C.periodRange(f.period, today(), { from: f.from, to: f.to });
      periodNote.textContent = r.from || r.to
        ? "Плановые сроки пересекают " + (r.from ? "с " + C.formatDay(r.from) : "") + (r.to ? " по " + C.formatDay(r.to) : "") + ". Это план, а не подтверждение, что работы идут."
        : "";
      periodNote.hidden = !periodNote.textContent;
    }
    function textMatch(it, q) {
      if (!q) return true;
      const norm = (s) => String(s || "").toLocaleLowerCase("ru").replace(/ё/g, "е");
      const needle = norm(q).trim();
      return !needle || norm(it.title).includes(needle) || norm(it.description).includes(needle) || norm(it.responsible.organization).includes(needle);
    }
    function filtered() {
      const res = C.applyFilters(st.items, st.filters, { today: today(), viewBox: st.filters.area ? st.viewBox : null });
      if (st.q) {
        const before = res.shown.length;
        res.shown = res.shown.filter((r) => textMatch(r.item, st.q));
        res.counts.bySearch = before - res.shown.length;
        res.counts.shown = res.shown.length;
      }
      res.shown = C.sortItems(res.shown);
      return res;
    }
    // Map shows kind/status/period/search filters, never the viewport filter.
    function mapItems() {
      const res = C.applyFilters(st.items, st.filters, { today: today(), viewBox: null });
      return res.shown.map((r) => r.item).filter((it) => textMatch(it, st.q));
    }

    // ---------- list ----------
    function renderList() {
      if (destroyed) return;
      const focusedId = document.activeElement && listEl.contains(document.activeElement) ? document.activeElement.getAttribute("data-id") : null;
      const res = filtered();
      const c = res.counts;
      for (const b of kindBox.querySelectorAll("[data-kind]")) {
        const n = c.byKind[b.getAttribute("data-kind")] || 0;
        b.querySelector("." + P + "chip-count").textContent = st.list === "ready" ? String(n) : "";
      }
      const synth = st.items.filter((it) => it.evidence === "synthetic").length;
      demoNote.hidden = !synth;
      demoNote.textContent = synth ? (synth === st.items.length ? "Все записи — синтетические демо-данные, не сведения о реальных работах." : "Демо-записей: " + synth + ". Они отмечены «Демо» и не описывают реальные работы.") : "";
      statusBox.replaceChildren();
      listEl.replaceChildren();
      listNotes.replaceChildren();
      listEl.setAttribute("aria-busy", String(st.list === "loading"));
      if (st.list === "loading" && !st.items.length) {
        countEl.textContent = "Загружаем объекты…";
        statusBox.append(h("div", { class: P + "loading" }, h("span", { class: P + "spinner", "aria-hidden": "true" }), "Загружаем опубликованные объекты…"));
        return;
      }
      if (st.list === "error") {
        countEl.textContent = st.items.length ? "Показаны прежние данные" : "Данные не загружены";
        statusBox.append(h("div", { class: P + "error", role: "alert" },
          h("p", { text: st.listError ? st.listError.text : "Не удалось загрузить объекты." }),
          h("button", { type: "button", class: P + "btn", "data-r03-action": "retry-list" }, svgIcon(ICON.retry), "Повторить")));
        if (!st.items.length) return;
      }
      if (st.list === "loading") statusBox.append(h("p", { class: P + "hint", text: "Обновляем…" }));
      countEl.textContent = st.list === "idle" ? "" : (c.shown === c.total ? plural(c.total, "объект", "объекта", "объектов") : "Показано " + c.shown + " из " + c.total);
      if (st.list === "ready" && !st.items.length) {
        statusBox.append(h("div", { class: P + "empty" }, h("p", { text: "Опубликованных объектов пока нет." }),
          h("p", { class: P + "hint", text: "Когда сотрудники опубликуют работы или события, они появятся на карте и в этом списке." })));
        return;
      }
      if (!res.shown.length && st.items.length) {
        statusBox.append(h("div", { class: P + "empty" }, h("p", { text: "По выбранным условиям ничего не найдено." }),
          h("button", { type: "button", class: P + "btn", "data-r03-action": "reset-filters", text: "Сбросить фильтры" })));
      }
      const frag = document.createDocumentFragment();
      for (const row of res.shown) frag.append(listItem(row.item, row.partial));
      listEl.append(frag);
      const notes = [];
      if (c.undated) notes.push(h("li", null, "Без плановых дат: " + c.undated + " — период их не включает. ", h("button", { type: "button", class: P + "link-btn", "data-r03-action": "show-undated", text: "Показать все сроки" })));
      if (c.partial) notes.push(h("li", { text: "С неполным интервалом: " + c.partial + " — известна только одна дата, она попадает в период." }));
      if (c.outsideArea) notes.push(h("li", { text: "Вне видимой части карты: " + c.outsideArea + "." }));
      if (c.noGeometry) notes.push(h("li", { text: "Без места на карте (не входят в «видимую часть»): " + c.noGeometry + "." }));
      const noGeo = st.items.filter((it) => !it.geometry).length;
      if (noGeo && !st.filters.area) notes.push(h("li", { text: "Без координат: " + noGeo + " — есть только в списке, на карте не показаны." }));
      if (st.truncated) notes.push(h("li", { text: "Загружены первые " + st.items.length + " записей; остальные не показаны." }));
      if (st.excluded) notes.push(h("li", { text: "Пропущено некорректных или неопубликованных записей: " + st.excluded + "." }));
      if (notes.length) listNotes.append(h("ul", null, notes));
      if (focusedId) {
        const again = listEl.querySelector('[data-id="' + cssEscape(focusedId) + '"]');
        if (again) again.focus();
      }
    }
    function cssEscape(s) { return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&"); }
    function plural(n, a, b, c) { return n + " " + C.plural(n, a, b, c); }
    function badge(text, cls, title) { return h("span", { class: P + "badge " + (cls ? P + cls : ""), title: title || null, text }); }
    function evidenceBadge(it) {
      if (it.evidence === "observed") return null;
      const info = C.evidenceInfo(it.evidence);
      return badge(info.short, it.evidence === "synthetic" ? "b-demo" : "b-warn", info.label);
    }
    function listItem(it, partial) {
      const k = C.kindInfo(it.kind);
      const iv = C.plannedInterval(it);
      const shift = C.scheduleShift(it);
      const stale = C.staleness(it, today());
      const when = iv.end ? "до " + C.formatDay(iv.end) : iv.start ? "с " + C.formatDay(iv.start) : "сроки: нет данных";
      const meta = [C.STATUSES[it.status], when];
      if (shift) meta.push(shift.days > 0 ? "срок перенесён" : "срок сдвинут раньше");
      const badges = [evidenceBadge(it),
        stale ? badge("Срок по плану прошёл", "b-warn") : null,
        !it.geometry ? badge("Нет на карте", "b-muted", it.issues[0] || "Координаты не указаны") : it.precision !== "source" ? badge(it.precision === "approximate" ? "Примерное место" : "Точность места?", "b-muted") : null,
        partial ? badge("Неполный интервал", "b-muted", "Известна только одна плановая дата") : null].filter(Boolean);
      const btn = h("button", { type: "button", class: P + "item", "data-r03-action": "select", "data-id": it.id, "aria-current": st.selectedId === it.id ? "true" : null, style: { "--civic-r03-k": k.color } },
        h("span", { class: P + "item-kind" }, h("i", { class: P + "dot " + P + "st-" + it.status, "aria-hidden": "true" }), k.label),
        h("span", { class: P + "item-title", text: it.title }),
        h("span", { class: P + "item-meta", text: meta.join(" · ") }),
        badges.length ? h("span", { class: P + "badges" }, badges) : null);
      return h("li", null, btn);
    }

    // ---------- loading ----------
    async function request(method, path) {
      const data = await api.request(method, pathPrefix + path, undefined);
      return C.unwrap(data);
    }
    async function refresh() {
      if (destroyed) return;
      const t = listSeq.next();
      st.list = "loading";
      st.listError = null;
      renderList();
      try {
        const raw = [];
        let cursor = null, pages = 0, truncated = false;
        do {
          const data = await request("GET", "/objects" + (cursor ? "?cursor=" + encodeURIComponent(cursor) : ""));
          if (destroyed || !listSeq.isCurrent(t)) return;
          const items = data && Array.isArray(data.items) ? data.items : Array.isArray(data) ? data : null;
          if (!items) throw Object.assign(new Error("bad payload"), { code: "bad_payload" });
          raw.push(...items);
          cursor = data && typeof data.next_cursor === "string" && data.next_cursor ? data.next_cursor : null;
          pages++;
          if (cursor && pages >= MAX_PAGES) { truncated = true; break; }
        } while (cursor);
        const norm = C.normalizeList(raw, { region });
        st.items = norm.items;
        st.excluded = norm.excluded.length;
        st.truncated = truncated;
        st.list = "ready";
        renderList();
        updateMapData();
        // Keep an open card in sync with the fresh list (or say it is gone).
        if (st.selectedId) {
          const fresh = st.items.find((x) => x.id === st.selectedId);
          if (fresh && st.detail.state !== "loading") { st.detail.item = fresh; renderCard(); }
        }
      } catch (err) {
        if (destroyed || !listSeq.isCurrent(t)) return;
        st.list = "error";
        st.listError = C.errorInfo(err);
        if (err && err.code === "bad_payload") st.listError.text = "Сервер вернул данные в неожиданном формате.";
        renderList();
      }
    }

    function findItem(id) { return st.items.find((x) => x.id === id) || null; }
    function currentItem() { return st.detail.item || findItem(st.selectedId); }
    function publicCopy(it) {
      return it ? Object.freeze({ id: it.id, title: it.title, kind: it.kind, status: it.status, geometry: it.geometry, precision: it.precision, evidence: it.evidence, schedule: Object.assign({}, it.schedule) }) : null;
    }

    async function selectObject(id, o) {
      if (destroyed) return;
      const opts = o || {};
      if (id === null || id === undefined || id === "") { closeCard(); return; }
      id = String(id);
      const prevFocus = opts.source === "list" ? id : null;
      st.selectedId = id;
      st.view = "card";
      st.compare = { a: null, b: null };
      const listed = findItem(id);
      st.detail = { id, state: "loading", item: listed, history: [], error: null, returnFocus: prevFocus };
      updateSelection();
      renderCard(true);
      if (isMobile() && st.sheet === "peek") setSheet("half");
      if (listed && opts.fly !== false && opts.source !== "map") flyTo(listed);
      if (permalink) writeHash(id);
      if (onSelect) safeCall(onSelect, publicCopy(listed) || { id }, { source: opts.source || "api" });
      await loadDetail(id, opts);
    }
    async function loadDetail(id, opts) {
      const t = cardSeq.next();
      st.detail.state = "loading";
      st.detail.error = null;
      renderCard();
      try {
        const data = await request("GET", "/objects/" + encodeURIComponent(id));
        if (destroyed || !cardSeq.isCurrent(t) || st.selectedId !== id) return;
        const raw = data && data.item ? data.item : null;
        const norm = raw ? C.normalizeObject(raw, { region }) : { item: null };
        if (!norm.item || norm.item.id !== id) {
          st.detail.state = "notfound";
          st.detail.item = null;
        } else {
          const hadItem = !!st.detail.item;
          st.detail.item = norm.item;
          st.detail.history = C.normalizeHistory(data.history);
          st.detail.state = "ready";
          if (!hadItem && opts && opts.fly !== false && (!opts.source || opts.source !== "map")) flyTo(norm.item);
          if (!hadItem && onSelect) safeCall(onSelect, publicCopy(norm.item), { source: (opts && opts.source) || "api" });
        }
      } catch (err) {
        if (destroyed || !cardSeq.isCurrent(t) || st.selectedId !== id) return;
        const info = C.errorInfo(err);
        st.detail.state = info.notFound ? "notfound" : "error";
        if (info.notFound) st.detail.item = null;
        st.detail.error = info;
      }
      renderCard();
      updateSelection();
    }
    function closeCard() {
      cardSeq.cancel();
      const back = st.detail.returnFocus || st.selectedId;
      st.selectedId = null;
      st.view = "list";
      st.detail = { id: null, state: "idle", item: null, history: [], error: null };
      updateSelection();
      renderCard();
      renderList();
      if (permalink) writeHash(null);
      if (onSelect) safeCall(onSelect, null, { source: "close" });
      const target = back ? listEl.querySelector('[data-id="' + cssEscape(back) + '"]') : null;
      if (target) target.focus();
      else if (root.contains(document.activeElement) || document.activeElement === document.body) { countEl.setAttribute("tabindex", "-1"); countEl.focus(); }
    }
    function safeCall(fn, ...args) { try { fn(...args); } catch (e) { console.error("CivicMap callback failed", e); } }

    // ---------- card ----------
    function dlRow(label, value, extra) {
      return [h("dt", { text: label }), h("dd", null, value === null || value === undefined || value === "" ? h("span", { class: P + "nodata", text: C.NO_DATA }) : value, extra || null)];
    }
    function renderCard(focus) {
      if (destroyed) return;
      root.setAttribute("data-civic-r03-view", st.view);
      listView.hidden = st.view === "card";
      cardView.hidden = st.view !== "card";
      cardView.replaceChildren();
      if (st.view !== "card") return;
      const d = st.detail;
      const it = d.item;
      const top = h("div", { class: P + "card-top" },
        h("button", { type: "button", class: P + "btn " + P + "btn-quiet", "data-r03-action": "back" }, svgIcon(ICON.back), "Все объекты"),
        it && it.geometry && map ? h("button", { type: "button", class: P + "btn " + P + "btn-quiet", "data-r03-action": "fly" }, svgIcon(ICON.pin), "На карте") : null);
      cardView.append(top);
      if (!it) {
        if (d.state === "loading") cardView.append(h("div", { class: P + "loading" }, h("span", { class: P + "spinner", "aria-hidden": "true" }), "Загружаем карточку…"));
        else if (d.state === "notfound") cardView.append(h("div", { class: P + "empty", role: "alert" }, h("h3", { class: P + "card-title", tabindex: "-1", text: "Объект не найден" }), h("p", { text: "Возможно, его сняли с публикации или ссылка устарела." })));
        else if (d.state === "error") cardView.append(h("div", { class: P + "error", role: "alert" }, h("p", { text: d.error ? d.error.text : "Не удалось загрузить карточку." }), h("button", { type: "button", class: P + "btn", "data-r03-action": "retry-card" }, svgIcon(ICON.retry), "Повторить")));
        if (focus) focusCard();
        return;
      }
      const k = C.kindInfo(it.kind);
      const ev = C.evidenceInfo(it.evidence);
      if (it.evidence !== "observed") {
        cardView.append(h("p", { class: P + "banner " + (it.evidence === "synthetic" ? P + "banner-demo" : P + "banner-warn"), role: "note" }, h("b", { text: ev.short + ". " }), ev.label + "."));
      }
      cardView.append(
        h("div", { class: P + "card-kind", style: { "--civic-r03-k": k.color } }, h("i", { class: P + "dot " + P + "st-" + it.status, "aria-hidden": "true" }), k.label + (it.kind === "other" && it.rawKind ? " (" + it.rawKind.slice(0, 40) + ")" : "")),
        h("h3", { class: P + "card-title", tabindex: "-1", text: it.title }),
        h("p", { class: P + "status-line" }, h("span", { class: P + "status " + P + "status-" + it.status, text: C.STATUSES[it.status] }),
          h("span", { class: P + "muted", text: it.updatedAt ? " по данным на " + C.formatTimestamp(it.updatedAt) : " · дата обновления не указана" })));
      if (it.description) cardView.append(h("section", { class: P + "sec" }, h("h4", { text: "Назначение" }), h("p", { class: P + "desc", text: it.description })));

      const stale = C.staleness(it, today());
      if (stale) cardView.append(h("p", { class: P + "banner " + P + "banner-warn", role: "note" },
        "Плановый срок окончания (" + C.formatDay(stale.end) + ") прошёл " + C.daysText(stale.days) + " назад, а в записи статус «" + C.STATUSES[it.status] + "». Фактическое состояние работ эта запись не подтверждает."));

      // Schedule
      const s = it.schedule;
      const shift = C.scheduleShift(it);
      const reasonInfo = C.shiftReason(d.history);
      let shiftNode = null;
      if (shift) {
        const dir = shift.days > 0 ? "позже" : "раньше";
        let reasonText;
        if (reasonInfo && reasonInfo.reason) reasonText = h("span", null, "Причина: ", h("q", { text: reasonInfo.reason }), reasonInfo.at ? " · " + C.formatTimestamp(reasonInfo.at) : "");
        else if (d.state === "loading") reasonText = h("span", { class: P + "muted", text: "Причина: загружаем историю…" });
        else if (d.state === "error") reasonText = h("span", { class: P + "muted", text: "Причина: история не загрузилась." });
        else reasonText = h("span", { class: P + "muted", text: "Причина переноса в опубликованной истории не указана." });
        shiftNode = h("div", { class: P + "shift", role: "note" },
          h("b", { text: "Срок перенесён на " + C.daysText(shift.days) + " " + dir + ": " }),
          h("span", { text: C.formatDay(shift.from) + " → " + C.formatDay(shift.to) }), h("br"), reasonText);
      }
      const iv = C.plannedInterval(it);
      cardView.append(h("section", { class: P + "sec" }, h("h4", { text: "Сроки" }),
        shiftNode,
        h("dl", { class: P + "dl" },
          dlRow("Начало по плану", s.planned_start ? C.formatDay(s.planned_start, "long") : null),
          dlRow("Первоначальный срок", s.original_planned_end ? C.formatDay(s.original_planned_end, "long") : null),
          dlRow("Текущий срок", s.current_planned_end ? C.formatDay(s.current_planned_end, "long") : null),
          dlRow("Фактическое окончание", s.actual_end ? C.formatDay(s.actual_end, "long") : null)),
        !iv.complete ? h("p", { class: P + "hint", text: "Плановый интервал неполный: неизвестную дату не заменяем сегодняшней." }) : null));

      // Responsible + budget
      const b = it.budget;
      const budgetSrc = b.sourceId ? it.sourceRefs.find((r) => r.id === b.sourceId) : null;
      cardView.append(h("section", { class: P + "sec" }, h("h4", { text: "Кто отвечает и сколько стоит" }),
        h("dl", { class: P + "dl" },
          dlRow("Организация", it.responsible.organization),
          dlRow("Публичный контакт", it.responsible.public_contact),
          dlRow("Стоимость", b.state === "ok" ? h("span", null, h("b", { class: P + "num", text: b.text }), b.approx ? h("span", { class: P + "muted", text: " " + b.approx }) : null) : h("span", { class: P + "nodata", text: b.text }),
            h("span", { class: P + "basis", text: b.state === "ok" ? b.basisLabel + (budgetSrc ? " · источник: " + (budgetSrc.publisher || budgetSrc.host || budgetSrc.id) : b.sourceId ? " · источник «" + b.sourceId + "» не найден в списке" : " · источник суммы не указан") : "" })))));

      // Place
      let placeText;
      if (!it.geometry) placeText = it.issues.find((x) => /координат|геометр/.test(x)) ? "Место не показано: " + it.issues.find((x) => /координат|геометр/.test(x)) + "." : "Координаты не указаны — объект есть только в списке, точку не придумываем.";
      else placeText = C.PRECISION[it.precision] + ". " + ({ Point: "Точка", LineString: "Линия (участок)", Polygon: "Территория" }[it.geometry.type] || "") + ".";
      cardView.append(h("section", { class: P + "sec" }, h("h4", { text: "Место" }), h("p", { text: placeText })));

      // Sources
      const srcSec = h("section", { class: P + "sec" }, h("h4", { text: "Источники" }));
      if (!it.sourceRefs.length) srcSec.append(h("p", { class: P + "nodata", text: it.evidence === "synthetic" ? "Нет: это демо-запись." : "Источник не указан." }));
      else {
        const ul = h("ul", { class: P + "sources" });
        for (const r of it.sourceRefs) {
          const name = r.publisher || r.host || "Источник";
          const link = r.url ? h("a", { href: r.url, target: "_blank", rel: "noopener noreferrer nofollow", class: P + "src-link" }, name, svgIcon(ICON.out, 14), h("span", { class: P + "sr", text: " (откроется в новой вкладке)" })) : h("span", { text: name });
          const meta = [];
          if (r.published_on) meta.push("опубликовано " + C.formatDay(r.published_on));
          if (r.retrieved_at) meta.push("получено " + (C.parseTimestamp(r.retrieved_at) ? C.formatTimestamp(r.retrieved_at) : C.formatDay(r.retrieved_at)));
          if (r.access_status) meta.push(C.ACCESS[r.access_status]);
          meta.push(r.license ? "лицензия: " + r.license : "лицензия не указана");
          const fields = r.fields.length ? "подтверждает: " + [...new Set(r.fields.map(C.fieldLabel))].join(", ") : null;
          ul.append(h("li", null, link, r.host && r.publisher ? h("span", { class: P + "muted", text: " · " + r.host }) : null,
            r.rawUrlRejected ? h("span", { class: P + "warn-text", text: " · ссылка скрыта: небезопасный адрес" }) : null,
            h("span", { class: P + "src-meta", text: meta.join(" · ") }), fields ? h("span", { class: P + "src-meta", text: fields }) : null));
        }
        srcSec.append(ul);
      }
      if (it.evidenceNotes) srcSec.append(h("p", { class: P + "notes" }, h("b", { text: "Примечание: " }), it.evidenceNotes));
      if (it.issues.length) srcSec.append(h("p", { class: P + "warn-text", text: "Проблемы записи: " + it.issues.join("; ") + "." }));
      srcSec.append(h("p", { class: P + "meta", text: "Обновлено: " + (it.updatedAt ? C.formatTimestamp(it.updatedAt) : C.NO_DATA) + (it.revision ? " · редакция " + it.revision : "") }));
      cardView.append(srcSec);

      // History
      const hist = h("section", { class: P + "sec" }, h("h4", { text: "История изменений" }));
      if (d.state === "loading") hist.append(h("p", { class: P + "loading" }, h("span", { class: P + "spinner", "aria-hidden": "true" }), "Загружаем историю…"));
      else if (d.state === "error") hist.append(h("div", { class: P + "error", role: "alert" }, h("p", { text: (d.error ? d.error.text : "") + " Показаны сведения из списка." }), h("button", { type: "button", class: P + "btn", "data-r03-action": "retry-card" }, svgIcon(ICON.retry), "Повторить")));
      else if (!d.history.length) hist.append(h("p", { class: P + "nodata", text: "Опубликованных изменений нет." }));
      else {
        const ol = h("ol", { class: P + "history" });
        for (const r of d.history.slice(0, 50)) {
          const ch = r.changed.length ? r.changed.map((c) => C.fieldLabel(c.field) + (c.hasValues ? ": " + valueText(c.field, c.before) + " → " + valueText(c.field, c.after) : "")).join("; ") : "поля не указаны";
          ol.append(h("li", { class: touches(r) ? P + "h-schedule" : null },
            h("span", { class: P + "h-when", text: (r.at ? C.formatTimestamp(r.at) : "дата не указана") + (r.revision ? " · ред. " + r.revision : "") }),
            h("span", { class: P + "h-what", text: "Изменено: " + ch }),
            h("span", { class: P + "h-why", text: r.reason ? "Причина: " + r.reason : "Причина не указана" }),
            r.actor ? h("span", { class: P + "muted", text: r.actor }) : null));
        }
        hist.append(ol);
        if (d.history.filter((r) => r.revision !== null).length >= 2) hist.append(compareBlock(d.history));
      }
      cardView.append(hist);

      // Actions
      const actions = h("div", { class: P + "actions" });
      if (onFeedback) actions.append(h("button", { type: "button", class: P + "btn " + P + "btn-primary", "data-r03-action": "feedback" }, svgIcon(ICON.chat), "Задать вопрос по объекту"));
      if (permalink) actions.append(h("button", { type: "button", class: P + "btn", "data-r03-action": "copy-link" }, svgIcon(ICON.link), "Ссылка на объект"));
      if (actions.childNodes.length) cardView.append(actions);
      if (focus) focusCard();
    }
    function touches(r) { return r.changed.some((c) => c.field.startsWith("schedule")); }
    function valueText(field, v) {
      if (v === null || v === undefined) return C.NO_DATA;
      if (typeof v === "string" && C.parseDay(v)) return C.formatDay(v);
      if (field === "status" && C.STATUSES[v]) return C.STATUSES[v];
      if (typeof v === "number") return C.formatNumber(v);
      if (typeof v === "string") return v.length > 80 ? v.slice(0, 80) + "…" : v;
      return "изменено";
    }
    let compareOut = null;
    function compareBlock(rows) {
      const revs = rows.filter((r) => r.revision !== null);
      const mk = (key, label) => {
        const sel = h("select", { class: P + "select", "data-r03-compare": key, id: P + "cmp-" + key }, h("option", { value: "", text: "—" }),
          revs.map((r) => h("option", { value: String(r.revision), text: "ред. " + r.revision + (r.at ? " · " + (C.parseTimestamp(r.at) ? C.formatDay(C.parseTimestamp(r.at).day) : "") : "") })));
        if (st.compare[key]) sel.value = String(st.compare[key]);
        return h("label", { class: P + "field", for: P + "cmp-" + key }, h("span", { text: label }), sel);
      };
      compareOut = h("div", { class: P + "cmp-out", "aria-live": "polite" });
      const box = h("details", { class: P + "compare" }, h("summary", { text: "Сравнить две редакции" }),
        h("div", { class: P + "two" }, mk("a", "С редакции"), mk("b", "По редакцию")), compareOut);
      if (st.compare.a || st.compare.b) box.open = true;
      renderCompare();
      return box;
    }
    function renderCompare() {
      if (!compareOut) return;
      compareOut.replaceChildren();
      const { a, b } = st.compare;
      if (!a || !b || a === b) { compareOut.append(h("p", { class: P + "hint", text: "Выберите две разные редакции." })); return; }
      const cmp = C.compareRevisions(st.detail.history, a, b);
      if (!cmp || !cmp.fields.length) { compareOut.append(h("p", { class: P + "hint", text: "Между этими редакциями опубликованных изменений нет." })); return; }
      compareOut.append(h("p", { text: "Между ред. " + cmp.from + " и " + cmp.to + " изменено: " }),
        h("ul", null, cmp.fields.map((f) => h("li", { text: f.label + (f.hasValues ? ": " + valueText(f.field, f.before) + " → " + valueText(f.field, f.after) : "") }))),
        cmp.reasons.length ? h("p", { class: P + "muted", text: "Причины: " + cmp.reasons.map((r) => "ред. " + r.revision + " — " + r.reason).join("; ") }) : null,
        cmp.fields.some((f) => !f.hasValues) ? h("p", { class: P + "hint", text: "Публичная история хранит, какие поля менялись; прежние значения доступны редактору." }) : null);
    }
    function focusCard() {
      const t = cardView.querySelector("." + P + "card-title");
      if (t) { try { t.focus({ preventScroll: true }); } catch (e) { t.focus(); } }
      scroller.scrollTop = 0;
    }

    // ---------- permalink ----------
    function readHash() {
      const m = new RegExp("(?:^#|&)" + HASH_KEY + "=([^&]*)").exec(window.location.hash || "");
      if (!m) return null;
      try { return decodeURIComponent(m[1]).slice(0, 200); } catch (e) { return null; }
    }
    function writeHash(id) {
      try {
        const cur = window.location.hash.replace(/^#/, "").split("&").filter((p) => p && !p.startsWith(HASH_KEY + "="));
        if (id) cur.push(HASH_KEY + "=" + encodeURIComponent(id));
        const next = cur.length ? "#" + cur.join("&") : "";
        if (next !== window.location.hash) history.replaceState(history.state, "", window.location.pathname + window.location.search + next);
      } catch (e) { /* sandboxed iframe or file: */ }
    }
    function onHash() {
      const id = readHash();
      if (id && id !== st.selectedId) selectObject(id, { source: "permalink" });
    }
    function copyLink(btn) {
      const url = window.location.href;
      const done = (ok) => { btn.lastChild.textContent = ok ? "Ссылка скопирована" : "Скопируйте адрес из строки браузера"; };
      try { navigator.clipboard.writeText(url).then(() => done(true), () => done(false)); } catch (e) { done(false); }
    }

    // ---------- map ----------
    function onMap(type, fn) { map.on(type, fn); mapHandlers.push([type, fn]); }
    function firstLabelLayer() {
      const layers = (map.getStyle() && map.getStyle().layers) || [];
      const l = layers.find((x) => x.type === "symbol" && x.layout && x.layout["text-field"] && !x.id.startsWith(P));
      return l ? l.id : undefined;
    }
    function ensureLayers() {
      if (!map || destroyed || addingLayers) return;
      if (map.getSource(SRC) && map.getLayer(L.point)) return;
      addingLayers = true;
      try {
        if (!map.getSource(SRC)) map.addSource(SRC, { type: "geojson", data: C.featureCollection(mapItems()), promoteId: "cid" });
        const defs = layerDefs();
        const before = firstLabelLayer();
        for (const def of defs) {
          if (map.getLayer(def.id)) continue;
          map.addLayer(def, BELOW_LABELS.includes(def.id) ? before : undefined);
        }
        updateSelection();
      } catch (e) {
        // Style not loaded yet: the next styledata event retries. Partial layers are removed first.
        removeLayers();
      } finally { addingLayers = false; }
    }
    function removeLayers() {
      if (!map) return;
      for (const id of BELOW_LABELS.concat(ON_TOP)) { try { if (map.getLayer(id)) map.removeLayer(id); } catch (e) { /* style gone */ } }
      try { if (map.getSource(SRC)) map.removeSource(SRC); } catch (e) { /* style gone */ }
    }
    function updateMapData() {
      if (!map || destroyed) return;
      const src = map.getSource(SRC);
      if (src && src.setData) src.setData(C.featureCollection(mapItems()));
      else ensureLayers();
    }
    function updateSelection() {
      if (!map || destroyed || !map.getLayer(L.selPoint)) return;
      const id = st.selectedId || "\u0000none";
      try {
        map.setFilter(L.selPoint, ["all", ["==", ["geometry-type"], "Point"], ["==", ["get", "cid"], id]]);
        map.setFilter(L.selLine, ["all", ["!", ["==", ["geometry-type"], "Point"]], ["==", ["get", "cid"], id]]);
      } catch (e) { /* layer removed by a style switch */ }
    }
    function liveLayers() { return INTERACTIVE.filter((id) => map.getLayer(id)); }
    function hitAt(point) {
      const layers = liveLayers();
      if (!layers.length) return null;
      const box = [[point.x - 6, point.y - 6], [point.x + 6, point.y + 6]];
      const feats = map.queryRenderedFeatures(box, { layers });
      if (!feats.length) return null;
      const rank = (f) => (f.geometry && f.geometry.type === "Point" ? 0 : f.geometry && f.geometry.type === "LineString" ? 1 : 2);
      feats.sort((a, b) => rank(a) - rank(b));
      return feats[0].properties && feats[0].properties.cid;
    }
    function onMapClick(e) {
      if (destroyed) return;
      const id = hitAt(e.point);
      if (id) selectObject(id, { source: "map", fly: false });
    }
    function onMapMove(e) {
      lastHoverPoint = e;
      if (hoverRaf) return;
      hoverRaf = requestAnimationFrame(() => {
        hoverRaf = 0;
        if (destroyed || !lastHoverPoint) return;
        const ev = lastHoverPoint;
        const id = hitAt(ev.point);
        const canvas = map.getCanvas();
        if (id) { canvas.style.cursor = "pointer"; cursorSet = true; showTip(id, ev.lngLat); }
        else { if (cursorSet) { canvas.style.cursor = ""; cursorSet = false; } hideTip(); }
      });
    }
    function onMapOut() { if (cursorSet && map) { map.getCanvas().style.cursor = ""; cursorSet = false; } hideTip(); }
    function showTip(id, lngLat) {
      if (!window.maplibregl || !window.maplibregl.Popup || isMobile()) return;
      const it = findItem(id);
      if (!it) return;
      if (!popup) popup = new window.maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14, maxWidth: "280px", className: P + "tip" });
      const k = C.kindInfo(it.kind);
      const node = h("div", { class: P + "tip-body" },
        h("b", { text: it.title.length > 90 ? it.title.slice(0, 90) + "…" : it.title }),
        h("span", { text: k.label + " · " + C.STATUSES[it.status] }),
        it.evidence === "synthetic" ? h("span", { class: P + "tip-demo", text: "Демо-запись" }) : null,
        it.precision !== "source" ? h("span", { class: P + "muted", text: C.PRECISION[it.precision] }) : null);
      popup.setLngLat(lngLat).setDOMContent(node);
      if (!popup.isOpen || !popup.isOpen()) popup.addTo(map);
    }
    function hideTip() { if (popup) popup.remove(); }
    function onStyleData() { if (!destroyed && map && !map.getSource(SRC)) ensureLayers(); }
    function onMoveEnd() {
      if (!st.filters.area) return;
      clearTimeout(moveTimer);
      moveTimer = setTimeout(() => { updateViewBox(); renderList(); }, 120);
    }
    function updateViewBox() {
      if (!map) { st.viewBox = null; return; }
      try {
        const b = map.getBounds();
        st.viewBox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
      } catch (e) { st.viewBox = null; }
    }
    function freePadding() {
      const pad = Object.assign({}, basePadding);
      const c = map.getContainer().getBoundingClientRect();
      const r = root.getBoundingClientRect();
      if (r.width && r.height && layout === "overlay") {
        if (isMobile()) pad.bottom = Math.max(pad.bottom, c.bottom - r.top + 16);
        else if (r.left - c.left < c.width / 2) pad.left = Math.max(pad.left, r.right - c.left + 24);
        else pad.right = Math.max(pad.right, c.right - r.left + 24);
      }
      // Never ask MapLibre for more padding than the map has.
      const maxH = Math.max(0, c.width - 60), maxV = Math.max(0, c.height - 60);
      if (pad.left + pad.right > maxH) { const k = maxH / (pad.left + pad.right); pad.left = Math.floor(pad.left * k); pad.right = Math.floor(pad.right * k); }
      if (pad.top + pad.bottom > maxV) { const k = maxV / (pad.top + pad.bottom); pad.top = Math.floor(pad.top * k); pad.bottom = Math.floor(pad.bottom * k); }
      return pad;
    }
    function flyTo(it) {
      if (!map || destroyed || !it || !it.bbox) return;
      const [w, s, e, n] = it.bbox;
      const point = w === e && s === n;
      try {
        map.fitBounds([[w, s], [e, n]], {
          padding: freePadding(),
          maxZoom: point ? (it.precision === "source" ? 16 : 14.5) : 16.5,
          duration: reducedMotion() ? 0 : 900,
          bearing: map.getBearing(),
          pitch: map.getPitch(),
          essential: false,
        });
      } catch (e2) { /* camera can fail on a zero-size container; selection still works */ }
    }
    function attachMap(m) {
      if (destroyed) return;
      if (map === m) return;
      detachMap();
      if (!m || typeof m.addLayer !== "function") { map = null; syncFilterControls(); return; }
      const prev = byMap.get(m);
      if (prev && prev !== instance) { console.warn("CivicMap: another public map was mounted on this map; destroying it"); prev.destroy(); }
      map = m;
      byMap.set(m, instance);
      onMap("click", onMapClick);
      onMap("mousemove", onMapMove);
      onMap("mouseout", onMapOut);
      onMap("styledata", onStyleData);
      onMap("moveend", onMoveEnd);
      ensureLayers();
      updateViewBox();
      syncFilterControls();
    }
    function detachMap() {
      if (!map) return;
      for (const [type, fn] of mapHandlers.splice(0)) { try { map.off(type, fn); } catch (e) { /* ignore */ } }
      removeLayers();
      if (popup) { popup.remove(); popup = null; }
      if (cursorSet) { try { map.getCanvas().style.cursor = ""; } catch (e) { /* ignore */ } cursorSet = false; }
      if (hoverRaf) { cancelAnimationFrame(hoverRaf); hoverRaf = 0; }
      if (byMap.get(map) === instance) byMap.delete(map);
      map = null;
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      listSeq.cancel();
      cardSeq.cancel();
      clearTimeout(moveTimer);
      detachMap();
      destroyed = true;
      for (const f of cleanups.splice(0)) { try { f(); } catch (e) { /* ignore */ } }
      root.replaceChildren(...saved.children);
      root.className = saved.className;
      for (const a of ["role", "aria-label"]) {
        const v = a === "role" ? saved.role : saved.label;
        if (v === null) root.removeAttribute(a); else root.setAttribute(a, v);
      }
      root.removeAttribute("data-civic-r03-sheet");
      root.removeAttribute("data-civic-r03-view");
      root.removeAttribute("data-civic-r03-dragging");
      root.style.removeProperty("--civic-r03-drag-h");
    }

    const instance = {
      refresh,
      selectObject,
      destroy,
      // Optional extras for R01 (not part of civic-v1): late map binding, layout and state probes.
      setMap: attachMap,
      getLayout,
      layerIds: () => BELOW_LABELS.concat(ON_TOP),
      sourceId: SRC,
      getState: () => ({ list: st.list, count: st.items.length, selectedId: st.selectedId, view: st.view, detail: st.detail.state, filters: C.sanitizeFilters(st.filters), q: st.q, sheet: st.sheet }),
      setFilters: (f) => { st.filters = C.sanitizeFilters(Object.assign({}, st.filters, f)); filtersChanged(); },
    };

    st.sheet = isMobile() ? "peek" : "half";
    filters.open = !isMobile();
    applySheet();
    syncFilterControls();
    renderList();
    renderCard();
    attachMap(opt.map || null);
    if (opt.autoload !== false) refresh();
    if (permalink) { const id = readHash(); if (id) selectObject(id, { source: "permalink" }); }
    return instance;
  }

  window.CivicMap = { mount, version: "r03-round11-1", schema: "civic-v1" };
})();
