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
    lineCore: P + "line-core",
    synthLine: P + "synthetic-outline",
    selLine: P + "selected-line",
    pointHalo: P + "point-halo",
    pointSynth: P + "point-synthetic",
    point: P + "point",
    selPoint: P + "selected-point",
  };
  const BELOW_LABELS = [L.areaFill, L.areaLine, L.areaLineApprox, L.lineCasing, L.line, L.lineApprox, L.lineCore, L.synthLine, L.selLine];
  const ON_TOP = [L.pointHalo, L.pointSynth, L.point, L.selPoint];
  const INTERACTIVE = [L.point, L.pointHalo, L.line, L.lineApprox, L.lineCasing, L.areaFill];
  const STORAGE_KEY = "civic-r03:filters:v1";
  const HASH_KEY = "civic-object";
  const SVGNS = "http://www.w3.org/2000/svg";
  const MOBILE_QUERY = "(max-width: 760px)";
  const MAX_PAGES = 20;
  const PAGE_LIMIT = 100;
  const LIST_STEP = 200;
  const DEMO_IMG = P + "demo-ring";
  const byMap = new WeakMap();
  const byRoot = new WeakMap();
  let instanceCount = 0;

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

  // Dashed grey ring for synthetic points, drawn on a canvas because MapLibre circle strokes
  // cannot be dashed; the legend swatch shows the same dashed ring.
  function demoRingImage() {
    try {
      const ratio = 2, size = 32 * ratio, c = document.createElement("canvas");
      c.width = c.height = size;
      const ctx = c.getContext("2d");
      if (!ctx || typeof ctx.setLineDash !== "function") return null;
      const r = 13 * ratio, mid = size / 2;
      ctx.lineWidth = 4.5 * ratio; ctx.strokeStyle = "rgba(255,255,255,0.92)";
      ctx.beginPath(); ctx.arc(mid, mid, r, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([3.4 * ratio, 2.4 * ratio]); ctx.lineWidth = 2.2 * ratio; ctx.strokeStyle = "#374151";
      ctx.beginPath(); ctx.arc(mid, mid, r, 0, Math.PI * 2); ctx.stroke();
      const d = ctx.getImageData(0, 0, size, size);
      return { image: { width: size, height: size, data: new Uint8Array(d.data.buffer) }, ratio };
    } catch (e) { return null; }
  }

  function layerDefs(demoImage) {
    const kc = kindColorExpr();
    const isPoly = ["==", ["geometry-type"], "Polygon"];
    const isLine = ["==", ["geometry-type"], "LineString"];
    const isPoint = ["==", ["geometry-type"], "Point"];
    const exact = ["==", ["get", "exact"], true];
    const approx = ["!=", ["get", "exact"], true];
    const statusOpacity = (inProgress, planned, completed, other) =>
      ["match", ["get", "status"], "in_progress", inProgress, "planned", planned, "completed", completed, other];
    const none = ["==", ["get", "cid"], "\u0000none"];
    const lineColor = ["match", ["get", "status"], "cancelled", "#8b939c", "unknown", "#4f5965", kc];
    const lineWidth = ["match", ["get", "status"], "in_progress", 5, "planned", 6, "unknown", 6, 3.5];
    return [
      // Areas: planned/unknown without fill (like the hollow point), in progress filled, completed pale.
      { id: L.areaFill, type: "fill", source: SRC, filter: isPoly,
        paint: { "fill-color": ["match", ["get", "status"], "cancelled", "#8b939c", kc], "fill-opacity": ["match", ["get", "status"], "in_progress", 0.32, "completed", 0.12, "cancelled", 0.1, 0] } },
      { id: L.areaLine, type: "line", source: SRC, filter: ["all", isPoly, exact],
        paint: { "line-color": lineColor, "line-width": ["match", ["get", "status"], "planned", 2.5, "in_progress", 2, 1.5], "line-opacity": statusOpacity(0.95, 0.95, 0.6, 0.7) } },
      { id: L.areaLineApprox, type: "line", source: SRC, filter: ["all", isPoly, approx],
        paint: { "line-color": lineColor, "line-width": ["match", ["get", "status"], "planned", 2.5, "in_progress", 2, 1.5], "line-dasharray": [2, 1.6], "line-opacity": statusOpacity(0.95, 0.95, 0.6, 0.7) } },
      { id: L.lineCasing, type: "line", source: SRC, filter: isLine, layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.9 } },
      // Lines: planned/unknown are hollow (wide line + white core), in progress solid, completed thin and pale.
      { id: L.line, type: "line", source: SRC, filter: ["all", isLine, exact], layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": lineColor, "line-width": lineWidth, "line-opacity": statusOpacity(1, 1, 0.55, 0.8) } },
      { id: L.lineApprox, type: "line", source: SRC, filter: ["all", isLine, approx], layout: { "line-join": "round" },
        paint: { "line-color": lineColor, "line-width": lineWidth, "line-dasharray": [1.4, 1.1], "line-opacity": statusOpacity(1, 1, 0.55, 0.8) } },
      { id: L.lineCore, type: "line", source: SRC, filter: ["all", isLine, ["match", ["get", "status"], ["planned", "unknown"], true, false]],
        layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 2.2 } },
      { id: L.synthLine, type: "line", source: SRC, filter: ["all", ["!", isPoint], ["==", ["get", "synthetic"], true]],
        paint: { "line-color": "#4f5965", "line-width": 1.2, "line-gap-width": ["case", isLine, 12, 5], "line-dasharray": [1, 2], "line-opacity": 0.85 } },
      { id: L.selLine, type: "line", source: SRC, filter: ["all", ["!", isPoint], none], layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#152c26", "line-width": 3, "line-gap-width": ["case", isLine, 7, 0], "line-opacity": 0.95 } },
      { id: L.pointHalo, type: "circle", source: SRC, filter: ["all", isPoint, approx],
        paint: { "circle-radius": 18, "circle-color": kc, "circle-opacity": 0.13, "circle-stroke-color": kc, "circle-stroke-width": 1, "circle-stroke-opacity": 0.45, "circle-pitch-alignment": "map" } },
      demoImage
        ? { id: L.pointSynth, type: "symbol", source: SRC, filter: ["all", isPoint, ["==", ["get", "synthetic"], true]],
          layout: { "icon-image": DEMO_IMG, "icon-allow-overlap": true, "icon-ignore-placement": true, "icon-pitch-alignment": "viewport" } }
        : { id: L.pointSynth, type: "circle", source: SRC, filter: ["all", isPoint, ["==", ["get", "synthetic"], true]],
          paint: { "circle-radius": 13, "circle-opacity": 0, "circle-stroke-color": "#374151", "circle-stroke-width": 2 } },
      { id: L.point, type: "circle", source: SRC, filter: isPoint,
        paint: {
          "circle-radius": 7.5,
          "circle-color": ["match", ["get", "status"], "in_progress", kc, "completed", kc, "cancelled", "#a3aab3", "#ffffff"],
          "circle-opacity": ["match", ["get", "status"], "completed", 0.6, 1],
          "circle-stroke-color": ["match", ["get", "status"], "planned", kc, "in_progress", "#ffffff", "completed", "#ffffff", "#4f5965"],
          "circle-stroke-width": ["match", ["get", "status"], "planned", 3, "unknown", 2.5, 2],
        } },
      // Outside the demo ring (r 13), so a selected demo point keeps its demo mark.
      { id: L.selPoint, type: "circle", source: SRC, filter: ["all", isPoint, none],
        paint: { "circle-radius": 17.5, "circle-opacity": 0, "circle-stroke-color": "#152c26", "circle-stroke-width": 3 } },
    ];
  }

  function mount(options) {
    const opt = options || {};
    if (!C) throw new Error("CivicMap: civic-map-core.js must be loaded before civic-map.js");
    const root = opt.root;
    if (!root || root.nodeType !== 1) throw new Error("CivicMap.mount: root element is required");
    if (!opt.api || typeof opt.api.request !== "function") throw new Error("CivicMap.mount: api.request(method, path, body) is required");
    // A second mount on the same root or map replaces the first one cleanly: the old instance
    // restores the root first, then this one captures it.
    const prevOnRoot = byRoot.get(root);
    if (prevOnRoot) prevOnRoot.destroy();
    const prevOnMap = opt.map && byMap.get(opt.map);
    if (prevOnMap && prevOnMap !== prevOnRoot) prevOnMap.destroy();
    const uid = P + (++instanceCount) + "-";
    const api = opt.api;
    const onSelect = typeof opt.onSelect === "function" ? opt.onSelect : null;
    const onFeedback = typeof opt.onFeedback === "function" ? opt.onFeedback : null;
    const now = typeof opt.now === "function" ? opt.now : () => new Date();
    // overlay: the module positions its own panel over the map (root is a direct child of <body>).
    // embedded: the host (R01 shell panel / sheet) positions and scrolls; we only fill the root.
    const layout = opt.layout === "embedded" || opt.layout === "overlay" ? opt.layout : (root.parentElement === document.body ? "overlay" : "embedded");
    const persist = opt.persistFilters !== false;
    const permalink = opt.permalink === true;
    const region = opt.region === null ? null : (Array.isArray(opt.region) ? opt.region : C.ASTANA_BBOX);
    // Defaults keep objects clear of the original topbar (bottom ≈ 96px) and map tools (right).
    const basePadding = Object.assign({ top: 130, right: 84, bottom: 48, left: 40 }, opt.mapPadding || {});
    const pathPrefix = typeof opt.pathPrefix === "string" ? opt.pathPrefix : "";
    const title = typeof opt.title === "string" && opt.title ? opt.title : "Что делают рядом";
    const fitOnLoad = opt.fitOnLoad === true;
    let fitted = false;

    let map = null;
    let destroyed = false;
    const mapHandlers = [];
    const cleanups = [];
    const listSeq = C.createSequence();
    const cardSeq = C.createSequence();
    const aborters = { list: null, card: null };
    // R01 api.request accepts a 4th {signal} argument; other implementations ignore it.
    function freshSignal(kind) {
      if (aborters[kind]) { try { aborters[kind].abort(); } catch (e) { /* ignore */ } }
      aborters[kind] = typeof AbortController === "function" ? new AbortController() : null;
      return aborters[kind] ? aborters[kind].signal : undefined;
    }
    let popup = null, cursorSet = false, hoverRaf = 0, moveTimer = 0, lastHoverPoint = null, searchTimer = 0, layoutTimer = 0;
    let statusKey = null;
    const searchText = new Map();
    let addingLayers = false;

    const st = {
      items: [], excluded: 0, truncated: false,
      list: "idle", listError: null,
      filters: C.defaultFilters(), q: "",
      selectedId: null, view: "list",
      detail: { id: null, state: "idle", item: null, history: [], error: null },
      sheet: "peek", viewBox: null, limit: LIST_STEP, cameraPending: false,
      compare: { a: null, b: null }, pick: null,
    };
    if (persist) {
      try { const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null"); if (saved) st.filters = C.sanitizeFilters(saved); } catch (e) { /* storage blocked: defaults */ }
    }
    if (opt.filters) st.filters = C.sanitizeFilters(opt.filters);

    // ---------- root setup (restored in destroy) ----------
    const saved = { className: root.getAttribute("class"), role: root.getAttribute("role"), label: root.getAttribute("aria-label"), children: [...root.childNodes] };
    root.replaceChildren();
    root.classList.add(P + "root", P + "layout-" + layout);
    if (!saved.role) root.setAttribute("role", "region");
    if (!saved.label) root.setAttribute("aria-label", "Городские работы и события на карте");
    const mql = window.matchMedia ? window.matchMedia(MOBILE_QUERY) : null;
    const isMobile = () => !!(mql && mql.matches);

    // ---------- static skeleton ----------
    const handle = h("button", { type: "button", class: P + "handle", "data-r03-action": "sheet", "aria-label": "Развернуть панель наполовину", "aria-controls": uid + "scroll" }, h("span", { class: P + "grip", "aria-hidden": "true" }));
    const countEl = h("p", { class: P + "count", role: "status", "aria-live": "polite" });
    const demoNote = h("p", { class: P + "demo-note", hidden: true });
    const head = h("header", { class: P + "head" },
      h("div", { class: P + "head-row" }, h("h2", { class: P + "title", text: title }), h("span", { class: P + "city", text: "Астана" })),
      countEl, demoNote);

    const searchInput = h("input", { type: "search", class: P + "search", id: uid + "q", "data-r03-filter": "q", placeholder: "Название или описание", autocomplete: "off", "aria-label": "Поиск по названию и описанию", maxlength: "120" });
    const kindBox = h("div", { class: P + "chips", role: "group", "aria-label": "Вид работ" });
    const statusSel = h("select", { id: uid + "status", class: P + "select", "data-r03-filter": "status" },
      h("option", { value: "", text: "Все статусы" }), C.STATUS_ORDER.map((s) => h("option", { value: s, text: C.STATUSES[s] })));
    const periodSel = h("select", { id: uid + "period", class: P + "select", "data-r03-filter": "period" },
      Object.entries(C.PERIODS).map(([k, v]) => h("option", { value: k, text: v })));
    const fromInput = h("input", { type: "date", id: uid + "from", class: P + "date", "data-r03-filter": "from" });
    const toInput = h("input", { type: "date", id: uid + "to", class: P + "date", "data-r03-filter": "to" });
    const customBox = h("div", { class: P + "custom", hidden: true },
      h("label", { for: uid + "from" }, "с", fromInput), h("label", { for: uid + "to" }, "по", toInput));
    const areaBox = h("input", { type: "checkbox", id: uid + "area", "data-r03-filter": "area" });
    const evidenceSel = h("select", { id: uid + "evidence", class: P + "select", "data-r03-filter": "evidence" },
      Object.entries(C.EVIDENCE_FILTERS).map(([k, v]) => h("option", { value: k, text: v })));
    const pastBox = h("input", { type: "checkbox", id: uid + "past", "data-r03-filter": "hidePast" });
    const pills = h("div", { class: P + "pills", role: "group", "aria-label": "Активные фильтры" });
    const resetBtn = h("button", { type: "button", class: P + "link-btn", "data-r03-action": "reset-filters", text: "Сбросить фильтры" });
    const periodNote = h("p", { class: P + "hint" });
    const filtersSummary = h("summary", { class: P + "filters-summary" }, h("span", { text: "Фильтры" }), h("span", { class: P + "filters-active" }));
    const filters = h("details", { class: P + "filters" }, filtersSummary,
      h("div", { class: P + "filters-body" },
        h("label", { class: P + "field", for: uid + "q" }, h("span", { text: "Поиск" }), searchInput),
        h("div", { class: P + "field" }, h("span", { class: P + "field-label", id: uid + "kinds-label", text: "Вид" }), kindBox),
        h("div", { class: P + "two" },
          h("label", { class: P + "field", for: uid + "status" }, h("span", { text: "Статус" }), statusSel),
          h("label", { class: P + "field", for: uid + "period" }, h("span", { text: "Период по плану" }), periodSel)),
        customBox, periodNote,
        h("label", { class: P + "field", for: uid + "evidence" }, h("span", { text: "Сведения" }), evidenceSel),
        h("div", { class: P + "row" },
          h("label", { class: P + "check", for: uid + "area" }, areaBox, h("span", { text: "Только видимая часть карты" })),
          h("label", { class: P + "check", for: uid + "past" }, pastBox, h("span", { text: "Скрыть планы с прошедшим сроком" })),
          resetBtn)));
    kindBox.setAttribute("aria-labelledby", uid + "kinds-label");
    for (const k of C.KIND_ORDER) {
      kindBox.append(h("button", { type: "button", class: P + "chip", "data-r03-action": "toggle-kind", "data-kind": k, "aria-pressed": "false", style: { "--civic-r03-k": C.KINDS[k].color } },
        h("i", { class: P + "dot", "aria-hidden": "true" }), h("span", { text: C.KINDS[k].label }), h("span", { class: P + "chip-count" })));
    }

    const statusBox = h("div", { class: P + "state", "aria-live": "polite" });
    const listEl = h("ul", { class: P + "list", "aria-label": "Объекты" });
    const listNotes = h("div", { class: P + "list-notes" });
    const legend = buildLegend();
    const listView = h("section", { class: P + "list-view", "aria-label": "Список объектов" }, filters, pills, statusBox, listEl, listNotes, legend);
    const cardView = h("section", { class: P + "card", "aria-label": "Карточка объекта", hidden: true });
    const scroller = h("div", { class: P + "scroll", id: uid + "scroll" }, listView, cardView);
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
          h("p", { class: P + "legend-h", text: "Линии и участки — статус" }),
          h("ul", null,
            sample(P + "sw-line " + P + "sw-line-hollow", g, "Запланировано — полая линия, участок без заливки"),
            sample(P + "sw-line", g, "Идут работы — сплошная линия, залитый участок"),
            sample(P + "sw-line " + P + "sw-line-faded", g, "Завершено — тонкая бледная линия"),
            sample(P + "sw-line " + P + "sw-line-cancel", g, "Отменено — серая линия"),
            sample(P + "sw-line " + P + "sw-line-hollow " + P + "sw-line-unknown", g, "Статус неизвестен — серая полая линия")),
          h("p", { class: P + "legend-h", text: "Точность места" }),
          h("ul", null,
            sample(P + "sw-solid", g, "Сплошная линия, точка — место по источнику"),
            sample(P + "sw-halo", g, "Пунктир, ореол — примерное место"),
            sample(P + "sw-synth", g, "Серое пунктирное кольцо (у линий и участков — пунктирная обводка) — демо-запись")),
          h("p", { class: P + "hint", text: "Записи без координат есть только в списке: точку за них не придумываем." })));
    }

    let ownFocus = false;
    function focusEl(el, o) {
      if (!el) return;
      ownFocus = true;
      try { el.focus(o); } catch (e) { try { el.focus(); } catch (e2) { /* ignore */ } } finally { ownFocus = false; }
    }

    // ---------- listeners on root (delegated; removed in destroy) ----------
    function on(target, type, fn, o) { target.addEventListener(type, fn, o); cleanups.push(() => target.removeEventListener(type, fn, o)); }
    on(root, "click", onRootClick);
    on(root, "change", onRootChange);
    on(root, "input", onRootInput);
    on(root, "keydown", onRootKey);
    on(handle, "pointerdown", onHandleDown);
    // Keyboard focus entering a peeking sheet opens it, so the focused control is visible.
    on(scroller, "focusin", (e) => {
      // Only focus the user moved with the keyboard opens a peeking sheet; the module's own
      // focus restoration after a re-render must not undo a sheet the user just collapsed.
      if (ownFocus || !isMobile() || layout !== "overlay" || st.sheet !== "peek") return;
      let keyboard = true;
      try { keyboard = e.target.matches(":focus-visible"); } catch (err) { /* old browser: assume keyboard */ }
      if (keyboard) setSheet("half");
    });
    if (mql) {
      const f = () => { applySheet(); };
      if (mql.addEventListener) { mql.addEventListener("change", f); cleanups.push(() => mql.removeEventListener("change", f)); }
    }
    if (permalink) on(window, "hashchange", onHash);

    function onRootClick(e) {
      const t = e.target.closest("[data-r03-action]");
      if (!t || !root.contains(t)) return;
      const a = t.getAttribute("data-r03-action");
      const wasFocused = document.activeElement === t;
      handleAction(t, a);
      if (wasFocused && a !== "select" && a !== "back" && a !== "pick-cancel") keepFocus(t, a);
    }
    // If the activated control vanished in the re-render, put focus somewhere stable nearby.
    function keepFocus(t, a) {
      if (destroyed || (t.isConnected && !t.closest("[hidden]") && t.getClientRects().length)) return;
      let target = countEl;
      if (a === "reset-filters" || a === "show-undated") target = filters.open ? (a === "show-undated" ? periodSel : searchInput) : filtersSummary;
      else if (a === "more") target = listEl.querySelector("[data-r03-more-anchor]") || countEl;
      else if (a === "drop-filter") target = pills.querySelector("button") || filtersSummary;
      if (target === countEl) countEl.setAttribute("tabindex", "-1");
      focusEl(target);
    }
    function handleAction(t, a) {
      if (a === "select") {
        const fromPick = st.view === "pick";
        if (fromPick) st.pick = null;
        selectObject(t.getAttribute("data-id"), { source: fromPick ? "map" : "list" });
      }
      else if (a === "back") closeCard();
      else if (a === "retry-list") refresh();
      else if (a === "retry-card" && st.detail.id) loadDetail(st.detail.id);
      else if (a === "reset-filters") { st.filters = C.defaultFilters(); st.q = ""; searchInput.value = ""; clearTimeout(searchTimer); filtersChanged(); }
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
      else if (a === "area-off") { st.filters.area = false; filtersChanged(); }
      else if (a === "drop-filter") dropFilter(t.getAttribute("data-key"), t.getAttribute("data-value"));
      else if (a === "pick-cancel") closePick();
      else if (a === "pick-fit" && st.pick) fitIds(st.pick.ids);
      else if (a === "more") { st.limit += LIST_STEP; renderList(st.limit - LIST_STEP); }
    }
    function onRootChange(e) {
      const f = e.target.getAttribute && e.target.getAttribute("data-r03-filter");
      if (f === "q") { applySearch(); return; }
      if (f === "status") st.filters.statuses = e.target.value ? [e.target.value] : [];
      else if (f === "period") st.filters.period = e.target.value;
      else if (f === "from") st.filters.from = e.target.value || null;
      else if (f === "to") st.filters.to = e.target.value || null;
      else if (f === "area") { st.filters.area = !!e.target.checked; updateViewBox(); }
      else if (f === "evidence") st.filters.evidence = e.target.value;
      else if (f === "hidePast") st.filters.hidePast = !!e.target.checked;
      else if (e.target.getAttribute && e.target.getAttribute("data-r03-compare")) {
        st.compare[e.target.getAttribute("data-r03-compare")] = e.target.value ? +e.target.value : null;
        renderCompare();
        return;
      } else return;
      filtersChanged();
    }
    function onRootInput(e) {
      if (e.target !== searchInput) return;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(applySearch, 150);
    }
    function applySearch() {
      clearTimeout(searchTimer);
      if (destroyed) return;
      const q = searchInput.value.slice(0, 120);
      if (q === st.q) return;
      st.q = q;
      st.limit = LIST_STEP;
      syncFilterControls();
      renderList();
      updateMapData();
    }
    function onRootKey(e) {
      if (e.key === "Escape" && st.view === "card") { e.preventDefault(); closeCard(); }
      else if (e.key === "Escape" && st.view === "pick") { e.preventDefault(); closePick(); }
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
      // The label names what the next tap does; the cycle is peek -> half -> full -> peek.
      handle.setAttribute("aria-label", st.sheet === "peek" ? "Развернуть панель наполовину" : st.sheet === "half" ? "Развернуть панель полностью" : "Свернуть панель");
      handle.setAttribute("aria-expanded", String(st.sheet === "full"));
      handle.hidden = !isMobile() || layout !== "overlay";
      if (isMobile() && filters.open && st.sheet === "peek") filters.open = false;
      if (destroyed) return;
      if (st.filters.area && map) { clearTimeout(moveTimer); moveTimer = setTimeout(() => { if (!destroyed) { updateViewBox(); renderList(); } }, 320); }
      try { root.dispatchEvent(new CustomEvent("civic-r03:layout", { detail: getLayout() })); } catch (e) { /* old browsers */ }
    }
    function getLayout() {
      const r = root.getBoundingClientRect();
      return { mobile: isMobile(), sheet: st.sheet, view: st.view, rect: { left: r.left, top: r.top, width: r.width, height: r.height } };
    }

    // ---------- filters ----------
    function filtersChanged() {
      st.filters = C.sanitizeFilters(st.filters);
      st.limit = LIST_STEP;
      // setFilters({area:true}) from the host may come without any later map move: measure now.
      if (st.filters.area) updateViewBox();
      if (persist) { try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(st.filters)); } catch (e) { /* ignore */ } }
      syncFilterControls();
      renderList();
      updateMapData();
    }
    function today() { return C.localDay(now()); }
    function dropFilter(key, value) {
      const f = st.filters;
      if (key === "kind") f.kinds = f.kinds.filter((k) => k !== value);
      else if (key === "status") f.statuses = [];
      else if (key === "period") { f.period = "all"; f.from = null; f.to = null; }
      else if (key === "area") f.area = false;
      else if (key === "evidence") f.evidence = "all";
      else if (key === "hidePast") f.hidePast = false;
      else if (key === "q") { st.q = ""; searchInput.value = ""; clearTimeout(searchTimer); }
      filtersChanged();
    }
    // Removable summary of what is filtered, visible even with the filter box folded.
    function renderPills() {
      const f = st.filters, items = [];
      const pill = (key, value, text) => items.push(h("button", { type: "button", class: P + "pill", "data-r03-action": "drop-filter", "data-key": key, "data-value": value || "", "aria-label": "Убрать фильтр: " + text }, h("span", { text }), h("span", { class: P + "pill-x", "aria-hidden": "true", text: "×" })));
      if (st.q) pill("q", "", "«" + st.q + "»");
      for (const k of f.kinds) pill("kind", k, C.kindInfo(k).label);
      if (f.statuses.length) pill("status", f.statuses[0], C.STATUSES[f.statuses[0]]);
      if (f.period !== "all") {
        const r = C.periodRange(f.period, today(), { from: f.from, to: f.to });
        pill("period", "", f.period === "custom" ? (r.from ? "с " + C.formatDay(r.from) + " " : "") + (r.to ? "по " + C.formatDay(r.to) : "") || "свой период" : C.PERIODS[f.period]);
      }
      if (f.area) pill("area", "", "видимая часть карты");
      if (f.evidence !== "all") pill("evidence", "", C.EVIDENCE_FILTERS[f.evidence]);
      if (f.hidePast) pill("hidePast", "", "без прошедших планов");
      pills.replaceChildren(...items);
      pills.hidden = !items.length;
    }
    function syncFilterControls() {
      const f = st.filters;
      for (const b of kindBox.querySelectorAll("[data-kind]")) b.setAttribute("aria-pressed", String(f.kinds.includes(b.getAttribute("data-kind"))));
      statusSel.value = f.statuses[0] || "";
      periodSel.value = f.period;
      customBox.hidden = f.period !== "custom";
      fromInput.value = f.from || "";
      toInput.value = f.to || "";
      areaBox.checked = f.area;
      evidenceSel.value = f.evidence;
      pastBox.checked = f.hidePast;
      renderPills();
      areaBox.disabled = !map;
      const active = activeFilterCount();
      filtersSummary.lastChild.textContent = active ? "активно: " + active : "";
      resetBtn.hidden = !active;
      const r = C.periodRange(f.period, today(), { from: f.from, to: f.to });
      periodNote.textContent = r.from || r.to
        ? "Показаны записи, плановые сроки которых пересекают период" + (r.from ? " с " + C.formatDay(r.from) : "") + (r.to ? " по " + C.formatDay(r.to) : "") +
          ". Если одна из дат неизвестна, запись помечена. Это план, а не подтверждение, что работы идут."
        : "";
      periodNote.hidden = !periodNote.textContent;
    }
    const norm = (v) => String(v || "").toLocaleLowerCase("ru").replace(/ё/g, "е");
    function textOf(it) {
      let t = searchText.get(it.id);
      if (t === undefined) { t = norm(it.title) + "\n" + norm(it.description) + "\n" + norm(it.responsible.organization); searchText.set(it.id, t); }
      return t;
    }
    function searchPredicate() {
      const needle = norm(st.q).trim();
      return needle ? (it) => textOf(it).includes(needle) : null;
    }
    // st.items is sorted once per load, so filtering keeps a stable, cheap order.
    function filtered() {
      return C.applyFilters(st.items, st.filters, { today: today(), viewBox: st.filters.area ? st.viewBox : null, match: searchPredicate() });
    }
    // Map shows kind/status/period/search filters, never the viewport filter.
    function mapItems() {
      return C.applyFilters(st.items, st.filters, { today: today(), viewBox: null, match: searchPredicate() }).shown.map((r) => r.item);
    }

    // ---------- list ----------
    // The polite status region is rebuilt only when its meaning changes, so typing or panning
    // does not re-announce the same error or empty message.
    function setStatus(key, build) {
      if (key === statusKey) return;
      statusKey = key;
      const keep = document.activeElement && statusBox.contains(document.activeElement);
      statusBox.replaceChildren();
      if (build) statusBox.append(build());
      if (keep) { countEl.setAttribute("tabindex", "-1"); focusEl(countEl); }
    }
    function setCount(text) { if (countEl.textContent !== text) countEl.textContent = text; }
    // What the published list actually contains: demo vs records backed by a source (observed/derived).
    function coverage() {
      const c = { total: st.items.length, demo: 0, real: 0, other: 0 };
      for (const it of st.items) {
        if (it.evidence === "synthetic") c.demo++;
        else if (it.evidence === "observed" || it.evidence === "derived") c.real++;
        else c.other++;
      }
      return c;
    }
    function coverageText(c) {
      if (!c.total) return "Опубликованных записей пока нет.";
      if (!c.real) return "Подтверждённых реальных работ в нём пока нет, опубликовано " + plural(c.total, "запись", "записи", "записей") + (c.demo === c.total ? ", все демонстрационные." : ".");
      return "Записей с источником: " + c.real + " из " + c.total + ".";
    }
    function activeFilterCount() {
      const f = st.filters;
      return (f.kinds.length ? 1 : 0) + (f.statuses.length ? 1 : 0) + (f.period !== "all" ? 1 : 0) + (f.area ? 1 : 0) + (st.q ? 1 : 0) +
        (f.evidence !== "all" ? 1 : 0) + (f.hidePast ? 1 : 0);
    }
    function renderList(focusFrom) {
      if (destroyed) return;
      const focusedId = document.activeElement && listEl.contains(document.activeElement) ? document.activeElement.getAttribute("data-id") : null;
      const res = filtered();
      const c = res.counts;
      for (const b of kindBox.querySelectorAll("[data-kind]")) {
        const n = c.byKind[b.getAttribute("data-kind")] || 0;
        const t = st.list === "ready" ? String(n) : "";
        const el = b.querySelector("." + P + "chip-count");
        if (el.textContent !== t) el.textContent = t;
      }
      if (st.list === "ready") {
        for (const o of statusSel.options) if (o.value) o.textContent = C.STATUSES[o.value] + " (" + (c.byStatus[o.value] || 0) + ")";
        for (const o of evidenceSel.options) if (o.value !== "all") o.textContent = C.EVIDENCE_FILTERS[o.value] + " (" + (c.byEvidence[o.value] || 0) + ")";
      }
      const cov = coverage();
      demoNote.hidden = !cov.demo;
      demoNote.textContent = !cov.demo ? "" : cov.real === 0
        ? "Подтверждённых реальных работ в реестре пока нет: все " + plural(cov.total, "запись", "записи", "записей") + " — демонстрационные, не сведения о работах в городе."
        : "Демо-записей: " + cov.demo + ". Они отмечены «Демо» и не описывают реальные работы.";
      listEl.replaceChildren();
      listNotes.replaceChildren();
      listEl.setAttribute("aria-busy", String(st.list === "loading"));
      if (st.list === "loading" && !st.items.length) {
        setCount("Загружаем объекты…");
        setStatus("loading", () => h("div", { class: P + "loading", "aria-hidden": "true" }, h("span", { class: P + "spinner" }), "Загружаем опубликованные объекты…"));
        return;
      }
      const emptyFilter = st.items.length > 0 && !res.shown.length;
      const shownText = c.shown === c.total ? plural(c.total, "объект", "объекта", "объектов") : "Показано " + c.shown + " из " + c.total;
      // With "visible part" on (the shell turns it on when a street or district is chosen) an empty
      // result must not read as "no works here": the registry is incomplete.
      const areaEmpty = emptyFilter && st.filters.area;
      const emptyNode = () => areaEmpty
        ? h("div", { class: P + "empty" },
          h("p", { class: P + "empty-title", text: "В видимой части карты нет опубликованных записей." }),
          h("p", { class: P + "hint", text: "Это не значит, что здесь не ведутся работы: реестр неполный. " + coverageText(cov) }),
          h("div", { class: P + "row" },
            h("button", { type: "button", class: P + "btn", "data-r03-action": "area-off", text: "Показать записи по всему городу" }),
            activeFilterCount() > 1 ? h("button", { type: "button", class: P + "link-btn", "data-r03-action": "reset-filters", text: "Сбросить все фильтры" }) : null))
        : h("div", { class: P + "empty" }, h("p", { text: "По выбранным условиям ничего не найдено." }),
          h("button", { type: "button", class: P + "btn", "data-r03-action": "reset-filters", text: "Сбросить фильтры" }));
      const emptyKey = areaEmpty ? "empty-area" : "empty-filter";
      if (st.list === "error") {
        const text = st.listError ? st.listError.text : "Не удалось загрузить объекты.";
        setCount(st.items.length ? shownText + " · прежние данные" : "Данные не загружены");
        setStatus("error|" + text + "|" + (emptyFilter ? emptyKey : ""), () => {
          const box = h("div", null, h("div", { class: P + "error" },
            h("p", { text }), h("button", { type: "button", class: P + "btn", "data-r03-action": "retry-list" }, svgIcon(ICON.retry), "Повторить")));
          if (emptyFilter) box.append(emptyNode());
          return box;
        });
        if (!st.items.length) return;
      } else if (st.list === "ready" && !st.items.length) {
        setCount("0 объектов");
        setStatus("empty-server", () => h("div", { class: P + "empty" }, h("p", { text: "Опубликованных объектов пока нет." }),
          h("p", { class: P + "hint", text: "Когда сотрудники опубликуют работы или события, они появятся на карте и в этом списке." })));
        return;
      } else {
        if (st.list === "loading") setStatus("refreshing|" + (emptyFilter ? emptyKey : ""), () => { const box = h("div", null, h("p", { class: P + "hint", text: "Обновляем…" })); if (emptyFilter) box.append(emptyNode()); return box; });
        else setStatus(emptyFilter ? emptyKey : "", emptyFilter ? emptyNode : null);
        setCount(st.list === "idle" ? "" : shownText);
      }
      const frag = document.createDocumentFragment();
      const visible = res.shown.slice(0, st.limit);
      visible.forEach((row, i) => {
        const li = listItem(row.item, row.missing);
        if (focusFrom !== undefined && i === focusFrom) li.firstChild.setAttribute("data-r03-more-anchor", "");
        frag.append(li);
      });
      listEl.append(frag);
      const notes = [];
      if (res.shown.length > visible.length) notes.push(h("li", null, "Показаны первые " + visible.length + " из " + res.shown.length + ". ",
        h("button", { type: "button", class: P + "link-btn", "data-r03-action": "more", text: "Показать ещё " + Math.min(LIST_STEP, res.shown.length - visible.length) })));
      if (c.undated) notes.push(h("li", null, "Без плановых дат: " + c.undated + " (в выбранный период не входят). ", h("button", { type: "button", class: P + "link-btn", "data-r03-action": "show-undated", text: "Показать все сроки" })));
      if (c.partial) notes.push(h("li", { text: "С неполными сроками: " + c.partial + " — одна из плановых дат неизвестна; такие записи помечены." }));
      if (c.past) notes.push(h("li", null, "Скрыто планов с прошедшим сроком: " + c.past + ". ", h("button", { type: "button", class: P + "link-btn", "data-r03-action": "drop-filter", "data-key": "hidePast", text: "Показать" })));
      if (c.outsideArea) notes.push(h("li", { text: "Вне видимой части карты: " + c.outsideArea + "." }));
      if (c.noGeometry) notes.push(h("li", { text: "Без места на карте (не входят в «видимую часть»): " + c.noGeometry + "." }));
      if (c.mappedOut) {
        const rows = res.shown.filter((r) => !r.item.bbox);
        const absent = rows.filter((r) => !r.item.geoIssue).length, bad = rows.length - absent;
        if (absent) notes.push(h("li", { text: "Без координат: " + absent + " — есть только в списке, на карте не показаны." }));
        if (bad) notes.push(h("li", { text: "Координаты вне области карты или некорректны: " + bad + " — показаны только в списке." }));
      }
      if (st.truncated) notes.push(h("li", { text: "Записей загружено: " + st.items.length + "; остальные не показаны." }));
      if (st.excluded) notes.push(h("li", { text: "Пропущено некорректных или неопубликованных записей: " + st.excluded + "." }));
      if (notes.length) listNotes.append(h("ul", null, notes));
      if (focusedId) {
        const again = listEl.querySelector('[data-id="' + cssEscape(focusedId) + '"]');
        if (again) focusEl(again);
        else { countEl.setAttribute("tabindex", "-1"); focusEl(countEl); }
      } else if (focusFrom !== undefined) {
        const anchor = listEl.querySelector("[data-r03-more-anchor]");
        if (anchor) focusEl(anchor);
      }
    }
    function cssEscape(s) { return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&"); }
    function plural(n, a, b, c) { return n + " " + C.plural(n, a, b, c); }
    function badge(text, cls, title) { return h("span", { class: P + "badge " + (cls ? P + cls : ""), title: title || null, text }); }
    function evidenceBadge(it) {
      if (it.evidence === "observed") return badge("С источником", "b-ok", "Сведения из опубликованного источника");
      const info = C.evidenceInfo(it.evidence);
      return badge(info.short, it.evidence === "synthetic" ? "b-demo" : "b-warn", info.label);
    }
    function listItem(it, missing) {
      const k = C.kindInfo(it.kind);
      const iv = C.plannedInterval(it);
      const shift = C.scheduleShift(it);
      const stale = C.staleness(it, today());
      const when = iv.end ? "до " + C.formatDay(iv.end) : iv.start ? "с " + C.formatDay(iv.start) : "сроки: нет данных";
      const meta = [C.STATUSES[it.status], when];
      if (shift) meta.push(shift.days > 0 ? "срок перенесён" : "срок сдвинут раньше");
      const badges = [evidenceBadge(it),
        stale ? badge(stale.kind === "old_start_no_end" ? "Старый план без срока" : "Срок по плану прошёл", "b-warn") : null,
        !it.geometry ? badge("Нет на карте", "b-muted", it.geoIssue ? it.issues.find((x) => /координат|геометр/.test(x)) : "Координаты не указаны") : it.precision !== "source" ? badge(it.precision === "approximate" ? "Примерное место" : "Точность места?", "b-muted") : null,
        missing === "end" ? badge("Окончание неизвестно", "b-muted", "Плановая дата окончания не указана") : missing === "start" ? badge("Начало неизвестно", "b-muted", "Плановая дата начала не указана") : null].filter(Boolean);
      const btn = h("button", { type: "button", class: P + "item", "data-r03-action": "select", "data-id": it.id, "aria-current": st.selectedId === it.id ? "true" : null, style: { "--civic-r03-k": k.color } },
        h("span", { class: P + "item-kind" }, h("i", { class: P + "dot " + P + "st-" + it.status, "aria-hidden": "true" }), k.label),
        h("span", { class: P + "item-title", text: it.title }),
        h("span", { class: P + "item-meta", text: meta.join(" · ") }),
        badges.length ? h("span", { class: P + "badges" }, badges) : null);
      return h("li", null, btn);
    }

    // ---------- loading ----------
    async function request(method, path, signal) {
      const data = signal ? await api.request(method, pathPrefix + path, undefined, { signal }) : await api.request(method, pathPrefix + path, undefined);
      return C.unwrap(data);
    }
    async function refresh() {
      if (destroyed) return;
      const t = listSeq.next();
      const signal = freshSignal("list");
      st.list = "loading";
      st.listError = null;
      renderList();
      try {
        const raw = [];
        let cursor = null, pages = 0, truncated = false;
        // Ask for R02's largest page (limit 1-100, default 50) so 20 pages cover 2000 records; a server that
        // rejects the parameter (400/422 on the first page) is asked again without it.
        let limit = PAGE_LIMIT;
        do {
          const qs = [cursor ? "cursor=" + encodeURIComponent(cursor) : null, limit ? "limit=" + limit : null].filter(Boolean).join("&");
          let data;
          try {
            data = await request("GET", "/objects" + (qs ? "?" + qs : ""), signal);
          } catch (err) {
            const info = C.errorInfo(err);
            if (limit && !cursor && (info.status === 400 || info.status === 422)) { limit = 0; continue; }
            throw err;
          }
          if (destroyed || !listSeq.isCurrent(t)) return;
          const items = data && Array.isArray(data.items) ? data.items : Array.isArray(data) ? data : null;
          if (!items) throw Object.assign(new Error("bad payload"), { code: "bad_payload" });
          raw.push(...items);
          cursor = data && typeof data.next_cursor === "string" && data.next_cursor ? data.next_cursor : null;
          pages++;
          if (cursor && pages >= MAX_PAGES) { truncated = true; break; }
        } while (cursor);
        const norm = C.normalizeList(raw, { region });
        st.items = C.sortItems(norm.items);
        searchText.clear();
        st.excluded = norm.excluded.length;
        st.truncated = truncated;
        st.list = "ready";
        if (typeof opt.onData === "function") safeCall(opt.onData, st.items.map((item) => ({ evidence: item.evidence })));
        renderList();
        updateMapData();
        if (fitOnLoad && !fitted && !st.selectedId) fitted = fitAll();
        // Keep an open card in sync with the fresh list. A changed revision or an object that
        // left the public list is re-read from GET /objects/{id} (404 -> "не найден"), so the
        // history and the reason for a moved date always match the shown record.
        if (st.selectedId && st.detail.state !== "loading") {
          const fresh = findItem(st.selectedId), cur = st.detail.item;
          if (!fresh || !cur || fresh.revision !== cur.revision) loadDetail(st.selectedId, { fly: false, source: "refresh" });
          else { st.detail.item = fresh; renderCard(); }
        }
      } catch (err) {
        if (destroyed || !listSeq.isCurrent(t)) return;
        st.list = "error";
        st.listError = C.errorInfo(err, "list");
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
      id = String(id).slice(0, 200);
      // Clicking the object that is already open does not re-run the selection: no second
      // request, no second onSelect (the R01 shell would close an open feedback form).
      if (id === st.selectedId && (opts.source === "map" || opts.source === "list") && (st.detail.state === "ready" || st.detail.state === "loading")) {
        const it = currentItem();
        if (st.view !== "card") { st.view = "card"; renderCard(true); updateSelection(); }
        if (isMobile() && layout === "overlay" && st.sheet === "peek") setSheet("half");
        if (opts.source === "map") focusCard();
        if (it && opts.source === "list" && opts.fly !== false) afterLayout(() => flyTo(it), id);
        else if (it && opts.source === "map") afterLayout(() => ensureVisible(it), id);
        return;
      }
      const prevFocus = opts.source === "list" ? id : null;
      // Remember where the resident was in the list, to come back to the same place.
      if (st.view === "list") st.listScroll = scroller.scrollTop;
      st.selectedId = id;
      st.view = "card";
      st.compare = { a: null, b: null };
      const listed = findItem(id);
      st.detail = { id, state: "loading", item: listed, history: [], error: null, returnFocus: prevFocus };
      updateSelection();
      renderCard(opts.source === "list" || opts.source === "map" || opts.focus === true);
      if (isMobile() && layout === "overlay" && st.sheet === "peek") setSheet("half");
      if (permalink) writeHash(id);
      // onSelect first: a host that resizes its own sheet does so before we measure the free area.
      if (onSelect) safeCall(onSelect, publicCopy(listed) || { id }, { source: opts.source || "api" });
      if (listed && opts.fly !== false) afterLayout(() => (opts.source === "map" ? ensureVisible(listed) : flyTo(listed)), id);
      await loadDetail(id, opts);
    }
    // On phones the sheet animates its height; measure the free map area after it settles.
    function afterLayout(fn, id) {
      clearTimeout(layoutTimer);
      const run = () => {
        st.cameraPending = false;
        if (!destroyed && st.selectedId === id) fn();
      };
      if (!isMobile() || reducedMotion()) { st.cameraPending = false; run(); return; }
      st.cameraPending = true;
      layoutTimer = setTimeout(run, 320);
    }
    async function loadDetail(id, opts) {
      const t = cardSeq.next();
      const signal = freshSignal("card");
      st.detail.state = "loading";
      st.detail.error = null;
      renderCard();
      try {
        const data = await request("GET", "/objects/" + encodeURIComponent(id), signal);
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
          if (!hadItem && opts && opts.fly !== false) { const it = norm.item; afterLayout(() => (opts.source === "map" ? ensureVisible(it) : flyTo(it)), id); }
        }
      } catch (err) {
        if (destroyed || !cardSeq.isCurrent(t) || st.selectedId !== id) return;
        const info = C.errorInfo(err);
        st.detail.state = info.notFound ? "notfound" : "error";
        if (info.notFound) st.detail.item = null;
        else if (opts && opts.source === "refresh") { const f = findItem(id); if (f) { st.detail.item = f; st.detail.history = []; } }
        st.detail.error = info;
      }
      try { renderCard(); } finally { updateSelection(); }
    }
    // ---------- choosing among overlapping objects ----------
    function openPick(ids) {
      hideTip();
      st.pick = { ids: ids.slice(0, 50), more: Math.max(0, ids.length - 50), prevView: st.view, prevId: st.selectedId };
      st.view = "pick";
      if (isMobile() && layout === "overlay" && st.sheet === "peek") setSheet("half");
      renderCard(true);
      updateSelection();
    }
    function closePick(nextView) {
      if (!st.pick) return;
      const prev = st.pick;
      st.pick = null;
      st.view = nextView || (prev.prevView === "card" && prev.prevId ? "card" : "list");
      renderCard(st.view === "card");
      if (st.view === "list") { renderList(); countEl.setAttribute("tabindex", "-1"); focusEl(countEl); }
      updateSelection();
    }
    function renderPick(focus) {
      const p = st.pick;
      const ul = h("ul", { class: P + "list" });
      for (const id of p.ids) { const it = findItem(id); if (it) ul.append(listItem(it, null)); }
      cardView.append(
        h("div", { class: P + "card-top" },
          h("button", { type: "button", class: P + "btn " + P + "btn-quiet", "data-r03-action": "pick-cancel" }, svgIcon(ICON.back), "Отмена"),
          map ? h("button", { type: "button", class: P + "btn " + P + "btn-quiet", "data-r03-action": "pick-fit" }, svgIcon(ICON.pin), "Приблизить все") : null),
        h("h3", { class: P + "card-title", tabindex: "-1", text: "Здесь " + plural(p.ids.length, "объект", "объекта", "объектов") + " рядом" }),
        h("p", { class: P + "hint", text: "Они перекрывают друг друга на карте. Выберите нужный." + (p.more ? " Ещё " + p.more + " — приблизьте карту." : "") }),
        ul);
      if (focus) focusCard();
    }
    function fitIds(ids) {
      if (!map) return;
      const boxes = ids.map((id) => findItem(id)).filter((it) => it && it.bbox).map((it) => it.bbox);
      if (!boxes.length) return;
      const b = boxes.reduce((a, x) => [Math.min(a[0], x[0]), Math.min(a[1], x[1]), Math.max(a[2], x[2]), Math.max(a[3], x[3])]);
      try { map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: freePadding(), maxZoom: 17.5, duration: reducedMotion() ? 0 : 700, bearing: map.getBearing(), pitch: map.getPitch() }); } catch (e) { /* ignore */ }
    }

    function closeCard() {
      cardSeq.cancel();
      clearTimeout(layoutTimer);
      st.cameraPending = false;
      if (aborters.card) { try { aborters.card.abort(); } catch (e) { /* ignore */ } aborters.card = null; }
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
      if (typeof st.listScroll === "number") scroller.scrollTop = st.listScroll;
      if (target) focusEl(target, { preventScroll: true });
      else if (root.contains(document.activeElement) || document.activeElement === document.body) { countEl.setAttribute("tabindex", "-1"); focusEl(countEl); }
    }
    function safeCall(fn, ...args) { try { fn(...args); } catch (e) { console.error("CivicMap callback failed", e); } }

    // ---------- card ----------
    function dlRow(label, value, extra) {
      return [h("dt", { text: label }), h("dd", null, value === null || value === undefined || value === "" ? h("span", { class: P + "nodata", text: C.NO_DATA }) : value, extra || null)];
    }
    function renderCard(focus) {
      if (destroyed) return;
      // Re-rendering replaces nodes; keep keyboard focus where the user was.
      const active = document.activeElement;
      const keep = !focus && active && cardView.contains(active) ? (active.getAttribute("data-r03-action") || active.getAttribute("data-r03-compare") || "title") : null;
      root.setAttribute("data-civic-r03-view", st.view);
      listView.hidden = st.view !== "list";
      cardView.hidden = st.view === "list";
      cardView.replaceChildren();
      if (st.view === "pick") { renderPick(focus); return; }
      if (st.view !== "card") return;
      const d = st.detail;
      const it = d.item;
      const top = h("div", { class: P + "card-top" },
        h("button", { type: "button", class: P + "btn " + P + "btn-quiet", "data-r03-action": "back" }, svgIcon(ICON.back), "Все объекты"),
        it && it.geometry && map ? h("button", { type: "button", class: P + "btn " + P + "btn-quiet", "data-r03-action": "fly" }, svgIcon(ICON.pin), "На карте") : null);
      cardView.append(top);
      if (!it) {
        if (d.state === "loading") cardView.append(h("h3", { class: P + "card-title " + P + "sr", tabindex: "-1", text: "Карточка объекта" }), h("div", { class: P + "loading" }, h("span", { class: P + "spinner", "aria-hidden": "true" }), "Загружаем карточку…"));
        else if (d.state === "notfound") cardView.append(h("div", { class: P + "empty", role: "alert" }, h("h3", { class: P + "card-title", tabindex: "-1", text: "Объект не найден" }), h("p", { text: "Возможно, его сняли с публикации или ссылка устарела." })));
        else if (d.state === "error") cardView.append(h("h3", { class: P + "card-title " + P + "sr", tabindex: "-1", text: "Карточка объекта" }), h("div", { class: P + "error", role: "alert" }, h("p", { text: d.error ? d.error.text : "Не удалось загрузить карточку." }), h("button", { type: "button", class: P + "btn", "data-r03-action": "retry-card" }, svgIcon(ICON.retry), "Повторить")));
        if (focus) focusCard();
        else if (keep) restoreFocus("title");
        return;
      }
      const k = C.kindInfo(it.kind);
      const ev = C.evidenceInfo(it.evidence);
      const statusSrc = it.sourceRefs.find((r) => r.published_on && r.fields.includes("status"));
      if (it.evidence !== "observed") {
        cardView.append(h("p", { class: P + "banner " + (it.evidence === "synthetic" ? P + "banner-demo" : P + "banner-warn"), role: "note" },
          it.evidence === "synthetic" ? h("b", { text: "Демо. " }) : null, ev.label + "."));
      }
      cardView.append(
        h("div", { class: P + "card-kind", style: { "--civic-r03-k": k.color } }, h("i", { class: P + "dot " + P + "st-" + it.status, "aria-hidden": "true" }), k.label + (it.kind === "other" && it.rawKind ? " (" + it.rawKind.slice(0, 40) + ")" : "")),
        h("h3", { class: P + "card-title", tabindex: "-1", text: it.title }));

      // ---- "Коротко": what, until when, who, from where — before anything technical ----
      const s = it.schedule;
      const shift = C.scheduleShift(it);
      const stale = C.staleness(it, today());
      const resp = C.responsibleView(it);
      const prov = C.provenanceLine(it);
      let whenText;
      if (s.actual_end) whenText = "завершено " + C.formatDay(s.actual_end, "long");
      else if (it.status === "cancelled") whenText = "отменено" + (s.current_planned_end ? " (план был до " + C.formatDay(s.current_planned_end, "long") + ")" : "");
      else if (s.current_planned_end) whenText = "до " + C.formatDay(s.current_planned_end, "long") + " (по плану)";
      else if (s.original_planned_end) whenText = "новый срок не опубликован (изначально до " + C.formatDay(s.original_planned_end, "long") + ")";
      else whenText = "срок окончания не указан";
      const summary = h("dl", { class: P + "summary", "aria-label": "Коротко об объекте" },
        h("dt", { text: "Сейчас" }),
        h("dd", null, h("span", { class: P + "status " + P + "status-" + it.status, text: C.STATUSES[it.status] }),
          statusSrc ? h("span", { class: P + "muted", text: " по источнику от " + C.formatDay(statusSrc.published_on) }) : h("span", { class: P + "muted", text: " по записи" }),
          stale ? h("span", { class: P + "warn-text", text: " · срок по плану уже прошёл" }) : null),
        h("dt", { text: "Когда закончат" }),
        h("dd", null, h("span", { text: whenText }),
          shift && !s.actual_end ? h("span", { class: P + "shift-chip", text: (shift.days > 0 ? "перенесён на " : "сдвинут раньше на ") + C.daysText(shift.days) }) : null),
        h("dt", { text: "Кто отвечает" }),
        h("dd", null, resp.show
          ? h("span", null, [resp.organization, resp.contact].filter(Boolean).join(" · "), h("span", { class: P + "muted", text: " — по источнику" }))
          : h("span", { class: P + "nodata", text: resp.state === "unsourced" ? "не подтверждено источником" : "не указано" })),
        h("dt", { text: "Откуда сведения" }),
        h("dd", null, h("span", { class: prov.state === "ok" ? null : P + "nodata", text: prov.text })));
      cardView.append(summary);

      // Moved deadline with its reason, right under the summary.
      const reasonInfo = C.shiftReason(d.history);
      if (shift) {
        const dir = shift.days > 0 ? "позже" : "раньше";
        let reasonText;
        if (reasonInfo && reasonInfo.reason) reasonText = h("span", null, "Причина: «" + reasonInfo.reason + "»", reasonInfo.at ? " · " + C.formatTimestamp(reasonInfo.at) : "");
        else if (d.state === "loading") reasonText = h("span", { class: P + "muted", text: "Причина: загружаем историю…" });
        else if (d.state === "error") reasonText = h("span", { class: P + "muted", text: "Причина: история не загрузилась." });
        else reasonText = h("span", { class: P + "muted", text: "Причина переноса в опубликованной истории не указана." });
        cardView.append(h("div", { class: P + "shift", role: "note" },
          h("b", { text: "Срок перенесён на " + C.daysText(shift.days) + " " + dir + ": " }),
          h("span", { text: C.formatDay(shift.from) + " → " + C.formatDay(shift.to) }), h("br"), reasonText));
      }
      if (stale) {
        const st0 = "«" + C.STATUSES[it.status] + "»";
        const text = stale.kind === "old_start_no_end"
          ? "Начало по плану — " + C.formatDay(stale.start) + " (" + C.daysText(stale.days) + " назад), срок окончания не опубликован, в записи статус " + st0 + "."
          : stale.original
            ? "Первоначальный срок окончания (" + C.formatDay(stale.end) + ") прошёл " + C.daysText(stale.days) + " назад, новый срок не опубликован, в записи статус " + st0 + "."
            : "Плановый срок окончания (" + C.formatDay(stale.end) + ") прошёл " + C.daysText(stale.days) + " назад, а в записи статус " + st0 + ".";
        cardView.append(h("p", { class: P + "banner " + P + "banner-warn", role: "note" }, text + " Фактическое состояние работ эта запись не подтверждает."));
      }
      if (it.description) cardView.append(h("section", { class: P + "sec" }, h("h4", { text: "Назначение" }), h("p", { class: P + "desc", text: it.description })));

      // Dates: originally / now / actually.
      const iv = C.plannedInterval(it);
      cardView.append(h("section", { class: P + "sec" }, h("h4", { text: "Сроки" }),
        h("dl", { class: P + "dl" },
          dlRow("Начало по плану", s.planned_start ? C.formatDay(s.planned_start, "long") : null),
          dlRow("Изначально — до", s.original_planned_end ? C.formatDay(s.original_planned_end, "long") : null),
          dlRow("Сейчас — до", s.current_planned_end ? C.formatDay(s.current_planned_end, "long") : (s.original_planned_end ? "новый срок не опубликован" : null)),
          dlRow("Фактически", s.actual_end ? "завершено " + C.formatDay(s.actual_end, "long") : null)),
        !iv.complete ? h("p", { class: P + "hint", text: "Плановый интервал неполный: неизвестную дату не заменяем сегодняшней." }) : null));

      // Money and responsible: shown only when a source covers them.
      const cost = C.costView(it);
      const costNode = cost.show
        ? h("span", null, h("b", { class: P + "num", text: cost.text }), cost.approx ? h("span", { class: P + "muted", text: " " + cost.approx }) : null,
          h("span", { class: P + "basis", text: cost.basisLabel + " · источник: " + (cost.source.publisher || cost.source.host || cost.source.id) }))
        : h("span", { class: P + "nodata", text: cost.text });
      const respNode = resp.show
        ? h("span", null, resp.organization ? h("span", { text: resp.organization }) : null, resp.contact ? h("span", { class: P + "basis", text: resp.contact }) : null,
          h("span", { class: P + "basis", text: "источник: " + (resp.source.publisher || resp.source.host || resp.source.id) }))
        : h("span", { class: P + "nodata", text: resp.state === "unsourced" ? "в записи указан, но источник не подтверждает — не показываем" : C.NO_DATA });
      cardView.append(h("section", { class: P + "sec" }, h("h4", { text: "Кто отвечает и сколько стоит" }),
        h("dl", { class: P + "dl" }, dlRow("Ответственный", respNode), dlRow("Стоимость", costNode))));

      // Place
      let placeText;
      if (!it.geometry) placeText = it.issues.find((x) => /координат|геометр/.test(x)) ? "Место не показано: " + it.issues.find((x) => /координат|геометр/.test(x)) + "." : "Координаты не указаны — объект есть только в списке, точку не придумываем.";
      else placeText = C.PRECISION[it.precision] + ". " + ({ Point: "Точка", LineString: "Линия (участок)", Polygon: "Территория" }[it.geometry.type] || "") + ".";
      cardView.append(h("section", { class: P + "sec" }, h("h4", { text: "Место" }), h("p", { text: placeText })));

      // Sources: short list first; technical provenance folded away.
      const srcSec = h("section", { class: P + "sec" }, h("h4", { text: "Источники" }));
      if (!it.sourceRefs.length) srcSec.append(h("p", { class: P + "nodata", text: prov.text }));
      else {
        const ul = h("ul", { class: P + "sources" });
        for (const r of it.sourceRefs) {
          const name = r.publisher || r.host || "Источник";
          const link = r.url ? h("a", { href: r.url, target: "_blank", rel: "noopener noreferrer nofollow", class: P + "src-link" }, name, svgIcon(ICON.out, 14), h("span", { class: P + "sr", text: " (откроется в новой вкладке)" })) : h("span", { text: name });
          ul.append(h("li", null, link, r.published_on ? h("span", { class: P + "muted", text: " · " + C.formatDay(r.published_on) }) : null,
            r.rawUrlRejected ? h("span", { class: P + "warn-text", text: " · ссылка скрыта: небезопасный адрес" }) : null));
        }
        srcSec.append(ul);
      }
      const tech = h("div", { class: P + "tech-body" });
      for (const r of it.sourceRefs) {
        const meta = [];
        if (r.retrieved_at) meta.push("получено " + (C.parseTimestamp(r.retrieved_at) ? C.formatTimestamp(r.retrieved_at) : C.formatDay(r.retrieved_at)));
        if (r.access_status) meta.push(C.ACCESS[r.access_status]);
        meta.push(r.license ? "лицензия: " + r.license : "лицензия не указана");
        tech.append(h("p", null, h("b", { text: (r.publisher || r.host || r.id) + ": " }), meta.join(" · "),
          r.fields.length ? h("span", { class: P + "src-meta", text: "подтверждает: " + [...new Set(r.fields.map(C.fieldLabel))].join(", ") }) : h("span", { class: P + "src-meta", text: "не указано, какие поля подтверждает" })));
      }
      tech.append(h("p", { text: "Тип сведений: " + ev.label + "." }));
      if (it.evidenceNotes) tech.append(h("p", { class: P + "notes" }, h("b", { text: "Примечание: " }), it.evidenceNotes));
      if (it.issues.length) tech.append(h("p", { class: P + "warn-text", text: "Проблемы записи: " + it.issues.join("; ") + "." }));
      tech.append(h("p", { class: P + "meta", text: "Запись обновлена: " + (it.updatedAt ? C.formatTimestamp(it.updatedAt) : C.NO_DATA) + (it.revision ? " · редакция " + it.revision : "") }));
      srcSec.append(h("details", { class: P + "tech" }, h("summary", { text: "Подробнее о сведениях" }), tech));
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
      actions.append(h("button", { type: "button", class: P + "btn", "data-r03-action": "copy-link" }, svgIcon(ICON.link), "Скопировать ссылку"));
      if (actions.childNodes.length) cardView.append(actions);
      if (focus) focusCard();
      else if (keep) restoreFocus(keep);
    }
    function restoreFocus(key) {
      const el = key === "title" ? null : cardView.querySelector('[data-r03-action="' + key + '"], [data-r03-compare="' + key + '"]');
      const t = el || cardView.querySelector("." + P + "card-title");
      if (t) focusEl(t, { preventScroll: true });
    }
    function touches(r) { return r.changed.some((c) => c.field.startsWith("schedule")); }
    function valueText(field, v) {
      if (v === null || v === undefined) return C.NO_DATA;
      if (typeof v === "string" && C.parseDay(v)) return C.formatDay(v);
      if (field === "status" && typeof v === "string" && Object.prototype.hasOwnProperty.call(C.STATUSES, v)) return C.STATUSES[v];
      if (typeof v === "number") return C.formatNumber(v);
      if (typeof v === "string") return v.length > 80 ? v.slice(0, 80) + "…" : v;
      return "изменено";
    }
    let compareOut = null;
    function compareBlock(rows) {
      const revs = rows.filter((r) => r.revision !== null);
      const mk = (key, label) => {
        const sel = h("select", { class: P + "select", "data-r03-compare": key, id: uid + "cmp-" + key }, h("option", { value: "", text: "—" }),
          revs.map((r) => h("option", { value: String(r.revision), text: "ред. " + r.revision + (C.timestampDay(r.at) ? " · " + C.formatDay(C.timestampDay(r.at)) : "") })));
        if (st.compare[key]) sel.value = String(st.compare[key]);
        return h("label", { class: P + "field", for: uid + "cmp-" + key }, h("span", { text: label }), sel);
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
      if (t) focusEl(t, { preventScroll: true });
      scroller.scrollTop = 0;
      if (layout === "embedded") { try { cardView.scrollIntoView({ block: "start", behavior: "auto" }); } catch (e) { /* ignore */ } }
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
    // Link to the open card. Default format is the R01 shell's "#object=<id>"; a host may pass linkFor(id).
    function objectLink(id) {
      if (typeof opt.linkFor === "function") { try { const u = opt.linkFor(id); if (typeof u === "string" && u) return u; } catch (e) { /* fall back */ } }
      const l = window.location;
      return l.origin + l.pathname + l.search + "#" + (permalink ? HASH_KEY : "object") + "=" + encodeURIComponent(id);
    }
    function copyLink(btn) {
      const id = st.selectedId;
      if (!id) return;
      const url = objectLink(id);
      const box = btn.parentElement;
      const say = (text, showField) => {
        let note = box.querySelector("." + P + "copy-note");
        if (!note) { note = h("p", { class: P + "copy-note", role: "status" }); box.append(note); }
        note.replaceChildren(text);
        if (showField) {
          const field = h("input", { type: "text", readonly: true, class: P + "search", value: url, "aria-label": "Ссылка на объект" });
          note.append(field);
          field.select();
        }
      };
      try {
        navigator.clipboard.writeText(url).then(() => say("Ссылка скопирована.", false), () => say("Скопируйте ссылку:", true));
      } catch (e) { say("Скопируйте ссылку:", true); }
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
        let demo = map.hasImage(DEMO_IMG);
        if (!demo) {
          const img = demoRingImage();
          if (img) { map.addImage(DEMO_IMG, img.image, { pixelRatio: img.ratio }); demo = true; }
        }
        const defs = layerDefs(demo);
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
      try { if (map.hasImage(DEMO_IMG)) map.removeImage(DEMO_IMG); } catch (e) { /* style gone */ }
    }
    function updateMapData() {
      if (!map || destroyed) return;
      const src = map.getSource(SRC);
      if (src && src.setData) src.setData(C.featureCollection(mapItems()));
      else ensureLayers();
    }
    function updateSelection() {
      if (!map || destroyed || !map.getLayer(L.selPoint)) return;
      // While choosing among overlapping objects, all candidates are outlined.
      const ids = st.view === "pick" && st.pick ? st.pick.ids : [st.selectedId || "\u0000none"];
      const inIds = ["in", ["get", "cid"], ["literal", ids]];
      try {
        map.setFilter(L.selPoint, ["all", ["==", ["geometry-type"], "Point"], inIds]);
        map.setFilter(L.selLine, ["all", ["!", ["==", ["geometry-type"], "Point"]], inIds]);
      } catch (e) { /* layer removed by a style switch */ }
    }
    function liveLayers() { return INTERACTIVE.filter((id) => map.getLayer(id)); }
    // All distinct objects under the pointer: points first, then lines, then areas (smallest first).
    function hitIds(point) {
      const layers = liveLayers();
      if (!layers.length) return [];
      const r = isMobile() ? 11 : 7;
      const feats = map.queryRenderedFeatures([[point.x - r, point.y - r], [point.x + r, point.y + r]], { layers });
      const rank = (f) => (f.geometry && f.geometry.type === "Point" ? 0 : f.geometry && f.geometry.type === "LineString" ? 1 : 2);
      // Among overlapping areas the smallest wins, so a small area inside a big one stays pickable.
      const area = (f) => { const it = findItem(f.properties && f.properties.cid); const b = it && it.bbox; return b ? (b[2] - b[0]) * (b[3] - b[1]) : Infinity; };
      feats.sort((a, b) => rank(a) - rank(b) || (rank(a) === 2 ? area(a) - area(b) : 0));
      const ids = [];
      for (const f of feats) { const id = f.properties && f.properties.cid; if (id && !ids.includes(id) && findItem(id)) ids.push(id); }
      return ids;
    }
    function hitAt(point) { return hitIds(point)[0] || null; }
    // One object -> open it. Several on top of each other -> let the resident choose in the panel.
    function onMapClick(e) {
      if (destroyed) return;
      const ids = hitIds(e.point);
      if (ids.length === 1) selectObject(ids[0], { source: "map" });
      else if (ids.length > 1) openPick(ids);
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
    let styleRaf = 0;
    function onStyleData() {
      if (destroyed || !map || map.getSource(SRC) || styleRaf) return;
      styleRaf = requestAnimationFrame(() => { styleRaf = 0; if (!destroyed && map && !map.getSource(SRC)) ensureLayers(); });
    }
    function onMoveEnd() {
      if (!st.filters.area) return;
      clearTimeout(moveTimer);
      moveTimer = setTimeout(() => { updateViewBox(); renderList(); }, 120);
    }
    // "Visible part" = the map canvas minus the panel or sheet that covers it.
    function updateViewBox() {
      if (!map) { st.viewBox = null; return; }
      try {
        const c = map.getContainer().getBoundingClientRect();
        const ob = obstruction();
        const r = ob ? ob.getBoundingClientRect() : null;
        let l = 0, t = 0, rt = c.width, b = c.height;
        if (r && r.width && r.height) {
          if (isMobile()) b = Math.min(b, Math.max(0, r.top - c.top));
          else if (r.left - c.left < c.width / 2) l = Math.max(l, r.right - c.left);
          else rt = Math.min(rt, r.left - c.left);
        }
        if (rt - l < 24 || b - t < 24) { l = 0; t = 0; rt = c.width; b = c.height; }
        const pts = [[l, t], [rt, t], [l, b], [rt, b]].map((p) => map.unproject(p));
        const xs = pts.map((p) => p.lng), ys = pts.map((p) => p.lat);
        st.viewBox = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
      } catch (e) { st.viewBox = null; }
    }
    // Pan just enough that an object chosen on the map is not left under the panel or sheet.
    function ensureVisible(it) {
      if (!map || destroyed || !it || !it.bbox) return;
      const c = map.getContainer().getBoundingClientRect();
      const pad = freePadding();
      const free = { l: c.left + pad.left, t: c.top + pad.top, r: c.right - pad.right, b: c.bottom - pad.bottom };
      let p;
      try { p = map.project([(it.bbox[0] + it.bbox[2]) / 2, (it.bbox[1] + it.bbox[3]) / 2]); } catch (e) { return; }
      const x = c.left + p.x, y = c.top + p.y;
      if (x >= free.l && x <= free.r && y >= free.t && y <= free.b) return;
      try { map.panBy([x - (free.l + free.r) / 2, y - (free.t + free.b) / 2], { duration: reducedMotion() ? 0 : 350 }); } catch (e) { /* ignore */ }
    }
    // The panel that covers the map: our root in overlay mode, or the host's positioned
    // panel (outermost absolute/fixed ancestor) when embedded in the R01 shell.
    function obstruction() {
      let found = null;
      for (let n = root; n && n !== document.body && n.nodeType === 1; n = n.parentElement) {
        const pos = window.getComputedStyle(n).position;
        if (pos === "absolute" || pos === "fixed") found = n;
      }
      return found;
    }
    function freePadding() {
      // Phones: the topbar ends near 72-84px and the tool column is ~50px wide.
      const pad = Object.assign({}, basePadding, isMobile() && !opt.mapPadding ? { top: 84, right: 60, left: 16 } : null);
      const c = map.getContainer().getBoundingClientRect();
      const ob = obstruction();
      const r = ob ? ob.getBoundingClientRect() : { width: 0, height: 0 };
      if (r.width && r.height && !opt.mapPadding) {
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
    // Fit every mapped object (current filters) into the part of the map not covered by the panel.
    function fitAll() {
      if (!map || destroyed) return false;
      const boxes = mapItems().map((it) => it.bbox).filter(Boolean);
      if (!boxes.length) return false;
      const b = boxes.reduce((a, x) => [Math.min(a[0], x[0]), Math.min(a[1], x[1]), Math.max(a[2], x[2]), Math.max(a[3], x[3])]);
      try {
        map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: freePadding(), maxZoom: 14, duration: reducedMotion() ? 0 : 700, bearing: map.getBearing(), pitch: map.getPitch() });
      } catch (e) { return false; }
      return true;
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
      if (styleRaf) { cancelAnimationFrame(styleRaf); styleRaf = 0; }
      if (byMap.get(map) === instance) byMap.delete(map);
      map = null;
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      listSeq.cancel();
      cardSeq.cancel();
      for (const k of ["list", "card"]) if (aborters[k]) { try { aborters[k].abort(); } catch (e) { /* ignore */ } aborters[k] = null; }
      clearTimeout(moveTimer);
      clearTimeout(searchTimer);
      clearTimeout(layoutTimer);
      detachMap();
      if (byRoot.get(root) === instance) byRoot.delete(root);
      for (const f of cleanups.splice(0)) { try { f(); } catch (e) { /* ignore */ } }
      root.replaceChildren(...saved.children);
      for (const a of ["class", "role", "aria-label"]) {
        const v = a === "class" ? saved.className : a === "role" ? saved.role : saved.label;
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
      fitAll,
      getLayout,
      layerIds: () => BELOW_LABELS.concat(ON_TOP),
      sourceId: SRC,
      getState: () => ({ list: st.list, count: st.items.length, selectedId: st.selectedId, view: st.view, detail: st.detail.state, filters: C.sanitizeFilters(st.filters), q: st.q, sheet: st.sheet, cameraPending: st.cameraPending }),
      setFilters: (f) => { st.filters = C.sanitizeFilters(Object.assign({}, st.filters, f)); filtersChanged(); },
    };

    byRoot.set(root, instance);
    st.sheet = isMobile() ? "peek" : "half";
    filters.open = false;
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
