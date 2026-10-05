/* «Несколько объектов (v2)» — UI of city-plan-v2 (CORE_SPEC round 8) on top of app.js.
 * Uses the pure module plan.js for every number; this file only edits state, draws the hypothetical layer and cards.
 * Candidates are hypothetical, costs are conditional units entered by the user (or an explicitly SYNTHETIC demo set).
 * Strings are inserted with textContent only. The original records of the slice are never modified.
 */
(function () {
  "use strict";
  const APP = window.CITY_APP, PL = window.CITY_PLAN;
  if (!APP || !APP.ui || !PL || !APP.ui.F || !APP.ui.F.sha256hex) return;
  const { el, sv, $, D, F, EXT, toScreen, renderMap, updateStatus, qaOf, selectPlace, fmtM } = APP.ui;
  const STATE = APP.state;
  const PS = { category: "school", points: [], cands: [], budget: 1000, max_selected: 3, radius: 500, required: [], excluded: [], selected: [],
    mode: null, moveId: null, seqP: 1, seqK: 1, msg: "", demo: false };
  const ctxCache = {};
  const ctxOf = (city) => ctxCache[city] || (ctxCache[city] = PL.makeContext(D, city, F));
  const mmText = (mm) => (mm === null || mm === undefined ? "нет данных" : fmtM(mm / 1000));
  const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
  // collapsible sections; open state survives re-render (long lists of 25 points / 16 candidates)
  const OPEN = {};
  function section(parent, id, title, openByDefault) {
    const d = el("details", { id, class: "pl-sec" });
    d.open = id in OPEN ? OPEN[id] : openByDefault;
    const sm = el("summary", null, title);
    sm.addEventListener("click", () => { OPEN[id] = !d.open; });  // only a user toggle is remembered
    d.append(sm);
    parent.append(d);
    return d;
  }

  // ---------- scenario from the editor state (validated by plan.js; empty point list allowed in the editor) ----------
  function rawScenario() {
    const ctx = ctxOf(STATE.city);
    return { schema_version: PL.SCHEMA, city_id: STATE.city, source_snapshot: ctx.source_snapshot, category: PS.category,
      control_points: PS.points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, weight: p.weight })),
      candidates: PS.cands.map((c) => ({ id: c.id, lon: c.lon, lat: c.lat, category: PS.category, kind: "hypothetical", cost: c.cost })),
      budget: PS.budget, max_selected: PS.max_selected, coverage_radius_m: PS.radius,
      required_ids: PS.required.slice(), excluded_ids: PS.excluded.slice(), selected_ids: PS.selected.slice() };
  }
  const scenario = () => PL.validatePlanScenario(rawScenario(), ctxOf(STATE.city), { requirePoints: false });
  function evaluate() { const sc = scenario(); return sc.control_points.length ? PL.evaluatePlan(ctxOf(STATE.city), sc, sc.selected_ids) : null; }

  // ---------- state changes (every change re-renders; optimizer results are tied to problem_digest) ----------
  function changed(msg) { if (msg !== undefined) PS.msg = msg; onProblemChange(); render(); renderMap(); updateStatus(); }
  function reset(reason) {
    Object.assign(PS, { points: [], cands: [], required: [], excluded: [], selected: [], mode: null, moveId: null, seqP: 1, seqK: 1, demo: false, msg: reason || "" });
    if (typeof OS !== "undefined") { if (OS.status === "running") for (const j of OS.jobs || []) j.s.cancel(); Object.assign(OS, { status: "idle", result: null, sens: null, msg: "", backup: null }); OS.request_id++; }
    $("map").classList.remove("planmode");
  }
  function setMode(mode, moveId) {
    PS.mode = PS.mode === mode && (mode !== "move" || PS.moveId === moveId) ? null : mode;
    PS.moveId = PS.mode === "move" ? moveId : null;
    if (PS.mode) APP.ui.stopV1();
    $("map").classList.toggle("planmode", !!PS.mode);
    render(); renderMap(); updateStatus();
  }
  const nextId = (prefix, key, list) => { let id; do { id = prefix + PS[key]++; } while (list.some((x) => x.id === id)); return id; };
  function place([lon, lat]) {
    if (!PS.mode) return false;
    if (!PL.LIMITS || !inBbox(lon, lat)) { changed("Место вне квадрата среза — туда ставить нельзя."); return false; }
    if (PS.mode === "points") {
      if (PS.points.length >= PL.LIMITS.points) { changed(`Не больше ${PL.LIMITS.points} контрольных точек.`); return false; }
      const id = nextId("P", "seqP", PS.points);
      PS.points.push({ id, lon, lat, weight: 1 });
      changed(`Контрольная точка ${id} (вес 1) поставлена.`);
    } else if (PS.mode === "cands") {
      if (PS.cands.length >= PL.LIMITS.candidates) { changed(`Не больше ${PL.LIMITS.candidates} кандидатных мест.`); return false; }
      const id = nextId("K", "seqK", PS.cands);
      PS.cands.push({ id, lon, lat, cost: 100 });
      changed(`Кандидат ${id} поставлен; стоимость по умолчанию 100 усл. ед. — задайте свою.`);
    } else if (PS.mode === "move") {
      const c = PS.cands.find((x) => x.id === PS.moveId);
      if (!c) return false;
      c.lon = lon; c.lat = lat; PS.mode = null; PS.moveId = null; $("map").classList.remove("planmode");
      changed(`Кандидат ${c.id} перенесён — всё пересчитано.`);
    }
    return true;
  }
  function inBbox(lon, lat) { const b = D.cities[STATE.city].bbox; return b[0] <= lon && lon <= b[2] && b[1] <= lat && lat <= b[3]; }
  const without = (arr, id) => arr.filter((x) => x !== id);
  function removePoint(id) { PS.points = PS.points.filter((p) => p.id !== id); changed(`Точка ${id} удалена.`); }
  function removeCand(id) {
    PS.cands = PS.cands.filter((c) => c.id !== id);
    PS.required = without(PS.required, id); PS.excluded = without(PS.excluded, id); PS.selected = without(PS.selected, id);
    if (PS.moveId === id) { PS.mode = null; PS.moveId = null; }
    changed(`Кандидат ${id} удалён (и из ограничений, и из ручного плана).`);
  }
  function setStatus(id, st) {
    PS.required = without(PS.required, id); PS.excluded = without(PS.excluded, id);
    if (st === "required") PS.required.push(id);
    if (st === "excluded") PS.excluded.push(id);
    changed();
  }
  function toggleSelected(id, on) { PS.selected = on ? [...new Set([...PS.selected, id])] : without(PS.selected, id); changed(); }
  function setNumber(what, raw, lo, hi, apply) {
    const v = Number(raw);
    if (raw === "" || !isInt(v, lo, hi)) { changed(`${what}: нужно целое ${lo}..${hi}; значение не применено.`); return false; }
    apply(v); changed(); return true;
  }
  function setCategory(cat) {
    if (!PL.CATEGORIES[cat] || cat === PS.category) return;
    const had = PS.points.length || PS.cands.length;
    PS.category = cat;
    reset(had ? `Категория изменена на «${PL.CATEGORIES[cat]}» — сценарий v2, результаты поиска и объяснение сброшены.` : "");
    changed();
  }
  // SYNTHETIC demo set: grid inside the square; costs and weights are invented and labelled as such.
  function demoSet() {
    reset("");
    const [w, s, e, n] = D.cities[STATE.city].bbox, g = (fx, fy) => [w + (e - w) * fx, s + (n - s) * fy];
    for (let k = 0; k < 10; k++) { const [lon, lat] = g(0.12 + 0.76 * ((k % 5) / 4), k < 5 ? 0.3 : 0.7); PS.points.push({ id: `P${k + 1}`, lon, lat, weight: 1 + (k * 7) % 10 }); }
    for (let k = 0; k < 8; k++) { const [lon, lat] = g(0.15 + 0.7 * ((k % 4) / 3), k < 4 ? 0.2 : 0.8); PS.cands.push({ id: `K${k + 1}`, lon, lat, cost: 100 + (k * 37) % 400 }); }
    PS.seqP = 11; PS.seqK = 9; PS.budget = 600; PS.max_selected = 3; PS.radius = 400; PS.demo = true;
    changed("Демо-набор загружен: 10 точек и 8 кандидатов. Места, стоимости и веса ВЫДУМАНЫ для показа (synthetic), это не данные города.");
  }

  // ---------- optimizer hooks (stage 2 fills these) ----------
  const OPT = { onProblemChange: [], render: [] };
  function onProblemChange() { for (const f of OPT.onProblemChange) f(); }

  // ---------- map layer: only when the v2 tool is active; never mixed into observed counters ----------
  function layer(g, gLabel) {
    if (STATE.tool !== "v2" || (!PS.points.length && !PS.cands.length)) return;
    let res = null;
    try { res = evaluate(); } catch (e) { res = null; }
    const byId = Object.fromEntries(D.cities[STATE.city].places.map((p) => [p.id, p]));
    const cById = Object.fromEntries(PS.cands.map((c) => [c.id, c]));
    if (res) for (const r of res.rows) {
      const t = r.nearest_after && (r.nearest_after.kind === "hypothetical" ? cById[r.nearest_after.id] : byId[r.nearest_after.id]);
      if (!t) continue;
      const [a, b] = toScreen(r.lon, r.lat), [c, d] = toScreen(t.lon, t.lat);
      g.append(sv("line", { x1: a, y1: b, x2: c, y2: d, stroke: r.nearest_after.kind === "hypothetical" ? "var(--critical)" : "var(--ink-2)", "stroke-width": 1.1, "stroke-dasharray": "4 3" }));
    }
    for (const p of PS.points) {
      const [x, y] = toScreen(p.lon, p.lat);
      const m = sv("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`, "data-plan-point": p.id, role: "img", "aria-label": `Контрольная точка ${p.id}, вес ${p.weight}` });
      m.append(sv("rect", { x: -5, y: -5, width: 10, height: 10, fill: "var(--surface)", stroke: "var(--ink)", "stroke-width": 2 }));
      g.append(m);
      const t = sv("text", { x: x + 8, y: y + 4, "font-size": 10.5, fill: "var(--ink)" }); t.textContent = `${p.id}·в${p.weight}`; gLabel.append(t);
    }
    for (const c of PS.cands) {
      const [x, y] = toScreen(c.lon, c.lat), sel = PS.selected.includes(c.id), req = PS.required.includes(c.id), exc = PS.excluded.includes(c.id);
      const m = sv("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`, "data-plan-cand": c.id, role: "img",
        "aria-label": `Кандидат (гипотеза) ${c.id}, ${c.cost} усл. ед.${sel ? ", в ручном плане" : ""}${req ? ", обязателен" : ""}${exc ? ", исключён" : ""}` });
      m.append(sv("path", { d: "M0 -9L8 -4.5L8 4.5L0 9L-8 4.5L-8 -4.5Z", fill: sel ? "var(--critical)" : "var(--surface)", stroke: "var(--critical)", "stroke-width": req ? 3 : 1.6, "stroke-dasharray": exc ? "2 2" : null }));
      if (exc) m.append(sv("path", { d: "M-6 -6L6 6M6 -6L-6 6", stroke: "var(--ink)", "stroke-width": 1.5 }));
      g.append(m);
      const t = sv("text", { x: x + 11, y: y - 6, "font-size": 10.5, fill: "var(--critical)" }); t.textContent = `${c.id} · ${c.cost} у.е.`; gLabel.append(t);
    }
  }

  // ---------- card ----------
  const btn = (id, text, onClick, extra) => { const b = el("button", { type: "button", class: "tool", id, ...(extra || {}) }, text); b.addEventListener("click", onClick); return b; };
  function numInput(id, label, value, lo, hi, apply, what) {
    const lab = el("label", { class: "ctl", for: id }, label + " ");
    const inp = el("input", { type: "number", id, min: lo, max: hi, step: 1, value: String(value), inputmode: "numeric", class: "num-in" });
    inp.addEventListener("change", () => setNumber(what || label, inp.value.trim(), lo, hi, apply));
    lab.append(inp);
    return lab;
  }
  function render() {
    const card = $("planCard"), b = $("planBody");
    card.hidden = STATE.tool !== "v2";
    if (card.hidden) return;
    const focusId = document.activeElement && document.activeElement.id && b.contains(document.activeElement) ? document.activeElement.id : null;
    b.replaceChildren();
    b.append(el("p", { class: "muted" }, "Условный план: несколько гипотетических мест одной категории, условные стоимости и бюджет. Польза — только расстояние по прямой в пределах среза до выбранных вами контрольных точек. Не смета, не население, не вместимость, не пешая доступность."));
    const r1 = el("div", { class: "wi-ctl" });
    const sel = el("select", { id: "plCat" });
    for (const [k, v] of Object.entries(PL.CATEGORIES)) { const o = el("option", { value: k }, v); if (k === PS.category) o.selected = true; sel.append(o); }
    sel.addEventListener("change", () => setCategory(sel.value));
    r1.append(el("label", { for: "plCat" }, "Категория "), sel);
    const r2 = el("div", { class: "wi-ctl" });
    r2.append(btn("plModePoints", `Ставить контрольные точки (${PS.points.length}/${PL.LIMITS.points})`, () => setMode("points"), { "aria-pressed": String(PS.mode === "points") }),
      btn("plModeCands", `Ставить кандидатов (${PS.cands.length}/${PL.LIMITS.candidates})`, () => setMode("cands"), { "aria-pressed": String(PS.mode === "cands") }));
    const r3 = el("div", { class: "wi-ctl" });
    const clr = btn("plClear", "Сбросить план", () => { reset("Сценарий v2 сброшен."); changed(); }); clr.disabled = !PS.points.length && !PS.cands.length;
    r3.append(btn("plDemo", "Демо-набор (синтетический)", demoSet), clr);
    const r4 = el("div", { class: "wi-ctl" });
    r4.append(numInput("plBudget", "Бюджет, усл. ед.", PS.budget, 0, 1000000, (v) => { PS.budget = v; }, "Бюджет"),
      numInput("plMax", "Максимум объектов", PS.max_selected, 0, 5, (v) => { PS.max_selected = v; }, "Максимум объектов"),
      numInput("plRadius", "Радиус охвата, м", PS.radius, 100, 5000, (v) => { PS.radius = v; }, "Радиус охвата"));
    b.append(r1, r2, r3, r4, el("p", { class: "muted" }, "Радиус охвата — параметр анализа по прямой, не норматив пешей доступности. Бюджет и стоимости — условные единицы, не тенге."));
    b.append(el("p", { class: "wi-msg warn", id: "plMsg", role: "status", "aria-live": "polite" }, PS.msg));
    if (PS.demo) b.append(el("p", { class: "pill", id: "plDemoNote" }, "демо-набор: места, стоимости и веса выдуманы (synthetic)"));

    // points
    const secP = section(b, "plSecPoints", `Контрольные точки (${PS.points.length})`, PS.points.length <= 6);
    if (!PS.points.length) secP.append(el("p", { class: "muted" }, "Нет точек. Включите «Ставить контрольные точки» и нажмите на карту (Enter на карте — точка в центре). Вес 1..100 — ваш приоритет точки, не число жителей."));
    else {
      const ul = el("ul", { class: "wi-pts", id: "plPoints" });
      for (const p of PS.points) {
        const li = el("li", { "data-plan-item": p.id });
        li.append(el("span", null, p.id),
          numInput(`plW_${p.id}`, "вес", p.weight, 1, 100, (v) => { p.weight = v; }, `Вес ${p.id}`),
          btn(null, "Удалить", () => removePoint(p.id), { "aria-label": `Удалить контрольную точку ${p.id}` }));
        ul.append(li);
      }
      secP.append(ul);
    }
    // candidates
    const secC = section(b, "plSecCands", `Кандидатные места — гипотеза (${PS.cands.length})`, PS.cands.length <= 6);
    if (!PS.cands.length) secC.append(el("p", { class: "muted" }, "Нет кандидатов. Включите «Ставить кандидатов» и нажмите на карту. Стоимость задаёте вы (1..1 000 000 усл. ед.)."));
    else {
      const ul = el("ul", { class: "wi-pts pl-cands", id: "plCands" });
      for (const c of PS.cands) {
        const li = el("li", { "data-plan-cand-item": c.id });
        const st = el("select", { id: `plS_${c.id}`, "aria-label": `Ограничение для ${c.id}` });
        for (const [k, v] of [["free", "свободный"], ["required", "обязателен"], ["excluded", "исключён"]]) {
          const o = el("option", { value: k }, v);
          if ((k === "required" && PS.required.includes(c.id)) || (k === "excluded" && PS.excluded.includes(c.id)) || (k === "free" && !PS.required.includes(c.id) && !PS.excluded.includes(c.id))) o.selected = true;
          st.append(o);
        }
        st.addEventListener("change", () => setStatus(c.id, st.value));
        const chk = el("input", { type: "checkbox", id: `plSel_${c.id}` }); chk.checked = PS.selected.includes(c.id);
        chk.addEventListener("change", () => toggleSelected(c.id, chk.checked));
        const lab = el("label", { class: "chk", for: `plSel_${c.id}` }); lab.append(chk, document.createTextNode("в ручном плане"));
        li.append(el("strong", null, c.id), numInput(`plC_${c.id}`, "стоимость", c.cost, 1, 1000000, (v) => { c.cost = v; }, `Стоимость ${c.id}`), st, lab,
          btn(`plMove_${c.id}`, PS.mode === "move" && PS.moveId === c.id ? "Щёлкните на карте…" : "Перенести", () => setMode("move", c.id), { "aria-pressed": String(PS.mode === "move" && PS.moveId === c.id) }),
          btn(null, "Удалить", () => removeCand(c.id), { "aria-label": `Удалить кандидата ${c.id}` }));
        ul.append(li);
      }
      secC.append(ul);
    }
    renderManual(b);
    for (const f of OPT.render) f(b);
    if (focusId) { const f = document.getElementById(focusId); if (f) f.focus(); }
  }
  function renderManual(b) {
    b.append(el("h3", null, "Ручной план: до и после"));
    let res;
    try { res = evaluate(); } catch (e) { b.append(el("p", { class: "err" }, "Сценарий не прошёл проверку: " + (e.detail || e.message))); return; }
    if (!res) { b.append(el("p", { class: "muted" }, "Поставьте хотя бы одну контрольную точку.")); return; }
    const m = res.metrics, bl = res.baseline, f = res.feasibility;
    b.append(el("p", { class: f.feasible ? "pill" : "warn", id: "plFeasible" }, f.feasible ? `План допустим: ${m.count} объект(а), ${m.cost} из ${PS.budget} усл. ед.` : "План недопустим: " + f.reasons.map((r) => r.text).join("; ")));
    if (!res.source_candidates) b.append(el("p", { class: "warn" }, "В срезе нет исходных записей этой категории: «до» неизвестно, разница не вычисляется. Охват 0 в этом наборе записей не доказывает отсутствие услуги в городе."));
    const t = el("table", { id: "plMetrics", "aria-label": "Показатели ручного плана" });
    const hr = el("tr"); for (const h of ["Показатель", "До (только срез)", "После (ручной план)"]) hr.append(el("th", null, h));
    const th = el("thead"); th.append(hr); t.append(th);
    const tb = el("tbody");
    const rowM = (k, a, c) => { const tr = el("tr"); tr.append(el("td", null, k), el("td", { class: "num" }, a), el("td", { class: "num" }, c)); tb.append(tr); };
    rowM("Взвешенное среднее по прямой", mmText(bl.weighted_mean_mm), mmText(m.weighted_mean_mm));
    rowM("Худшая точка по прямой", mmText(bl.max_mm), mmText(m.max_mm));
    rowM(`Охват: вес точек ≤ ${PS.radius} м`, `${bl.covered_weight} из ${bl.total_weight}`, `${m.covered_weight} из ${m.total_weight}`);
    rowM("Точек без известного расстояния", String(bl.unknown_count), String(m.unknown_count));
    rowM("Стоимость, усл. ед.", "0", String(m.cost));
    t.append(tb); b.append(t);
    const secR = section(b, "plSecRows", `Таблица по точкам (${res.rows.length})`, res.rows.length <= 6);
    const pt = el("table", { id: "plRows", "aria-label": "Расстояние по прямой по контрольным точкам" });
    pt.append(el("caption", { class: "muted" }, "по прямой в пределах среза; метры из миллиметров haversine-mm-v1"));
    const h2 = el("tr"); for (const [h, c] of [["Точка (вес)", null], ["До", "num"], ["После", "num"], ["Разница", "num"]]) h2.append(el("th", { class: c }, h));
    const th2 = el("thead"); th2.append(h2); pt.append(th2);
    const tb2 = el("tbody"), byId = Object.fromEntries(D.cities[STATE.city].places.map((p) => [p.id, p]));
    for (const r of res.rows) {
      const tr = el("tr", { "data-plan-row": r.id });
      const na = r.nearest_after;
      const tdA = el("td", { class: "num" }, mmText(r.after_mm));
      if (na && na.kind === "hypothetical") tdA.append(el("div", { class: "muted" }, `кандидат ${na.id} (гипотеза)`));
      const tdP = el("td", null, `${r.id} (в${r.weight})`);
      let srcRow = null;
      if (r.nearest_before) {  // nearest source record before: name, QA marks, opens the record card
        const src = byId[r.nearest_before.id], qa = src ? qaOf(src) : [];
        const sb = el("button", { type: "button", class: "tool wi-src", "data-plan-source": r.nearest_before.id }, `${qa.length ? "⚠ " : ""}${src ? src.name || "Без названия" : r.nearest_before.id}`);
        sb.addEventListener("click", () => selectPlace(r.nearest_before.id));
        const td = el("td", { colspan: 4, class: "muted" }, `${r.id} — ближайшая запись среза: `);
        td.append(sb, document.createTextNode(qa.length ? " · QA: " + qa.map((q) => q.code).join(", ") : ""));
        srcRow = el("tr", { class: "wi-srcrow" }); srcRow.append(td);
      }
      const d = r.delta_mm;
      tr.append(tdP, el("td", { class: "num" }, mmText(r.before_mm)), tdA,
        el("td", { class: "num" + (d > 0 ? " better" : "") }, d === null ? "не вычисляется" : d >= 500 ? `ближе на ${fmtM(d / 1000)}` : d > 0 ? "ближе менее чем на 1 м" : "без изменений"));
      tb2.append(tr);
      if (srcRow) tb2.append(srcRow);
    }
    pt.append(tb2); secR.append(pt);
  }

  // ---------- stage 2: exact search in chunks (no Worker: file:// pages cannot start one), cancel, stale guard, apply ----------
  const OS = { status: "idle", request_id: 0, digest: null, examined: 0, total: 0, result: null, sens: null, msg: "", backup: null };
  const OBJ = [["mean", "Среднее"], ["minimax", "Худшая точка"], ["coverage", "Охват"]];
  const CHUNK = 2048;
  function currentProblemDigest() { try { return PL.problemDigest(scenario(), F); } catch (e) { return null; } }
  OPT.onProblemChange.push(() => {
    const d = currentProblemDigest();
    if (OS.status === "running" && d !== OS.digest) { OS.status = "stale"; OS.msg = "Параметры задачи изменились — поиск остановлен, его ответ не будет применён."; }
    else if (OS.status === "done" && d !== OS.digest) { OS.status = "stale"; OS.result = null; OS.sens = null; OS.msg = "Задача изменилась — прежние оптимумы устарели. Запустите поиск снова."; }
  });
  function startSearch() {
    let sc;
    try { sc = PL.validatePlanScenario(rawScenario(), ctxOf(STATE.city)); } catch (e) { OS.msg = "Поиск не запущен: " + (e.detail || e.message); render(); return; }
    const ctx = ctxOf(STATE.city), rid = ++OS.request_id, digest = PL.problemDigest(sc, F);
    const budgets = [...new Set([0, Math.floor(sc.budget / 2), sc.budget])].sort((a, b) => a - b);
    const jobs = [{ kind: "main", s: PL.createSearch(ctx, sc, { F, request_id: rid }) },
      ...budgets.map((b) => ({ kind: "sens", budget: b, s: PL.createSearch(ctx, { ...sc, budget: b }, { F, request_id: rid }) }))];
    Object.assign(OS, { status: "running", digest, examined: 0, total: jobs.reduce((t, j) => t + j.s.total, 0), result: null, sens: [], msg: "", jobs });
    render();
    let k = 0;
    const tick = () => {
      if (OS.request_id !== rid || OS.status !== "running") { for (const j of jobs) j.s.cancel(); return; }  // cancelled or superseded
      const j = jobs[k];
      if (j.s.step(CHUNK)) {
        const r = j.s.result();
        if (j.kind === "main") OS.mainResult = r; else OS.sens.push({ budget: j.budget, ...r });
        k++;
      }
      OS.examined = jobs.reduce((t, x) => t + x.s.examined, 0);
      const pr = $("plProgress"); if (pr) { pr.value = OS.examined; pr.max = Math.max(1, OS.total); }
      const pt = $("plProgressText"); if (pt) pt.textContent = `просмотрено ${OS.examined} из ${OS.total} наборов`;
      if (k < jobs.length) { setTimeout(tick, 0); return; }
      // accept only the answer to the current request and the current problem
      if (OS.request_id !== rid || currentProblemDigest() !== digest || OS.mainResult.problem_digest !== digest) { OS.status = "stale"; OS.msg = "Ответ поиска устарел и отброшен."; render(); return; }
      OS.result = OS.mainResult; OS.status = "done";
      OS.msg = OS.result.status === "infeasible" ? "Нет допустимых планов: " + OS.result.reasons.map((r) => r.text).join("; ") : `Готово: просмотрены все ${OS.result.evaluated} наборов, допустимых ${OS.result.feasible_count}.`;
      render();
    };
    setTimeout(tick, 0);
  }
  function cancelSearch() {
    if (OS.status !== "running") return;
    for (const j of OS.jobs || []) j.s.cancel();
    OS.status = "cancelled"; OS.request_id++; OS.result = null; OS.sens = null;
    OS.msg = "Поиск отменён; ручной план не изменён, неполный результат не показывается.";
    render();
  }
  function applyPlan(name) {
    if (OS.status !== "done" || !OS.result || !OS.result.objectives || OS.result.problem_digest !== currentProblemDigest()) { OS.msg = "Нечего применять: результат отсутствует или устарел."; render(); return false; }
    if (!OS.backup) OS.backup = PS.selected.slice();
    PS.selected = OS.result.objectives[name].ids.slice();
    const label = OBJ.find((o) => o[0] === name)[1];
    changed(`План «${label}» применён как ручной (только условное предложение по введённым местам). «Вернуть ручной план» отменит это.`);
    return true;
  }
  function restoreManual() { if (!OS.backup) return; PS.selected = OS.backup; OS.backup = null; changed("Ручной план восстановлен."); }
  const meanText = (wsum, total, unknown) => (unknown ? "нет данных" : mmText(wsum / total));
  OPT.render.push((b) => {
    b.append(el("h3", null, "Точный поиск по введённым кандидатам"));
    b.append(el("p", { class: "muted" }, "Полный перебор всех наборов кандидатов (до 2^16 = 65 536) с бюджетом, максимумом и ограничениями. Оптимум — только среди введённых мест и условий, не лучший план города и не рекомендация строить."));
    const row = el("div", { class: "wi-ctl" });
    const run = btn("plRun", "Найти точные оптимумы", startSearch); run.disabled = !PS.points.length || OS.status === "running";
    const cancel = btn("plCancel", "Отменить поиск", cancelSearch); cancel.disabled = OS.status !== "running";
    row.append(run, cancel);
    if (OS.backup) row.append(btn("plRestore", "Вернуть ручной план", restoreManual));
    b.append(row);
    if (OS.status === "running") {
      const pr = el("progress", { id: "plProgress", max: Math.max(1, OS.total), "aria-label": "Ход поиска" }); pr.value = OS.examined;
      b.append(pr, el("span", { id: "plProgressText", class: "muted" }, ` просмотрено ${OS.examined} из ${OS.total} наборов`));
    }
    b.append(el("p", { class: "wi-msg warn", id: "plOptMsg", role: "status", "aria-live": "polite" }, OS.msg));
    const r = OS.status === "done" ? OS.result : null;
    if (!r || r.status !== "optimal") return;
    // comparison: manual plan vs three objectives; identical plans are named as such
    let man = null; try { man = evaluate(); } catch (e) { man = null; }
    const ids = (a) => (a.length ? a.join(", ") : "без новых объектов");
    const t = el("table", { id: "plCompare", "aria-label": "Сравнение ручного плана и трёх оптимумов" });
    const hr = el("tr"); hr.append(el("th", null, "Показатель"), el("th", null, "Текущий (ручной)"));
    for (const [k, label] of OBJ) hr.append(el("th", { "data-obj": k }, label));
    const th = el("thead"); th.append(hr); t.append(th);
    const tb = el("tbody");
    const cols = OBJ.map(([k]) => r.objectives[k]);
    const sameAs = cols.map((c, i) => { const j = cols.findIndex((d) => d.ids.join() === c.ids.join()); return j < i ? OBJ[j][1] : null; });
    const row2 = (name, manual, vals) => { const tr = el("tr"); tr.append(el("td", null, name), el("td", null, manual)); vals.forEach((v) => tr.append(el("td", null, v))); tb.append(tr); };
    const mm = man && man.metrics;
    row2("Объекты", man ? ids(man.selected_ids) + (man.feasibility.feasible ? "" : " (недопустим)") : "—", cols.map((c, i) => ids(c.ids) + (sameAs[i] ? ` (тот же, что «${sameAs[i]}»)` : "")));
    row2("Стоимость, усл. ед.", mm ? String(mm.cost) : "—", cols.map((c) => String(c.cost)));
    row2("Взвешенное среднее", mm ? mmText(mm.weighted_mean_mm) : "—", cols.map((c) => meanText(c.weighted_sum_mm, mm ? mm.total_weight : 1, c.unknown_count)));
    row2("Худшая точка", mm ? mmText(mm.max_mm) : "—", cols.map((c) => mmText(c.max_mm)));
    row2(`Охват (вес ≤ ${PS.radius} м)`, mm ? `${mm.covered_weight} из ${mm.total_weight}` : "—", cols.map((c) => `${c.covered_weight} из ${mm ? mm.total_weight : "?"}`));
    row2("Точек без расстояния", mm ? String(mm.unknown_count) : "—", cols.map((c) => String(c.unknown_count)));
    const ar = el("tr"); ar.append(el("td", null, ""), el("td", null, ""));
    for (const [k, label] of OBJ) { const td = el("td"); td.append(btn(`plApply_${k}`, "Применить", () => applyPlan(k), { "aria-label": `Применить план «${label}»` })); ar.append(td); }
    tb.append(ar); t.append(tb);
    const wrap = el("div", { class: "tablewrap" }); wrap.append(t); b.append(wrap);
    b.append(el("p", { class: "muted" }, `Просмотрено ${r.evaluated} наборов, допустимых ${r.feasible_count}. Найденный план не применяется сам — только кнопкой «Применить». Отпечаток задачи ${r.problem_digest.slice(7, 23)}.`));
    for (const f of OPT.renderResult) f(b, r, man);
  });
  OPT.renderResult = [];

  // ---------- registration ----------
  EXT.layers.push(layer);
  EXT.tools.push({ placing: () => STATE.tool === "v2" && !!PS.mode, place,
    stop: () => { if (PS.mode) { PS.mode = null; PS.moveId = null; $("map").classList.remove("planmode"); render(); } },
    statusText: () => PS.mode === "points" ? `План v2: режим «контрольные точки» — нажмите на карту (Enter — центр). ${PS.points.length}/${PL.LIMITS.points}. Escape — выйти.`
      : PS.mode === "cands" ? `План v2: режим «кандидаты» — нажмите на карту (Enter — центр). ${PS.cands.length}/${PL.LIMITS.candidates}. Escape — выйти.`
        : `План v2: щёлкните на карте новое место для ${PS.moveId}. Escape — отмена.` });
  EXT.onCity.push((key, changedCity) => {
    if (!changedCity) return;
    const had = PS.points.length || PS.cands.length;
    reset(had ? "Город изменён — сценарий v2 сброшен: точки и кандидаты между городами не переносятся, старые результаты поиска не применяются." : "");
    onProblemChange();
  });
  EXT.onTool.push(() => render());
  EXT.cards.push(() => render());
  window.CITY_PLAN_UI = { state: PS, place, setMode, setCategory, setStatus, toggleSelected, removePoint, removeCand, demoSet, scenario, evaluate, render,
    rawScenario, setNumber, OPT, changed, reset, ctxOf, el, btn, mmText, opt: OS, startSearch, cancelSearch, applyPlan, restoreManual };
  render();
})();
