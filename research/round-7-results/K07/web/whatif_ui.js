/* K07 round 7 — UX of the "если добавить объект" scenario (proposal for prototypes/city-evidence/web/).
 * UI only: explicit mode, category, 1..10 control points, one hypothetical proposed object, move / delete,
 * bbox rejection, reset on city / category change, keyboard and narrow screens. Spec: research/round-7/FEATURE_SPEC.txt.
 *
 * NO distance engine here (FEATURE_SPEC formula belongs to the calculation module, K05/BUILD). The table calls
 *   window.CITY_WHATIF_ENGINE.compute({ scenario, data, city })
 *   -> { rows: [{ control_point_id, before_m, after_m, delta_m, nearest_before: {record_id, name, source, qa:[codes]} | null }],
 *        notes: [string] }
 * If no engine is loaded the table says so. Strings are inserted with textContent only.
 * Hooks used in app.js (see patch): init(app), drawLayer(svg, ctx), onMapClick(lonlat, event), onMapEnter(lonlat),
 * onCitySwitch(city), onBasePointMode(on).
 */
(function () {
  "use strict";
  const SVGNS = "http://www.w3.org/2000/svg";
  const MAX_POINTS = 10;
  const CATEGORIES = { school: "Школа", outpatient_clinic: "Поликлиника" };   // MVP categories (FEATURE_SPEC)
  const NO_SOURCE_TEXT = "В срезе нет исходных записей; улучшение не вычисляется";
  const $ = (id) => document.getElementById(id);
  function el(tag, attrs, text) {
    const e = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function sv(tag, attrs) {
    const e = document.createElementNS(SVGNS, tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
    return e;
  }
  const fmtCoord = (p) => `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`;
  const fmtM = (m) => (m === null || m === undefined || !isFinite(m) ? "—" : m >= 1000 ? (m / 1000).toFixed(2).replace(".", ",") + " км" : Math.round(m) + " м");

  let APP = null;
  const S = { active: false, tool: "control", category: "school", points: [], proposed: null, nextId: 1, pending: null, city: null };

  function data() { return window.CITY_EVIDENCE; }
  function bbox() { return data().cities[S.city].bbox; }  // [W, S, E, N] of the saved K10 square
  function inBbox(lon, lat) { const [w, s, e, n] = bbox(); return isFinite(lon) && isFinite(lat) && lon >= w && lon <= e && lat >= s && lat <= n; }

  function scenario() {  // city-whatif-v1 shape without source_snapshot (computed by BUILD from the manifest, not here)
    return {
      schema_version: "city-whatif-v1", city_id: S.city, source_snapshot: null, category: S.category,
      control_points: S.points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat })),
      proposed_object: S.proposed ? { id: S.proposed.id, lon: S.proposed.lon, lat: S.proposed.lat, category: S.category, kind: "hypothetical" } : null,
    };
  }

  // ---------- messages ----------
  function say(text, where) {
    const m = $("wiMsg"); if (m) m.textContent = text;
    const mm = $("wiMapMsg"); if (mm) { mm.textContent = text; mm.hidden = !text; }
    if (where === "silent") return;
  }

  // ---------- state changes ----------
  function reset(reason) {
    const had = S.points.length || S.proposed;
    S.points = []; S.proposed = null; S.nextId = 1; S.pending = null;
    if (reason && had) say(`Сценарий сброшен: ${reason}.`);
    else if (reason) say("");
    render();
  }
  function place(lon, lat) {
    if (!inBbox(lon, lat)) {
      const b = bbox().map((x) => x.toFixed(4)).join(", ");
      say(`Вне квадрата среза (${b}): не поставлено. Расчёт возможен только внутри сохранённого bbox.`);
      return false;
    }
    if (S.pending) {  // move an existing item
      const it = S.pending.type === "proposed" ? S.proposed : S.points.find((p) => p.id === S.pending.id);
      S.pending = null;
      if (it) { it.lon = lon; it.lat = lat; say(`${label(it)} перемещена: ${fmtCoord(it)}.`); }
      render(); return true;
    }
    if (S.tool === "proposed") {
      const moved = !!S.proposed;
      S.proposed = { id: "proj-1", lon, lat };
      say(moved ? `Проектный объект перемещён: ${fmtCoord(S.proposed)} (он один в сценарии).` : `Проектный объект поставлен: ${fmtCoord(S.proposed)}.`);
      render(); return true;
    }
    if (S.points.length >= MAX_POINTS) { say(`Не больше ${MAX_POINTS} контрольных точек: удалите одну, чтобы поставить новую.`); return false; }
    const p = { id: `cp-${S.nextId++}`, lon, lat };
    S.points.push(p);
    say(`${label(p)} поставлена: ${fmtCoord(p)} (${S.points.length} из ${MAX_POINTS}).`);
    render(); return true;
  }
  function label(it) { return it.id === "proj-1" ? "Проектный объект" : `Точка ${it.id.slice(3)}`; }
  function remove(type, id) {
    if (type === "proposed") { S.proposed = null; say("Проектный объект удалён: показан исходный вариант (до)."); }
    else { S.points = S.points.filter((p) => p.id !== id); say(`Точка ${id.slice(3)} удалена.`); }
    if (S.pending && (S.pending.type === type && (type === "proposed" || S.pending.id === id))) S.pending = null;
    render();
  }
  function startMove(type, id) {
    S.pending = { type, id };
    const it = type === "proposed" ? S.proposed : S.points.find((p) => p.id === id);
    say(`Перемещение: ${label(it)}. Нажмите на карту в квадрате или наведите центр карты стрелками и нажмите Enter. Escape — отмена.`);
    render();
  }
  function setActive(on) {
    S.active = !!on;
    const b = $("whatifBtn"); if (b) b.setAttribute("aria-pressed", String(S.active));
    if (S.active && APP && APP.state.pointMode && APP.setPointMode) APP.setPointMode(false);  // one map tool at a time
    if (!S.active) { S.pending = null; say(S.points.length || S.proposed ? "Сценарий скрыт; точки сохраняются до смены города или категории." : ""); }
    else say(`Режим сценария: ${S.tool === "proposed" ? "клик/Enter на карте ставит проектный объект" : "клик/Enter на карте ставит контрольную точку"}.`);
    render();
  }

  // ---------- rendering ----------
  function render() {
    const card = $("whatifCard"); if (!card) return;
    card.hidden = !S.active;
    $("map") && $("map").classList.toggle("whatifmode", S.active);
    // tool radios
    for (const r of document.querySelectorAll('input[name="wiTool"]')) r.checked = r.value === S.tool;
    $("wiCount").textContent = `${S.points.length} из ${MAX_POINTS}`;
    // control points list
    const ol = $("wiList"); ol.replaceChildren();
    if (!S.points.length) ol.append(el("li", { class: "muted" }, "Контрольных точек нет. Выберите «Контрольная точка» и нажмите на карту (или Enter на карте)."));
    for (const p of S.points) {
      const li = el("li", { "data-wi-point": p.id, class: S.pending && S.pending.id === p.id ? "wi-pending" : null });
      li.append(el("span", { class: "wi-label" }, `${label(p)} · ${fmtCoord(p)}`));
      const mv = el("button", { type: "button", class: "tool", "data-wi-move": p.id, "aria-label": `Переместить ${label(p)}` }, "Переместить");
      const rm = el("button", { type: "button", class: "tool", "data-wi-del": p.id, "aria-label": `Удалить ${label(p)}` }, "Удалить");
      mv.addEventListener("click", () => startMove("control", p.id));
      rm.addEventListener("click", () => remove("control", p.id));
      li.append(mv, rm); ol.append(li);
    }
    // proposed object
    const pr = $("wiProposed"); pr.replaceChildren();
    if (!S.proposed) pr.append(el("span", { class: "muted" }, `не поставлен (категория: ${CATEGORIES[S.category]})`));
    else {
      pr.append(el("span", { class: "wi-label" }, `${CATEGORIES[S.category]}, гипотетический · ${fmtCoord(S.proposed)}`));
      const mv = el("button", { type: "button", class: "tool", id: "wiProjMove" }, "Переместить");
      const rm = el("button", { type: "button", class: "tool", id: "wiProjDel" }, "Удалить");
      mv.addEventListener("click", () => startMove("proposed"));
      rm.addEventListener("click", () => remove("proposed"));
      pr.append(mv, rm);
    }
    $("wiCancelMove").hidden = !S.pending;
    $("wiReset").disabled = !S.points.length && !S.proposed;
    renderTable();
    if (APP) APP.renderMap();  // redraws the scenario layer through drawLayer()
  }
  function renderTable() {
    const box = $("wiResult"); box.replaceChildren();
    if (!S.points.length) { box.append(el("p", { class: "muted" }, "Таблица до/после появится после первой контрольной точки.")); return; }
    const eng = window.CITY_WHATIF_ENGINE;
    let res = null, err = null;
    if (eng && typeof eng.compute === "function") {
      try { res = eng.compute({ scenario: scenario(), data: data(), city: S.city }); } catch (e) { err = e; }
    }
    const tbl = el("table", { class: "wi-table", "aria-label": "Расстояние по прямой до ближайшей записи среза: до и после" });
    const tr = el("tr");
    const HEAD = ["Точка", "До", "После", "Разница", "Ближайшая запись (до)"];  // data-label: stacked rows at <= 480 px
    HEAD.forEach((h, i) => tr.append(el("th", { class: i && i < 4 ? "num" : null }, h)));
    const th = el("thead"); th.append(tr); tbl.append(th);
    const tb = el("tbody");
    for (const p of S.points) {
      const row = res && Array.isArray(res.rows) ? res.rows.find((r) => r.control_point_id === p.id) : null;
      const r = el("tr", { "data-wi-row": p.id });
      r.append(el("td", { "data-label": HEAD[0] }, label(p)));
      if (!row) { for (let i = 1; i < 5; i++) r.append(el("td", { class: "muted", "data-label": HEAD[i] }, "—")); tb.append(r); continue; }
      const noSource = row.before_m === null || row.before_m === undefined;
      r.append(el("td", { class: "num", "data-label": HEAD[1] }, fmtM(row.before_m)), el("td", { class: "num", "data-label": HEAD[2] }, fmtM(row.after_m)),
        el("td", { class: "num", "data-label": HEAD[3] }, noSource ? "—" : row.delta_m > 0 ? "−" + fmtM(row.delta_m) : fmtM(row.delta_m)));
      const n = row.nearest_before;
      const td = el("td", { "data-label": HEAD[4] }, noSource ? NO_SOURCE_TEXT : n ? `${n.name || "Без названия"} · ${n.source || "источник не указан"}${n.qa && n.qa.length ? " · ⚠ " + n.qa.join(", ") : ""}` : "—");
      r.append(td); tb.append(r);
    }
    tbl.append(tb); box.append(tbl);
    if (err) box.append(el("p", { class: "err" }, "Расчёт не выполнен: " + (err.message || String(err))));
    else if (!res) box.append(el("p", { class: "muted", id: "wiNoEngine" }, "Расчёт до/после выполняет отдельный модуль (K05 / BUILD); в этом UI-прототипе он не подключён, поэтому в таблице прочерки."));
    else {
      box.append(el("p", { class: "muted" }, "«Разница» — уменьшение расстояния по прямой до ближайшей записи среза; это не время пешком и не улучшение образования или здоровья. Ближайшая запись в срезе — не обязательно ближайшее учреждение в городе."));
      for (const n of res.notes || []) box.append(el("p", { class: "muted" }, n));
    }
  }
  // scenario layer on top of the map (called by app.js renderMap)
  function drawLayer(svg, ctx) {
    if (!S.active) return;
    const g = sv("g", { "data-whatif": "layer" });
    for (const p of S.points) {
      const [x, y] = ctx.toScreen(p.lon, p.lat);
      const m = sv("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`, "data-whatif": p.id, "aria-hidden": "true" });
      m.append(sv("circle", { r: 9, fill: "var(--surface)", stroke: "var(--ink)", "stroke-width": 2, "stroke-dasharray": S.pending && S.pending.id === p.id ? "3 2" : null }));
      const t = sv("text", { "text-anchor": "middle", y: 4, "font-size": 10, "font-weight": 700, fill: "var(--ink)" }); t.textContent = p.id.slice(3);
      m.append(t); g.append(m);
    }
    if (S.proposed) {
      const [x, y] = ctx.toScreen(S.proposed.lon, S.proposed.lat);
      const m = sv("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`, "data-whatif": "proj-1", "aria-hidden": "true" });
      const star = Array.from({ length: 10 }, (_, i) => { const a = Math.PI / 5 * i - Math.PI / 2, r = i % 2 ? 5 : 12; return `${(r * Math.cos(a)).toFixed(1)} ${(r * Math.sin(a)).toFixed(1)}`; });
      m.append(sv("path", { d: "M" + star.join("L") + "Z", fill: "var(--surface)", stroke: "var(--ink)", "stroke-width": 2, "stroke-dasharray": "3 2" }));
      const t = sv("text", { x: 15, y: 4, "font-size": 11, fill: "var(--ink)" }); t.textContent = "Проект (гипотеза)";
      m.append(t); g.append(m);
    }
    // keyboard target: Enter on the focused map places the current item at the centre. Always drawn, shown only by CSS
    // (#map:focus): re-rendering the map on focus/blur would replace a marker between pointerdown and click (r7 W8).
    const cx = svg.clientWidth / 2, cy = svg.clientHeight / 2, tg = sv("g", { class: "wi-target", "data-whatif": "target", "aria-hidden": "true" });
    tg.append(sv("circle", { cx, cy, r: 11, fill: "none", stroke: "var(--focus)", "stroke-width": 2 }),
      sv("path", { d: `M${cx - 15} ${cy}H${cx - 6}M${cx + 6} ${cy}H${cx + 15}M${cx} ${cy - 15}V${cy - 6}M${cx} ${cy + 6}V${cy + 15}`, stroke: "var(--focus)", "stroke-width": 2 }));
    g.append(tg);
    svg.append(g);
  }

  // ---------- hooks from app.js ----------
  function onMapClick(lonlat, ev) {
    if (!S.active) return false;
    if (ev && ev.target && ev.target.closest && ev.target.closest("[data-whatif]")) return true;  // own marker: no new item
    place(lonlat[0], lonlat[1]);
    return true;
  }
  function onMapEnter(lonlat) { if (!S.active) return false; place(lonlat[0], lonlat[1]); return true; }
  function onCitySwitch(city) { if (S.city && city !== S.city) { S.city = city; reset("смена города — точки не переносятся между городами"); } S.city = city; }
  function onBasePointMode(on) { if (on && S.active) setActive(false); }

  function init(app) {
    APP = app; S.city = app.state.city;
    $("whatifBtn").addEventListener("click", () => setActive(!S.active));
    $("wiCat").addEventListener("change", (e) => { S.category = e.target.value; reset("смена категории"); });
    for (const r of document.querySelectorAll('input[name="wiTool"]')) r.addEventListener("change", (e) => { S.tool = e.target.value; S.pending = null; setActive(true); });
    $("wiReset").addEventListener("click", () => reset("по кнопке «Сбросить сценарий»"));
    $("wiCancelMove").addEventListener("click", () => { S.pending = null; say("Перемещение отменено."); render(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.pending) { S.pending = null; say("Перемещение отменено."); render(); } });
    render();
  }

  window.CITY_WHATIF_UI = { init, drawLayer, onMapClick, onMapEnter, onCitySwitch, onBasePointMode, setActive, scenario,
    _state: S, MAX_POINTS, NO_SOURCE_TEXT };
})();
