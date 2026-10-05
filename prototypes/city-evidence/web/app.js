/* «Городские данные: Шымкент / Астана» — demo viewer.
 * Based on the K07 round-3 prototype (claude/save-work-handoff-ku3ej3 @ 6778ded, prototype/app.js):
 * projection, markers, pan/zoom and the card layout are taken from it; data model switched to the
 * K10 round-3 compact squares (window.CITY_EVIDENCE from data.js, built by tools/build_data.py).
 * Strings from data are inserted with textContent only. No network, no API key.
 * Straight-line distance only; no walking times, isochrones or "unreachable" claims.
 */
(function () {
  "use strict";
  const SVGNS = "http://www.w3.org/2000/svg";
  const $ = (id) => document.getElementById(id);
  const D = window.CITY_EVIDENCE;
  const F = window.CITY_FACTS || null;  // optional stage-2 module (facts.js)
  const X = window.CITY_WHATIF || null;  // round-7 «Если добавить объект» (whatif.js), needs facts.js for the snapshot

  function el(tag, attrs, text) {
    const e = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function sv(tag, attrs) {
    const e = document.createElementNS(SVGNS, tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
    return e;
  }

  // ---------- error state: data missing / broken ----------
  function fatal(title, lines) {
    const main = document.querySelector("main");
    main.replaceChildren();
    const box = el("div", { class: "card err", role: "alert" });
    box.append(el("h2", null, title));
    for (const l of lines) box.append(typeof l === "string" ? el("p", null, l) : l);
    main.append(box);
    document.querySelector(".toolbar").hidden = true;
  }
  if (!D || !D.cities || !Object.keys(D.cities).length) {
    fatal("Данные не найдены", ["Файл web/data.js отсутствует или повреждён. Соберите его из сохранённых входов:",
      el("code", null, "python3 tools/build_data.py")]);
    return;
  }

  // evidence.js must belong to this data.js; otherwise districts / facts are not used (shown as a warning).
  window.CITY_EVIDENCE_PROBLEMS = F && F.evidenceProblems && window.CITY_OBS ? F.evidenceProblems(D, window.CITY_OBS) : [];
  if (window.CITY_EVIDENCE_PROBLEMS.length) {
    const b = $("banner");
    b.append(el("p", { class: "err", role: "alert" }, "Внимание: evidence.js не совпадает с data.js (другая версия данных или устарел) — районы и каталог фактов не показываются. "
      + window.CITY_EVIDENCE_PROBLEMS.join("; ")));
  }
  const SHAPES = { school: "circle", outpatient_clinic: "circle", preschool: "triangle", pharmacy: "triangle",
    college_university: "square", hospital: "square", government_office: "diamond" };
  const SECTOR_LABEL = { education: "образование", health: "здравоохранение", government: "госучреждения" };
  const FOOT_COLOR = { unknown: "var(--muted)", conditional: "var(--warning)", denied: "var(--critical)", allowed: "var(--good)" };
  const ORDER = (D.city_order || Object.keys(D.cities)).filter((k) => D.cities[k]);
  const STATE = { city: ORDER[0], groups: new Set(Object.keys(D.groups)), places: true, roads: true,
    roadStyle: "plain", pointMode: false, point: null, selected: null, view: null, epoch: 0,
    // what-if scenario: hypothetical layer, never mixed into places / counters / QA of the observed slice
    wi: { category: "school", points: [], proposed: null, mode: null, seq: 1, msg: "", explain: null },
    tool: "v1" };  // round 8: "v1" = one object (city-whatif-v1), "v2" = several objects (city-plan-v2, plan-ui.js)
  // Extension points for plan-ui.js (round 8): map layers, placement tools, city-switch hooks.
  const EXT = { layers: [], tools: [], onCity: [], onTool: [], cards: [] };
  const extTool = () => EXT.tools.find((t) => t.placing()) || null;
  const stopExt = () => { for (const t of EXT.tools) t.stop(); };

  // ---------- projection: local equirectangular metres around the square centre ----------
  let P = null;
  function setupProjection(city) {
    const [w, s, e, n] = D.cities[city].bbox;
    const lon0 = (w + e) / 2, lat0 = (s + n) / 2, kx = Math.cos(lat0 * Math.PI / 180) * 111320, ky = 110574;
    P = { lon0, lat0, kx, ky, bbox: [w, s, e, n], fx: (lon) => (lon - lon0) * kx, fy: (lat) => (lat0 - lat) * ky,
      ix: (x) => x / kx + lon0, iy: (y) => lat0 - y / ky };
  }
  function fitView() {
    const svg = $("map"), W = svg.clientWidth || 800, H = svg.clientHeight || 500;
    const [w, s, e, n] = P.bbox, x0 = P.fx(w), x1 = P.fx(e), y0 = P.fy(n), y1 = P.fy(s);
    STATE.view = { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, k: 0.82 * Math.min(W / (x1 - x0), H / (y1 - y0)) };
  }
  function toScreen(lon, lat) {
    const svg = $("map"), W = svg.clientWidth, H = svg.clientHeight, v = STATE.view;
    return [(P.fx(lon) - v.cx) * v.k + W / 2, (P.fy(lat) - v.cy) * v.k + H / 2];
  }
  function toLonLat(sx, sy) {
    const svg = $("map"), W = svg.clientWidth, H = svg.clientHeight, v = STATE.view;
    return [P.ix((sx - W / 2) / v.k + v.cx), P.iy((sy - H / 2) / v.k + v.cy)];
  }
  function haversine(lon1, lat1, lon2, lat2) {
    const R = 6371008.8, r = Math.PI / 180, dφ = (lat2 - lat1) * r, dλ = (lon2 - lon1) * r;
    const a = Math.sin(dφ / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dλ / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }
  const fmtM = (m) => (m >= 1000 ? (m / 1000).toFixed(2).replace(".", ",") + " км" : Math.round(m) + " м");
  const fmtDate = (t) => (t ? String(t).slice(0, 10) : "дата неизвестна");

  // ---------- markers ----------
  function markerShape(group, s) {
    const sh = SHAPES[group] || "circle";
    if (sh === "circle") return sv("circle", { r: s * 0.55 });
    if (sh === "square") return sv("rect", { x: -s / 2, y: -s / 2, width: s, height: s, rx: 1.5 });
    if (sh === "triangle") return sv("path", { d: `M0 ${-s * 0.62}L${s * 0.6} ${s * 0.42}L${-s * 0.6} ${s * 0.42}Z` });
    return sv("path", { d: `M0 ${-s * 0.65}L${s * 0.65} 0L0 ${s * 0.65}L${-s * 0.65} 0Z` });
  }
  function legendIcon(group) {
    const svg = sv("svg", { width: 16, height: 16, viewBox: "-8 -8 16 16", "aria-hidden": "true" });
    const m = markerShape(group, 11);
    m.setAttribute("fill", `var(--s-${D.groups[group].sector})`);
    m.setAttribute("stroke", "var(--surface)"); m.setAttribute("stroke-width", "1.5");
    svg.append(m);
    return svg;
  }

  // ---------- toolbar ----------
  function buildToolbar() {
    for (const key of ORDER) {
      const c = D.cities[key];
      const b = el("button", { type: "button", "aria-pressed": String(key === STATE.city), "data-city": key }, c.label);
      b.addEventListener("click", () => switchCity(key));
      $("citySeg").append(b);
    }
    for (const [g, info] of Object.entries(D.groups)) {
      const lab = el("label", { class: "chk" });
      const cb = el("input", { type: "checkbox", "data-group": g });
      cb.checked = true;
      cb.addEventListener("change", () => { cb.checked ? STATE.groups.add(g) : STATE.groups.delete(g); onFilterChange(); });
      lab.append(cb, legendIcon(g), document.createTextNode(info.label));
      $("groupFilters").append(lab);
    }
    $("tPlaces").addEventListener("change", (e) => { STATE.places = e.target.checked; onFilterChange(); });
    $("tRoads").addEventListener("change", (e) => {
      STATE.roads = e.target.checked;
      if (!STATE.roads && STATE.selected && STATE.selected.type === "segment") STATE.selected = null;  // K07 F2
      renderMap(); renderSelection(); updateStatus();
    });
    $("clearBtn").addEventListener("click", clearSelection);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if (STATE.wi.mode) setWiMode(null); if (extTool()) { stopExt(); renderMap(); updateStatus(); } clearSelection(); } });
    $("roadStyle").addEventListener("change", (e) => { STATE.roadStyle = e.target.value; renderRoadLegend(); renderMap(); });
    $("pointBtn").addEventListener("click", () => {
      STATE.pointMode = !STATE.pointMode;
      if (STATE.pointMode) { setWiMode(null, true); stopExt(); }
      $("pointBtn").setAttribute("aria-pressed", String(STATE.pointMode));
      $("map").classList.toggle("pointmode", STATE.pointMode);
      updateStatus(); renderMap();
    });
    $("zIn").addEventListener("click", () => zoomBy(1.5));
    $("zOut").addEventListener("click", () => zoomBy(1 / 1.5));
    $("zReset").addEventListener("click", () => { fitView(); renderMap(); });
  }
  // K07 P1/P2: point and selection can always be removed (button or Escape).
  function clearSelection() {
    if (!STATE.point && !STATE.selected) return;
    STATE.point = null; STATE.selected = null; STATE.epoch += 1;
    renderMap(); renderSelection(); renderTable(); renderExplain(); updateStatus();
  }
  // K07 W2: the result of a point / selection is announced next to the map (narrow screens show the card far below).
  function updateStatus() {
    const s = STATE.selected, st = $("mapStatus");
    $("clearBtn").disabled = !STATE.point && !s;
    if (STATE.wi.mode) { st.textContent = wiModeText(); return; }
    const et = extTool();
    if (et) { st.textContent = et.statusText(); return; }
    if (!s) { st.textContent = STATE.pointMode ? "Режим точки: нажмите на карту (или Enter — точка в центре)." : ""; return; }
    if (s.type === "point") {
      const [lon, lat] = STATE.point;
      const n = visiblePlaces().filter((p) => haversine(lon, lat, p.lon, p.lat) <= 500).length;
      st.textContent = `Точка выбрана: ${n} записей выбранных категорий в пределах 500 м по прямой. Время пешком не рассчитывается.`;
    } else if (s.type === "place") {
      const p = D.cities[STATE.city].places.find((x) => x.id === s.id);
      st.textContent = p ? `Выбрано: ${p.name || "Без названия"} (${p.group_label}). Карточка — в панели «Выбор».` : "";
    } else st.textContent = "Выбрана дорога. Карточка — в панели «Выбор».";
  }
  function renderRoadLegend() {
    const box = $("roadLegend");
    box.hidden = STATE.roadStyle !== "foot";
    box.replaceChildren();
    for (const [k, txt] of [["unknown", "нет правил"], ["conditional", "условия"], ["denied", "запрет"], ["allowed", "разрешено"]]) {
      const sw = sv("svg", { width: 18, height: 8, "aria-hidden": "true" });
      sw.append(sv("line", { x1: 1, y1: 4, x2: 17, y2: 4, stroke: FOOT_COLOR[k], "stroke-width": 3 }));
      box.append(sw, document.createTextNode(txt + " "));
    }
  }
  // City switch: drop every per-city state (selection, point, tooltip, pending explanation) before rendering.
  function switchCity(key) {
    if (!D.cities[key]) return;
    const hadScenario = STATE.city !== key && (STATE.wi.points.length || STATE.wi.proposed);
    for (const f of EXT.onCity) f(key, STATE.city !== key);
    STATE.city = key; STATE.point = null; STATE.selected = null; STATE.epoch += 1;
    resetScenario(hadScenario ? "Город изменён — сценарий сброшен: точки и проектный объект между городами не переносятся." : "");
    hideTip();
    document.querySelectorAll("#citySeg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.city === key)));
    setupProjection(key); fitView(); renderAll(); updateStatus();
  }
  // Filter change: a selected object that is no longer visible is deselected; explanations are recomputed.
  function onFilterChange() {
    STATE.epoch += 1;
    const s = STATE.selected;
    if (s && s.type === "place" && !visiblePlaces().some((p) => p.id === s.id)) STATE.selected = null;
    renderAll(); updateStatus();
  }
  function zoomBy(f, sx, sy) {
    const svg = $("map"), W = svg.clientWidth, H = svg.clientHeight, v = STATE.view;
    if (sx === undefined) { sx = W / 2; sy = H / 2; }
    const mx = (sx - W / 2) / v.k + v.cx, my = (sy - H / 2) / v.k + v.cy;
    v.k *= f; v.cx = mx - (sx - W / 2) / v.k; v.cy = my - (sy - H / 2) / v.k;
    renderMap();
  }

  // ---------- map ----------
  function visiblePlaces() {
    if (!STATE.places) return [];
    return D.cities[STATE.city].places.filter((p) => STATE.groups.has(p.group));
  }
  function renderMap() {
    const c = D.cities[STATE.city], svg = $("map");
    hideTip();  // K07 CS2: a tooltip of a removed element must not survive a re-render / city switch
    svg.replaceChildren();
    const gBox = sv("g"), gRoad = sv("g"), gPoint = sv("g"), gMark = sv("g"), gWi = sv("g", { "data-layer": "hypothetical" }), gLabel = sv("g");
    svg.append(gBox, gRoad, gPoint, gMark, gWi, gLabel);
    const [w, s, e, n] = c.bbox, [x0, y0] = toScreen(w, n), [x1, y1] = toScreen(e, s);
    gBox.append(sv("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, fill: "var(--surface-2)", stroke: "var(--ink)", "stroke-width": 1.5, "stroke-dasharray": "6 4" }));
    const t = sv("text", { x: x0 + 4, y: y0 - 6, "font-size": 11, fill: "var(--ink)" });
    t.textContent = `Квадрат K10 (${c.label}, ~2×2 км) — не весь город`; gLabel.append(t);
    if (STATE.roads) for (const sg of c.segments) {
      let d = ""; sg.coords.forEach(([x, y], i) => { const [a, b] = toScreen(x, y); d += (i ? "L" : "M") + a.toFixed(1) + " " + b.toFixed(1); });
      const color = STATE.roadStyle === "foot" ? FOOT_COLOR[sg.foot_access] : "var(--base)";
      gRoad.append(sv("path", { d, fill: "none", stroke: color, "stroke-width": sg.class === "footway" || sg.class === "path" ? 1.2 : 2, "stroke-linecap": "round" }));
      const hit = sv("path", { d, fill: "none", stroke: "transparent", "stroke-width": 10, tabindex: 0, role: "button",
        "aria-label": `Дорога: ${sg.class}${sg.name ? ", " + sg.name : ""}` });
      hit.style.cursor = "pointer";
      hit.addEventListener("pointermove", (ev) => showTip(ev, [`${sg.class}${sg.name ? " · " + sg.name : ""}`, `${fmtM(sg.length_m)} · проход пешком: ${sg.foot_access}`]));
      hit.addEventListener("pointerleave", hideTip);
      // In point mode a click on a road sets the point (roads cover most of the map); markers keep priority.
      const pick = (ev) => { if ((STATE.pointMode || STATE.wi.mode || extTool()) && ev.type === "click") return; ev.stopPropagation(); STATE.selected = { type: "segment", id: sg.id }; renderSelection(); renderExplain(); updateStatus(); };
      hit.addEventListener("click", pick);
      hit.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(ev); } });
      gRoad.append(hit);
    }
    if (STATE.point) {
      const [sx, sy] = toScreen(STATE.point[0], STATE.point[1]);
      gPoint.append(sv("path", { d: `M${sx - 8} ${sy}H${sx + 8}M${sx} ${sy - 8}V${sy + 8}`, stroke: "var(--ink)", "stroke-width": 2 }));
    }
    const places = visiblePlaces();
    const visIds = new Set(places.map((p) => p.id));
    for (const grp of colocatedGroups()) {
      const n = grp.ids.filter((i) => visIds.has(i)).length;
      if (!n) continue;
      const [cx, cy] = toScreen(grp.lon, grp.lat);
      gPoint.append(sv("circle", { cx, cy, r: 18, fill: "none", stroke: "var(--warning)", "stroke-width": 2, "stroke-dasharray": "3 2" }));
      const t = sv("text", { x: cx + 20, y: cy - 12, "font-size": 11, fill: "var(--ink)" });
      t.textContent = `×${n} в одной точке`; gLabel.append(t);
      const tt = sv("title"); tt.textContent = `${n} записей с одинаковыми координатами — точное место не проверено`; t.append(tt);
    }
    for (const p of places) {
      const [sx, sy] = toScreen(p.lon, p.lat);
      const g = sv("g", { transform: `translate(${sx.toFixed(1)} ${sy.toFixed(1)})`, tabindex: 0, role: "button",
        "aria-label": `${p.name || "Без названия"}, ${p.group_label}`, "data-id": p.id });
      g.style.cursor = "pointer";
      const sel = STATE.selected && STATE.selected.type === "place" && STATE.selected.id === p.id;
      g.append(sv("circle", { r: 12, fill: "transparent" }));
      if (sel) g.append(sv("circle", { r: 10, fill: "none", stroke: "var(--ink)", "stroke-width": 2 }));
      const m = markerShape(p.group, 11);
      m.setAttribute("fill", `var(--s-${p.sector})`); m.setAttribute("stroke", "var(--surface)"); m.setAttribute("stroke-width", "2");
      g.append(m);
      const qa = qaOf(p);
      if (qa.length) g.append(sv("circle", { cx: 6, cy: -6, r: 3.5, fill: "var(--warning)", stroke: "var(--surface)", "stroke-width": 1 }));
      g.addEventListener("pointermove", (ev) => showTip(ev, [p.name || "Без названия", `${p.group_label} · conf. ${p.confidence ?? "—"}`, ...qa.map((q) => "⚠ " + q.code)]));
      g.addEventListener("pointerleave", hideTip);
      const pick = (ev) => { if ((STATE.wi.mode || extTool()) && ev.type === "click") return; ev.stopPropagation(); selectPlace(p.id); };
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(ev); } });
      gMark.append(g);
    }
    if (STATE.tool === "v1") renderWiLayer(gWi, gLabel);
    for (const f of EXT.layers) f(gWi, gLabel);
    const msg = $("mapMsg");
    if (!STATE.places) { msg.hidden = false; msg.textContent = "Слой объектов выключен."; }
    else if (!STATE.groups.size) { msg.hidden = false; msg.textContent = "Не выбрана ни одна категория — включите категории в панели фильтров."; }
    else if (!places.length) { msg.hidden = false; msg.textContent = "В этом квадрате нет записей выбранных категорий. Это не значит, что таких объектов нет на местности."; }
    else msg.hidden = true;
    const att = $("attrib");
    att.replaceChildren(document.createTextNode(attributionLine(c) + " · "), el("a", { href: "attribution/ATTRIBUTION.md", target: "_blank", rel: "noopener" }, "лицензии"));
  }
  // Providers are taken from records' sources[] (K08 attribution.json), not from the K10 file header.
  function attributionLine(c) {
    const names = { OpenStreetMap: "© OpenStreetMap contributors", Overture: "Overture Maps Foundation", meta: "Meta", Foursquare: "Foursquare", TomTom: "TomTom" };
    const seen = [];
    for (const a of c.attribution || []) { const n = names[a.dataset] || a.dataset; if (!seen.includes(n)) seen.push(n); }
    return (seen.length ? seen.join("; ") : "источники не указаны") + " · Overture " + c.release;
  }
  function qaOf(p) { return F && F.qaOf ? F.qaOf(STATE.city, p) : []; }
  function colocatedGroups() {
    const ev = window.CITY_OBS;
    return ev && ev.cities && ev.cities[STATE.city] ? ev.cities[STATE.city].qa.colocated : [];
  }
  function selectPlace(id) { STATE.selected = { type: "place", id }; renderMap(); renderSelection(); renderTable(); renderExplain(); updateStatus(); }

  // ---------- tooltip ----------
  function showTip(e, lines) {
    const tip = $("tip"), wrap = tip.parentElement.getBoundingClientRect();
    tip.replaceChildren(el("strong", null, lines[0]), ...lines.slice(1).map((l) => el("div", null, l)));
    tip.style.display = "block";
    tip.style.left = Math.max(4, Math.min(e.clientX - wrap.left + 14, wrap.width - 270)) + "px";
    tip.style.top = e.clientY - wrap.top + 14 + "px";
  }
  function hideTip() { $("tip").style.display = "none"; }

  // ---------- pan / zoom / point ----------
  function setupInteraction() {
    const svg = $("map");
    let drag = null;
    svg.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, cx: STATE.view.cx, cy: STATE.view.cy, moved: false }; });
    svg.addEventListener("pointermove", (e) => {
      if (!drag || e.buttons === 0) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
      if (drag.moved) { STATE.view.cx = drag.cx - dx / STATE.view.k; STATE.view.cy = drag.cy - dy / STATE.view.k; renderMap(); }
    });
    svg.addEventListener("pointerup", (e) => {
      const d = drag; drag = null;
      const et = extTool();
      if (d && !d.moved && et) { const r = svg.getBoundingClientRect(); et.place(toLonLat(e.clientX - r.left, e.clientY - r.top)); return; }
      if (d && !d.moved && STATE.wi.mode) { const r = svg.getBoundingClientRect(); wiPlace(toLonLat(e.clientX - r.left, e.clientY - r.top)); return; }
      if (!d || d.moved || !STATE.pointMode) return;
      if (e.target.closest && e.target.closest("g[data-id]")) return;  // a click on an object marker selects the object
      const r = svg.getBoundingClientRect();
      STATE.point = toLonLat(e.clientX - r.left, e.clientY - r.top);
      STATE.selected = { type: "point" };
      renderMap(); renderSelection(); renderExplain(); updateStatus();
    });
    // K07 K5: keyboard on the focused map (only when the map itself has focus, not a marker inside it)
    svg.addEventListener("keydown", (e) => {
      if (e.target !== svg) return;
      const step = 60 / STATE.view.k, mv = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (mv) { e.preventDefault(); STATE.view.cx += mv[0]; STATE.view.cy += mv[1]; renderMap(); }
      else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomBy(1.5); }
      else if (e.key === "-") { e.preventDefault(); zoomBy(1 / 1.5); }
      else if ((e.key === "Enter" || e.key === " ") && extTool()) { e.preventDefault(); extTool().place(toLonLat(svg.clientWidth / 2, svg.clientHeight / 2)); }
      else if ((e.key === "Enter" || e.key === " ") && STATE.wi.mode) { e.preventDefault(); wiPlace(toLonLat(svg.clientWidth / 2, svg.clientHeight / 2)); }
      else if ((e.key === "Enter" || e.key === " ") && STATE.pointMode) {
        e.preventDefault();
        STATE.point = toLonLat(svg.clientWidth / 2, svg.clientHeight / 2);
        STATE.selected = { type: "point" };
        renderMap(); renderSelection(); renderExplain(); updateStatus();
      }
    });
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      zoomBy(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    window.addEventListener("resize", () => renderMap());
  }

  // ---------- side panel ----------
  function dlRows(dl, rows) {
    for (const [k, v, badge] of rows) {
      const unknown = v === null || v === undefined || v === "";
      const dd = el("dd", unknown ? { class: "kv-unknown" } : null, unknown ? "нет данных" : v);
      if (badge) dd.append(el("span", { class: "badge" }, badge));
      dl.append(el("dt", null, k), dd);
    }
  }
  function districtText(p) {
    if (!F || !F.districtOf) return ["не определён", "привязка не проверена"];
    const r = F.districtOf(STATE.city, p);
    return [r.text, r.badge];
  }
  function renderSelection() {
    const c = D.cities[STATE.city], body = $("selBody"), empty = $("selEmpty");
    body.replaceChildren();
    const s = STATE.selected;
    empty.hidden = !!s;
    if (!s) return;
    if (s.type === "place") {
      const p = c.places.find((x) => x.id === s.id);
      if (!p) { STATE.selected = null; empty.hidden = false; return; }
      body.append(el("h3", null, p.name || "Без названия"));
      const dl = el("dl"), [dt, db] = districtText(p);
      dlRows(dl, [
        ["Категория", `${p.group_label} (${SECTOR_LABEL[p.sector]})`, "правило K10"],
        ["Категория Overture", p.category, "наблюдение · вторичное"],
        ["Confidence", p.confidence, "оценка Overture 0..1"],
        ["Адрес", p.address, "наблюдение · вторичное"],
        ["Район", dt, db],
        ["Координаты", `${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}`, null],
        ["Мощность / места", null, "нет в источнике (not_in_source)"],
        ["Работает ли сейчас", p.operating_status, "Overture"],
      ]);
      body.append(dl);
      const qa = qaOf(p);
      if (qa.length) {
        body.append(el("h3", null, "Проверка качества записи"));
        const ul = el("ul", { class: "reasons" });
        for (const q of qa) {
          const li = el("li", q.code === "COLOCATED" ? { class: "warn", "data-coord-group": `${p.lon},${p.lat}` } : { class: "warn" }, q.text + " ");
          if (q.code !== "CATEGORY_DOUBT" && q.ids.length > 1) {
            const sub = el("ul");
            for (const id of q.ids) {
              if (id === p.id) continue;
              const other = c.places.find((x) => x.id === id);
              const b = el("button", { type: "button", class: "tool", "data-coord-group-item": id }, other ? `${other.name || "Без названия"} · ${other.group_label}` : id);
              b.addEventListener("click", () => selectPlace(id));
              const it = el("li"); it.append(b); sub.append(it);
            }
            li.append(sub);
          }
          ul.append(li);
        }
        body.append(ul, el("p", { class: "muted" }, "Метки не означают, что запись неверна: их ставит воспроизводимое правило. Записи не удаляются и не перекатегоризируются."));
      }
      const det = el("details"); det.append(el("summary", null, "Источник записи"));
      const ul = el("ul", { class: "reasons" });
      for (const src of p.sources) ul.append(el("li", null, `${src.dataset} · ${src.license} · ${fmtDate(src.update_time)}${src.record_id ? " · " + src.record_id : ""}`));
      det.append(ul, el("p", { class: "muted" }, `Overture id ${p.id} (v${p.overture_version}). Наличие записи не подтверждает, что объект работает; отсутствие записи не означает, что объекта нет.`));
      body.append(det);
    } else if (s.type === "segment") {
      const g = c.segments.find((x) => x.id === s.id);
      if (!g) { STATE.selected = null; empty.hidden = false; return; }
      const segSource = { OpenStreetMap: "OSM", TomTom: "TomTom" }[g.dataset] || g.dataset || "источник не указан";
      body.append(el("h3", null, `Дорога (${segSource} через Overture)`));  // provider of this segment (K08 r5 A7)
      const dl = el("dl");
      dlRows(dl, [
        ["Класс", g.class + (g.subclass ? " / " + g.subclass : ""), "наблюдение"],
        ["Название", g.name, null],
        ["Длина", fmtM(g.length_m) + (g.crosses_edge ? " (вся линия, выходит за квадрат)" : ""), "гаверсинус по сфере, K10"],
        ["Проход пешком", D.foot_access_labels[g.foot_access], g.foot_access],
        ["Мост / тоннель", g.flags.length ? g.flags.join(", ") : "не отмечено", "road_flags"],
        ["Источник", `${g.dataset || "—"} · ${g.record_id || "id записи нет"} · ${g.license || "—"} · ${fmtDate(g.update_time)}`, g.dataset === "TomTom" ? "не OSM: K08 F3" : null],
      ]);
      body.append(dl, el("p", { class: "muted" }, "Режим просмотра дорог: время пешком и доступность по сети не рассчитываются — у большинства сегментов права прохода неизвестны."));
    } else if (s.type === "point") {
      renderPoint(c, body);
    }
  }
  function renderPoint(c, body) {
    const [lon, lat] = STATE.point;
    body.append(el("h3", null, `Точка ${lat.toFixed(5)}, ${lon.toFixed(5)}`));
    const [w, so, e, n] = c.bbox;
    if (lon < w || lon > e || lat < so || lat > n) body.append(el("p", { class: "warn" }, "Точка вне квадрата K10: объекты за его пределами в срез не входили."));
    body.append(el("p", { class: "warn" }, "Расстояние по прямой — нижняя граница пешего пути, не время в пути и не доступность."));
    const rows = visiblePlaces().map((p) => ({ p, d: haversine(lon, lat, p.lon, p.lat) })).sort((a, b) => a.d - b.d).slice(0, 8);
    if (!rows.length) { body.append(el("p", { class: "muted" }, "Нет видимых объектов среза.")); return; }
    const tbl = el("table"), tr = el("tr");
    for (const [h, cls] of [["Объект", null], ["Категория", null], ["По прямой", "num"]]) tr.append(el("th", { class: cls }, h));
    const th = el("thead"); th.append(tr); tbl.append(th);
    const tb = el("tbody");
    for (const { p, d } of rows) {
      const r = el("tr", { tabindex: 0 });
      r.append(el("td", null, p.name || "Без названия"), el("td", null, p.group_label), el("td", { class: "num" }, fmtM(d)));
      r.addEventListener("click", () => selectPlace(p.id));
      tb.append(r);
    }
    tbl.append(tb); body.append(tbl);
  }
  function renderSlice() {
    const c = D.cities[STATE.city], k = c.counts, b = $("sliceBody");
    b.replaceChildren();
    const dl = el("dl");
    dlRows(dl, [
      ["Квадрат", `${c.label}: ${c.bbox.map((x) => x.toFixed(4)).join(", ")}`, "W,S,E,N"],
      ["Источник", `Overture Maps ${c.release}`, "вторичный"],
      ["Выгружено", c.retrieved_utc ? c.retrieved_utc.replace("T", " ").slice(0, 16) + " UTC" : null, "K10"],
      ["Записей объектов", `${k.places} в полном ответе запроса по квадрату`, "не реестр города"],
      ["Объектов по всему городу", null, "не собиралось (not_collected)"],
      ["Сегментов дорог", `${k.segments} (из них ${k.segments_crossing_edge} выходят за край)`, null],
    ]);
    b.append(dl, el("h3", null, "Проход пешком по данным"));
    const ul = el("ul", { class: "reasons" });
    for (const key of ["unknown", "conditional", "denied", "allowed"])
      ul.append(el("li", null, `${D.foot_access_labels[key]}: ${k.foot_access[key] || 0}`));
    b.append(ul, el("p", { class: "muted" }, "«0 записей» = ноль в полном ответе запроса по этому квадрату и выпуску. Это не значит, что объектов нет в городе: число по городу неизвестно. Overture неполон; мощность, население и официальный состав районов в пакете отсутствуют."));
    const ev = window.CITY_OBS, q = ev && ev.cities && ev.cities[STATE.city] && ev.cities[STATE.city].qa;
    if (q) {
      b.append(el("h3", null, "Проверка качества среза"));
      const qul = el("ul", { class: "reasons" });
      qul.append(el("li", null, `групп с совпадающими координатами (≥3 записей): ${q.colocated.length}${q.colocated.length ? " — " + q.colocated.map((g) => g.ids.length).join(", ") + " записей" : ""}`),
        el("li", null, `пар — кандидатов в дубликаты: ${q.possible_duplicates.length}`),
        el("li", null, `записей с сомнением в категории: ${Object.keys(q.category_doubt).length}`));
      b.append(qul);
    }
  }
  function renderProvenance() {
    const c = D.cities[STATE.city], b = $("provBody");
    b.replaceChildren();
    const dl = el("dl");
    dlRows(dl, [
      ["Пакет", `K10 раунд 3 · ${D.inputs.k10_branch} @ ${D.inputs.k10_sha.slice(0, 10)}`, "source_manifest.json"],
      ["Коммит данных", D.inputs.k10_data_commit.slice(0, 10), null],
      ["Атрибуция", attributionLine(c), "по sources[] записей (K08)"],
      ["Вид данных", c.kind, null],
    ]);
    b.append(dl);
    const la = el("p");
    la.append(document.createTextNode("Лицензии: "));
    [["ATTRIBUTION.md", "attribution/ATTRIBUTION.md"], ["ODbL-1.0", "attribution/LICENSES/ODbL-1.0.txt"], ["CDLA-Permissive-2.0", "attribution/LICENSES/CDLA-Permissive-2.0.txt"], ["Apache-2.0", "attribution/LICENSES/Apache-2.0.txt"]]
      .forEach(([t, h], i) => { if (i) la.append(document.createTextNode(" · ")); la.append(el("a", { href: h, target: "_blank", rel: "noopener" }, t)); });
    const ul0 = el("ul", { class: "reasons" });
    for (const a of c.attribution || []) ul0.append(el("li", null, `${a.layer}: ${a.dataset} — ${a.license}`));
    b.append(la, ul0, el("p", { class: "muted" }, "Пробел происхождения (K08 F5): в Астане 26 источников ссылаются на свойство routes, которое не извлекалось в пакет K10; восстановить из сохранённых файлов нельзя."));
    b.append(el("h3", null, "Файлы и SHA256"));
    const ul = el("ul", { class: "reasons" });
    for (const [name, f] of Object.entries(c.files)) ul.append(el("li", null, `${name}: ${f.path} · ${f.sha256.slice(0, 16)}…`));
    b.append(ul);
    if (F && F.provenanceNotes) for (const note of F.provenanceNotes(STATE.city)) b.append(el("p", { class: "muted" }, note));
  }
  function renderTable() {
    const all = D.cities[STATE.city].places;
    const rows = visiblePlaces().slice().sort((a, b) => a.group.localeCompare(b.group) || (a.name || "").localeCompare(b.name || "", "ru"));
    const tb = $("tbl");
    tb.replaceChildren();
    $("tblCount").textContent = `(${rows.length} из ${all.length} записей среза)`;
    if (!rows.length) {
      const tr = el("tr");
      tr.append(el("td", { colspan: 4, class: "muted" }, !STATE.places ? "Слой объектов выключен." : STATE.groups.size ? "Нет записей выбранных категорий в этом квадрате." : "Не выбрана ни одна категория."));
      tb.append(tr); return;
    }
    for (const p of rows) {
      const tr = el("tr", { tabindex: 0 });
      if (STATE.selected && STATE.selected.type === "place" && STATE.selected.id === p.id) tr.classList.add("sel");
      const qa = qaOf(p);
      tr.append(el("td", null, (qa.length ? "⚠ " : "") + (p.name || "Без названия")), el("td", null, p.group_label), el("td", null, districtText(p)[0]), el("td", { class: "num" }, p.confidence ?? "—"));
      if (qa.length) tr.title = qa.map((q) => q.code).join(", ");
      tr.addEventListener("click", () => selectPlace(p.id));
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") selectPlace(p.id); });
      tb.append(tr);
    }
  }
  function renderExplain() {
    const card = $("explainCard");
    if (!F || !F.renderExplanation) { card.hidden = true; return; }
    card.hidden = false;
    const epoch = STATE.epoch, city = STATE.city;
    F.renderExplanation($("explainBody"), { state: STATE, data: D, isCurrent: () => STATE.epoch === epoch && STATE.city === city, el });
  }
  function renderAll() { renderMap(); renderSelection(); renderWhatIf(); for (const f of EXT.cards) f(); renderSlice(); renderExplain(); renderTable(); renderProvenance(); }
  // ---------- «Если добавить объект» (round 7, FEATURE_SPEC city-whatif-v1) ----------
  // The hypothetical object and control points live only in STATE.wi and the separate map layer; they never enter
  // places, counters, QA, the facts catalog or the objects table. Numbers come from whatif.js (pure, tested vs Python).
  const WI = STATE.wi, snapCache = {};
  const wiOn = () => !!(X && F && F.sha256hex && F.placesDigest);
  function snapshotOf(city) { return snapCache[city] || (snapCache[city] = X.sourceSnapshot(D, city, F)); }
  function wiScenario() {
    return { schema_version: X.SCHEMA, city_id: STATE.city, source_snapshot: snapshotOf(STATE.city), category: WI.category,
      control_points: WI.points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat })),
      proposed_object: WI.proposed ? { id: WI.proposed.id, lon: WI.proposed.lon, lat: WI.proposed.lat, category: WI.category, kind: "hypothetical" } : null };
  }
  function wiResult() { return X.compute(D.cities[STATE.city].places, WI.category, WI.points, wiScenario().proposed_object); }
  function wiRefresh() { renderMap(); renderWhatIf(); updateStatus(); }
  function resetScenario(reason) {
    WI.points = []; WI.proposed = null; WI.seq = 1; WI.explain = null; WI.mode = null; WI.msg = reason || "";
    $("map").classList.remove("wimode");
  }
  function setWiMode(mode, silent) {
    WI.mode = WI.mode === mode ? null : mode;
    if (WI.mode) stopExt();
    if (WI.mode && STATE.pointMode) {  // the two placement modes are exclusive
      STATE.pointMode = false; $("pointBtn").setAttribute("aria-pressed", "false"); $("map").classList.remove("pointmode");
    }
    $("map").classList.toggle("wimode", !!WI.mode);
    if (!silent) wiRefresh(); else renderWhatIf();
  }
  function setWiCategory(cat) {
    if (!X.CATEGORIES[cat] || cat === WI.category) return;
    const had = WI.points.length || WI.proposed;
    WI.category = cat;
    resetScenario(had ? `Категория изменена на «${X.CATEGORIES[cat]}» — сценарий и объяснение сброшены.` : "");
    wiRefresh();
  }
  function wiModeText() {
    return WI.mode === "points"
      ? `Режим «контрольные точки»: нажмите на карту (Enter — точка в центре карты). Точек ${WI.points.length} из ${X.MAX_POINTS}. Escape — выйти из режима.`
      : `Режим «проектный объект» (${X.CATEGORIES[WI.category]}): нажмите на карту, чтобы поставить или передвинуть его (Enter — в центр). Escape — выйти.`;
  }
  function nextId() { let id; do { id = "P" + WI.seq++; } while (WI.points.some((p) => p.id === id)); return id; }
  function wiPlace([lon, lat]) {
    if (!WI.mode) return false;
    const bb = D.cities[STATE.city].bbox;
    if (!X.inBbox(bb, lon, lat)) { WI.msg = "Место вне квадрата среза: там нет исходных записей, поэтому точку или проект туда поставить нельзя."; wiRefresh(); return false; }
    WI.explain = null;
    if (WI.mode === "points") {
      if (WI.points.length >= X.MAX_POINTS) { WI.msg = `Не больше ${X.MAX_POINTS} контрольных точек — удалите одну из списка.`; wiRefresh(); return false; }
      const id = nextId();
      WI.points.push({ id, lon, lat });
      WI.msg = `Контрольная точка ${id} поставлена.`;
    } else {
      WI.msg = WI.proposed ? "Проектный объект передвинут — расстояния пересчитаны." : "Проектный объект поставлен.";
      WI.proposed = { id: "X1", lon, lat };
    }
    wiRefresh();
    return true;
  }
  function wiRemovePoint(id) { WI.points = WI.points.filter((p) => p.id !== id); WI.explain = null; WI.msg = `Точка ${id} удалена.`; wiRefresh(); }
  function wiRemoveProposed() { WI.proposed = null; WI.explain = null; WI.msg = "Проектный объект удалён — показан исходный срез («после» = «до»)."; wiRefresh(); }

  function renderWiLayer(g, gLabel) {
    if (!wiOn() || (!WI.points.length && !WI.proposed)) return;
    const res = wiResult(), byId = Object.fromEntries(D.cities[STATE.city].places.map((p) => [p.id, p]));
    for (const r of res.rows) {  // dashed line to the nearest object after the change (source record or the project)
      const tgt = r.nearest_after === "proposed" ? WI.proposed : byId[r.nearest_before];
      if (!tgt) continue;
      const [a, b] = toScreen(r.lon, r.lat), [c, d] = toScreen(tgt.lon, tgt.lat);
      g.append(sv("line", { x1: a, y1: b, x2: c, y2: d, stroke: r.nearest_after === "proposed" ? "var(--critical)" : "var(--ink-2)", "stroke-width": 1.2, "stroke-dasharray": "4 3" }));
    }
    for (const p of WI.points) {
      const [x, y] = toScreen(p.lon, p.lat);
      const m = sv("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`, "data-wi-point": p.id, role: "img", "aria-label": `Контрольная точка ${p.id}` });
      m.append(sv("rect", { x: -5, y: -5, width: 10, height: 10, fill: "var(--surface)", stroke: "var(--ink)", "stroke-width": 2 }));
      g.append(m);
      const t = sv("text", { x: x + 8, y: y + 4, "font-size": 11, fill: "var(--ink)" }); t.textContent = p.id; gLabel.append(t);
    }
    if (WI.proposed) {
      const [x, y] = toScreen(WI.proposed.lon, WI.proposed.lat);
      const m = sv("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`, "data-wi-proposed": "X1", role: "img", "aria-label": `Проектный объект (гипотеза): ${X.CATEGORIES[WI.category]}` });
      m.append(sv("circle", { r: 11, fill: "none", stroke: "var(--critical)", "stroke-width": 2, "stroke-dasharray": "3 2" }));
      m.append(sv("path", { d: "M0 -7L2 -2L7 -2L3 1.5L4.5 7L0 3.8L-4.5 7L-3 1.5L-7 -2L-2 -2Z", fill: "var(--critical)" }));
      g.append(m);
      const t = sv("text", { x: x + 13, y: y - 8, "font-size": 11, fill: "var(--critical)" });
      t.textContent = `Проектный объект: ${X.CATEGORIES[WI.category].toLowerCase()} (гипотеза)`; gLabel.append(t);
    }
  }

  const fmtD = (v) => (v === null ? "нет данных" : fmtM(v));
  function renderWhatIf() {
    const card = $("whatifCard"), b = $("whatifBody");
    if (!wiOn() || STATE.tool !== "v1") { card.hidden = true; return; }
    card.hidden = false;
    b.replaceChildren();
    b.append(el("p", { class: "muted" }, "Условный сценарий, не решение акимата. Расстояние по прямой в пределах среза от ваших контрольных точек до ближайшей записи категории: до и после одного проектного объекта."));
    const row1 = el("div", { class: "wi-ctl" });
    const lab = el("label", { for: "wiCat" }, "Категория ");
    const sel = el("select", { id: "wiCat" });
    for (const [k, v] of Object.entries(X.CATEGORIES)) { const o = el("option", { value: k }, v); if (k === WI.category) o.selected = true; sel.append(o); }
    sel.addEventListener("change", () => setWiCategory(sel.value));
    row1.append(lab, sel);
    const row2 = el("div", { class: "wi-ctl" });
    const btn = (id, text, onClick, extra) => { const x = el("button", { type: "button", class: "tool", id, ...(extra || {}) }, text); x.addEventListener("click", onClick); return x; };
    row2.append(
      btn("wiModePoints", "Ставить контрольные точки", () => setWiMode("points"), { "aria-pressed": String(WI.mode === "points") }),
      btn("wiModeProject", WI.proposed ? "Передвинуть проектный объект" : "Поставить проектный объект", () => setWiMode("project"), { "aria-pressed": String(WI.mode === "project") }));
    const row3 = el("div", { class: "wi-ctl" });
    const del = btn("wiDelProject", "Удалить проектный объект", wiRemoveProposed); del.disabled = !WI.proposed;
    const clr = btn("wiClear", "Сбросить сценарий", () => { resetScenario("Сценарий сброшен."); wiRefresh(); }); clr.disabled = !WI.points.length && !WI.proposed;
    row3.append(del, clr);
    b.append(row1, row2, row3, el("p", { class: "wi-msg warn", id: "wiMsg", role: "status", "aria-live": "polite" }, WI.msg));

    const res = wiResult();
    if (WI.proposed) b.append(el("p", null, `Проектный объект X1 (${X.CATEGORIES[WI.category].toLowerCase()}, гипотеза): ${WI.proposed.lat.toFixed(5)}, ${WI.proposed.lon.toFixed(5)}`));
    if (!WI.points.length) b.append(el("p", { class: "muted", id: "wiEmpty" }, "Контрольных точек нет. Включите «Ставить контрольные точки» и нажмите на карту (1–10 точек)."));
    else {
      const ul = el("ul", { class: "wi-pts", "aria-label": "Контрольные точки" });
      for (const p of WI.points) {
        const li = el("li", { "data-wi-item": p.id }, `${p.id}: ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`);
        const rm = btn(null, "Удалить", () => wiRemovePoint(p.id), { "aria-label": `Удалить контрольную точку ${p.id}` });
        li.append(rm); ul.append(li);
      }
      b.append(ul);
      if (res.candidates === 0) b.append(el("p", { class: "warn" }, "В срезе нет исходных записей; улучшение не вычисляется. Это не значит, что таких учреждений нет на местности."));
      const tbl = el("table", { id: "wiTable", "aria-label": "Расстояние по прямой в пределах среза: до и после" });
      const cap = el("caption", { class: "muted" }, "по прямой в пределах среза, метры округлены только при выводе");
      const hr = el("tr");
      for (const [h, cls] of [["Точка", null], ["До", "num"], ["После", "num"], ["Разница", "num"]]) hr.append(el("th", { class: cls }, h));
      const th = el("thead"); th.append(hr); tbl.append(cap, th);
      const tb = el("tbody"), byId = Object.fromEntries(D.cities[STATE.city].places.map((p) => [p.id, p]));
      for (const r of res.rows) {
        const tr = el("tr", { "data-wi-row": r.id });
        const src = r.nearest_before ? byId[r.nearest_before] : null;
        const tdP = el("td", null, r.id), tdB = el("td", { class: "num" }, fmtD(r.before));
        let srcRow = null;
        if (src) {  // source of the nearest record (before), with its QA marks; opens the record card
          const qa = qaOf(src), td = el("td", { colspan: 4, class: "muted" }, `${r.id} — ближайшая запись в срезе: `);
          const sbtn = el("button", { type: "button", class: "tool wi-src", "data-wi-source": src.id, title: "Открыть исходную запись" }, `${qa.length ? "⚠ " : ""}${src.name || "Без названия"}`);
          sbtn.addEventListener("click", () => selectPlace(src.id));
          td.append(sbtn, document.createTextNode(` · ${src.group_label} · ${(src.sources[0] || {}).dataset || "источник не указан"}${qa.length ? " · QA: " + qa.map((q) => q.code).join(", ") : ""}`));
          srcRow = el("tr", { class: "wi-srcrow" }); srcRow.append(td);
        }
        const tdA = el("td", { class: "num" }, fmtD(r.after));
        if (r.nearest_after === "proposed") tdA.append(el("div", { class: "muted" }, "проектный объект"));
        const dtxt = r.delta === null ? "не вычисляется" : r.delta >= 0.5 ? `ближе на ${fmtM(r.delta)}` : r.delta > 0 ? "ближе менее чем на 1 м" : "без изменений";
        tr.append(tdP, tdB, tdA, el("td", { class: "num" + (r.delta > 0 ? " better" : "") }, dtxt));
        tb.append(tr);
        if (srcRow) tb.append(srcRow);
      }
      tbl.append(tb); b.append(tbl);
    }
    b.append(el("p", { class: "muted" }, "Ограничения: ближайшая запись в срезе — не обязательно ближайшее учреждение в городе (квадрат ~2×2 км, Overture неполон). QA-метки сохраняются; запись без метки не считается проверенной. Не время пешком, не изохроны, не обеспеченность местами, не население и не бюджет. «Ближе» — только меньшее геометрическое расстояние."));

    // export / import / explanation (stage 4)
    const row4 = el("div", { class: "wi-ctl" });
    const ex = btn("wiExport", "Сохранить сценарий (JSON)", wiExport); ex.disabled = !WI.points.length;
    const file = el("input", { type: "file", id: "wiFile", accept: ".json,application/json", hidden: "" });
    file.addEventListener("change", () => { const f = file.files && file.files[0]; file.value = ""; if (f) wiImportFile(f); });
    const im = btn("wiImport", "Загрузить сценарий", () => file.click());
    const exb = btn("wiExplainBtn", "Объяснить сценарий", wiExplain); exb.disabled = !WI.points.length;
    row4.append(ex, im, exb, file);
    b.append(row4);
    if (WI.explain) {
      const cur = WI.points.length ? X.scenarioDigest(wiScenario(), res, F) : null;
      if (cur !== WI.explain.digest) WI.explain = null;  // scenario changed after the request: old text is never shown
      else {
        const box = el("div", { class: "explain", id: "wiExplainText" });
        box.append(el("div", { class: "who" }, `шаблонное объяснение по вычисленным фактам (не LLM) · отпечаток ${WI.explain.digest}`));
        for (const line of WI.explain.text.split("\n")) box.append(el("p", null, line));
        b.append(box);
      }
    }
  }
  function wiExportText() { return X.exportScenario(wiScenario(), D, F); }
  function wiExport() {
    let text;
    try { text = wiExportText(); } catch (e) { WI.msg = "Сохранить нельзя: " + (e.detail || e.message); renderWhatIf(); return; }
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const a = el("a", { href: url, download: `whatif-${STATE.city}-${WI.category}.json` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    WI.msg = `Сценарий сохранён: whatif-${STATE.city}-${WI.category}.json (входные поля и пометка, что результаты пересчитываются).`;
    renderWhatIf();
  }
  // Import: nothing in STATE changes unless the whole file passes strict validation; results are recomputed.
  function wiImportText(text) {
    let sc;
    try { sc = X.importScenario(text, D, F).scenario; } catch (e) {
      WI.msg = "Файл не принят, текущий сценарий не изменён: " + String(e.detail || e.message).slice(0, 200);
      renderWhatIf(); return false;
    }
    if (sc.city_id !== STATE.city) switchCity(sc.city_id);
    WI.category = sc.category; WI.points = sc.control_points.map((p) => ({ ...p }));
    WI.proposed = sc.proposed_object ? { id: sc.proposed_object.id, lon: sc.proposed_object.lon, lat: sc.proposed_object.lat } : null;
    WI.seq = WI.points.length + 1; WI.explain = null; WI.mode = null; $("map").classList.remove("wimode");
    WI.msg = `Сценарий загружен (${D.cities[sc.city_id].label}, ${X.CATEGORIES[sc.category]}): расстояния пересчитаны заново, числа из файла не используются.`;
    wiRefresh();
    return true;
  }
  function wiImportFile(f) {
    if (f.size > X.MAX_BYTES) { WI.msg = `Файл не принят: ${f.size} байт больше ${X.MAX_BYTES}. Текущий сценарий не изменён.`; renderWhatIf(); return; }
    f.text().then(wiImportText, () => { WI.msg = "Файл не прочитан; текущий сценарий не изменён."; renderWhatIf(); });
  }
  function wiExplain() {
    if (!WI.points.length) return;
    const sc = wiScenario(), res = wiResult(), digest = X.scenarioDigest(sc, res, F);
    const names = Object.fromEntries(D.cities[STATE.city].places.map((p) => [p.id, p.name || "Без названия"]));
    try { WI.explain = { digest, text: X.explain(sc, res, names, digest, F).text }; }
    catch (e) { WI.explain = null; WI.msg = "Объяснение отклонено: " + (e.detail || e.message); }
    renderWhatIf();
  }

  buildToolbar();
  setupInteraction();
  setupProjection(STATE.city);
  fitView();
  renderAll();
  updateStatus();
  function selectSegment(id) { STATE.selected = { type: "segment", id }; renderSelection(); renderExplain(); updateStatus(); }
  // Tool switch (round 8): v1 and v2 keep their own state; switching only stops placement modes and swaps the card/layer.
  function setTool(t) {
    if (t !== "v1" && t !== "v2") return;
    STATE.tool = t;
    if (STATE.pointMode) { STATE.pointMode = false; $("pointBtn").setAttribute("aria-pressed", "false"); $("map").classList.remove("pointmode"); }
    WI.mode = null; $("map").classList.remove("wimode"); stopExt();
    document.querySelectorAll("#toolSeg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tool === t)));
    renderWhatIf(); for (const f of EXT.onTool) f(t); renderMap(); updateStatus();
  }
  document.querySelectorAll("#toolSeg button").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));
  window.CITY_APP = { state: STATE, switchCity, selectPlace, selectSegment, visiblePlaces, clearSelection,
    wiPlace, setWiMode, setWiCategory, wiScenario, wiResult, wiImportText, wiExportText, setTool,
    // internal helpers for plan-ui.js (same page, not a public API)
    ui: { el, sv, $, D, F, EXT, toScreen, renderMap, updateStatus, qaOf, selectPlace, fmtM, stopV1: () => { setWiMode(null, true);
      if (STATE.pointMode) { STATE.pointMode = false; $("pointBtn").setAttribute("aria-pressed", "false"); $("map").classList.remove("pointmode"); } } } };  // for the headless smoke test
})();
