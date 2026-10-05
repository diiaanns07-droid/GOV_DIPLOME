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

  const SHAPES = { school: "circle", outpatient_clinic: "circle", preschool: "triangle", pharmacy: "triangle",
    college_university: "square", hospital: "square", government_office: "diamond" };
  const SECTOR_LABEL = { education: "образование", health: "здравоохранение", government: "госучреждения" };
  const FOOT_COLOR = { unknown: "var(--muted)", conditional: "var(--warning)", denied: "var(--critical)", allowed: "var(--good)" };
  const ORDER = (D.city_order || Object.keys(D.cities)).filter((k) => D.cities[k]);
  const STATE = { city: ORDER[0], groups: new Set(Object.keys(D.groups)), places: true, roads: true,
    roadStyle: "plain", pointMode: false, point: null, selected: null, view: null, epoch: 0 };

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
    $("tRoads").addEventListener("change", (e) => { STATE.roads = e.target.checked; renderMap(); });
    $("roadStyle").addEventListener("change", (e) => { STATE.roadStyle = e.target.value; renderRoadLegend(); renderMap(); });
    $("pointBtn").addEventListener("click", () => {
      STATE.pointMode = !STATE.pointMode;
      $("pointBtn").setAttribute("aria-pressed", String(STATE.pointMode));
      $("map").classList.toggle("pointmode", STATE.pointMode);
    });
    $("zIn").addEventListener("click", () => zoomBy(1.5));
    $("zOut").addEventListener("click", () => zoomBy(1 / 1.5));
    $("zReset").addEventListener("click", () => { fitView(); renderMap(); });
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
    STATE.city = key; STATE.point = null; STATE.selected = null; STATE.epoch += 1;
    hideTip();
    document.querySelectorAll("#citySeg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.city === key)));
    setupProjection(key); fitView(); renderAll();
  }
  // Filter change: a selected object that is no longer visible is deselected; explanations are recomputed.
  function onFilterChange() {
    STATE.epoch += 1;
    const s = STATE.selected;
    if (s && s.type === "place" && !visiblePlaces().some((p) => p.id === s.id)) STATE.selected = null;
    renderAll();
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
    svg.replaceChildren();
    const gBox = sv("g"), gRoad = sv("g"), gPoint = sv("g"), gMark = sv("g"), gLabel = sv("g");
    svg.append(gBox, gRoad, gPoint, gMark, gLabel);
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
      const pick = (ev) => { ev.stopPropagation(); STATE.selected = { type: "segment", id: sg.id }; renderSelection(); renderExplain(); };
      hit.addEventListener("click", pick);
      hit.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(ev); } });
      gRoad.append(hit);
    }
    if (STATE.point) {
      const [sx, sy] = toScreen(STATE.point[0], STATE.point[1]);
      gPoint.append(sv("path", { d: `M${sx - 8} ${sy}H${sx + 8}M${sx} ${sy - 8}V${sy + 8}`, stroke: "var(--ink)", "stroke-width": 2 }));
    }
    const places = visiblePlaces();
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
      g.addEventListener("pointermove", (ev) => showTip(ev, [p.name || "Без названия", `${p.group_label} · conf. ${p.confidence ?? "—"}`]));
      g.addEventListener("pointerleave", hideTip);
      const pick = (ev) => { ev.stopPropagation(); selectPlace(p.id); };
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(ev); } });
      gMark.append(g);
    }
    const msg = $("mapMsg");
    if (!STATE.places) { msg.hidden = false; msg.textContent = "Слой объектов выключен."; }
    else if (!STATE.groups.size) { msg.hidden = false; msg.textContent = "Не выбрана ни одна категория — включите категории в панели фильтров."; }
    else if (!places.length) { msg.hidden = false; msg.textContent = "В этом квадрате нет записей выбранных категорий. Это не значит, что таких объектов нет на местности."; }
    else msg.hidden = true;
    $("attrib").textContent = "© OpenStreetMap contributors; Overture Maps Foundation · " + c.release;
  }
  function selectPlace(id) { STATE.selected = { type: "place", id }; renderMap(); renderSelection(); renderTable(); renderExplain(); }

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
      if (!d || d.moved || !STATE.pointMode) return;
      if (e.target.closest && e.target.closest('[role="button"]')) return;
      const r = svg.getBoundingClientRect();
      STATE.point = toLonLat(e.clientX - r.left, e.clientY - r.top);
      STATE.selected = { type: "point" };
      renderMap(); renderSelection(); renderExplain();
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
        ["Мощность / места", null, "нет источника"],
        ["Работает ли сейчас", p.operating_status, "Overture"],
      ]);
      body.append(dl);
      const det = el("details"); det.append(el("summary", null, "Источник записи"));
      const ul = el("ul", { class: "reasons" });
      for (const src of p.sources) ul.append(el("li", null, `${src.dataset} · ${src.license} · ${fmtDate(src.update_time)}${src.record_id ? " · " + src.record_id : ""}`));
      det.append(ul, el("p", { class: "muted" }, `Overture id ${p.id} (v${p.overture_version}). Наличие записи не подтверждает, что объект работает; отсутствие записи не означает, что объекта нет.`));
      body.append(det);
    } else if (s.type === "segment") {
      const g = c.segments.find((x) => x.id === s.id);
      if (!g) { STATE.selected = null; empty.hidden = false; return; }
      body.append(el("h3", null, "Дорога (OSM через Overture)"));
      const dl = el("dl");
      dlRows(dl, [
        ["Класс", g.class + (g.subclass ? " / " + g.subclass : ""), "наблюдение"],
        ["Название", g.name, null],
        ["Длина", fmtM(g.length_m) + (g.crosses_edge ? " (вся линия, выходит за квадрат)" : ""), "геодезическая, K10"],
        ["Проход пешком", D.foot_access_labels[g.foot_access], g.foot_access],
        ["Мост / тоннель", g.flags.length ? g.flags.join(", ") : "не отмечено", "road_flags"],
        ["Источник", `${g.record_id || "—"} · ${g.license || "—"} · ${fmtDate(g.update_time)}`, null],
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
      ["Записей объектов", `${k.places} в срезе`, "не реестр города"],
      ["Сегментов дорог", `${k.segments} (из них ${k.segments_crossing_edge} выходят за край)`, null],
    ]);
    b.append(dl, el("h3", null, "Проход пешком по данным"));
    const ul = el("ul", { class: "reasons" });
    for (const key of ["unknown", "conditional", "denied", "allowed"])
      ul.append(el("li", null, `${D.foot_access_labels[key]}: ${k.foot_access[key] || 0}`));
    b.append(ul, el("p", { class: "muted" }, "Неполнота: Overture не содержит все соцобъекты; мощность, население и официальный состав районов в пакете отсутствуют."));
  }
  function renderProvenance() {
    const c = D.cities[STATE.city], b = $("provBody");
    b.replaceChildren();
    const dl = el("dl");
    dlRows(dl, [
      ["Пакет", `K10 раунд 3 · ${D.inputs.k10_branch} @ ${D.inputs.k10_sha.slice(0, 10)}`, "source_manifest.json"],
      ["Коммит данных", D.inputs.k10_data_commit.slice(0, 10), null],
      ["Атрибуция", (c.attribution || []).join("; "), null],
      ["Вид данных", c.kind, null],
    ]);
    b.append(dl, el("h3", null, "Файлы и SHA256"));
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
      tr.append(el("td", null, p.name || "Без названия"), el("td", null, p.group_label), el("td", null, districtText(p)[0]), el("td", { class: "num" }, p.confidence ?? "—"));
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
  function renderAll() { renderMap(); renderSelection(); renderSlice(); renderExplain(); renderTable(); renderProvenance(); }

  buildToolbar();
  setupInteraction();
  setupProjection(STATE.city);
  fitView();
  renderAll();
  window.CITY_APP = { state: STATE, switchCity, selectPlace, visiblePlaces };  // for the headless smoke test
})();
