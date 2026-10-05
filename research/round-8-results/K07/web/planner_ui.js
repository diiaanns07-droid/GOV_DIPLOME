/* K07 round 8 — «План нескольких объектов» (city-plan-v2) UI module for the BUILD viewer.
 * Editor: control points with weights (1..25), candidate sites with conditional costs (0..16), required / excluded,
 * budget / max_selected / radius, a manual plan with feasibility and a before/after table.
 * All numbers come from a calculator adapter with the CORE_SPEC API (default window.CITY_PLAN_CALC = web/plan_calc.js;
 * another engine via CITY_PLAN_UI.setCalculator). The plan lives only in this module and its map layer: it never
 * enters the records, counters, QA, the facts catalog, the objects table or the what-if v1 scenario.
 * Strings are inserted with textContent only. Hooks used by app.js: init, drawLayer, placing, onMapClick, onMapEnter,
 * onCitySwitch, onOtherMode, statusText.
 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const SVGNS = "http://www.w3.org/2000/svg";
  const D = window.CITY_EVIDENCE, F = window.CITY_FACTS;
  let CALC = window.CITY_PLAN_CALC, makeCtx = CALC && CALC.makeContext;
  const RUN = window.CITY_PLAN_RUNNER, DEMO = window.CITY_PLAN_DEMO;
  const CAT = { school: "Школа", outpatient_clinic: "Поликлиника" };
  const LIM = { points: 25, cands: 16, weight: [1, 100], cost: [1, 1000000], budget: [0, 1000000], max: [0, 5], radius: [100, 5000] };
  const DEF = { cost: 100, budget: 300, max: 3, radius: 500 };  // conditional starting values, shown as such
  const STATUS = { free: "можно выбрать", required: "обязательно", excluded: "исключено" };
  let APP = null;
  const S = { open: false, tool: "control", category: "school", city: null, points: [], cands: [], selected: new Set(),
    budget: DEF.budget, max: DEF.max, radius: DEF.radius, nextP: 1, nextC: 1, pending: null, msg: "", synthetic: false,
    run: null, progress: null, result: null, undo: null, runOpts: {} };
  const ctxCache = {};

  // ---------- small DOM helpers ----------
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
  const btn = (fk, text, fn, attrs) => { const b = el("button", { type: "button", class: "tool", "data-fk": fk, ...attrs }, text); b.addEventListener("click", fn); return b; };
  const nf = new Intl.NumberFormat("ru-RU"), nf2 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });
  const fmtM = (mm) => (mm === null || mm === undefined ? "—" : mm >= 1e6 ? nf2.format(mm / 1e6) + " км" : nf.format(Math.round(mm / 1000)) + " м");
  const fmtCoord = (o) => `${o.lat.toFixed(5)}, ${o.lon.toFixed(5)}`;
  const pLabel = (id) => "Точка " + id.replace(/^cp-/, "");
  const cLabel = (id) => "Место " + id.replace(/^site-/, "");
  const pShort = (id) => "Т" + id.replace(/^cp-/, ""), cShort = (id) => "М" + id.replace(/^site-/, "");  // as on the map
  const units = (v) => `${nf.format(v)} усл. ед.`;
  const end = (t) => t.replace(/ед\.\./g, "ед.");  // "… усл. ед." before a full stop keeps one dot

  // ---------- scenario / calculator ----------
  function ctx() { return ctxCache[S.city] || (ctxCache[S.city] = makeCtx(D, S.city, F)); }
  function scenario(selected) {
    return { schema_version: "city-plan-v2", city_id: S.city, source_snapshot: ctx().source_snapshot, category: S.category,
      control_points: S.points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, weight: p.weight })),
      candidates: S.cands.map((c) => ({ id: c.id, lon: c.lon, lat: c.lat, category: S.category, kind: "hypothetical", cost: c.cost })),
      budget: S.budget, max_selected: S.max, coverage_radius_m: S.radius,
      required_ids: S.cands.filter((c) => c.status === "required").map((c) => c.id),
      excluded_ids: S.cands.filter((c) => c.status === "excluded").map((c) => c.id),
      selected_ids: selected || S.cands.filter((c) => S.selected.has(c.id)).map((c) => c.id) };
  }
  function validated() { return CALC.validatePlanScenario(scenario(), ctx(), { allowEmptyPoints: true }); }
  const bbox = () => D.cities[S.city].bbox;
  const inBbox = (lon, lat) => { const b = bbox(); return b[0] <= lon && lon <= b[2] && b[1] <= lat && lat <= b[3]; };
  function say(t) { S.msg = end(t); }

  // ---------- state changes ----------
  function problemChanged(why) {  // a running search is cancelled; an old result becomes stale (checked by digest)
    if (S.run && !S.run.finished) { S.run.cancel(); S.run = null; S.progress = null; say(`Поиск остановлен: ${why}. Запустите заново.`); }
  }
  function reset(reason) {
    if (S.run && !S.run.finished) S.run.cancel();
    Object.assign(S, { points: [], cands: [], selected: new Set(), nextP: 1, nextC: 1, pending: null, synthetic: false,
      run: null, progress: null, result: null, undo: null, budget: DEF.budget, max: DEF.max, radius: DEF.radius });
    say(reason || "");
  }
  function place(lon, lat) {
    if (!inBbox(lon, lat)) { say("Место вне квадрата среза: там нет исходных записей, точку или кандидатное место туда поставить нельзя."); return false; }
    if (S.pending) {
      const it = (S.pending.type === "point" ? S.points : S.cands).find((x) => x.id === S.pending.id);
      S.pending = null;
      if (it) { it.lon = lon; it.lat = lat; problemChanged("место перенесено"); say(`${it.id.startsWith("cp-") ? pLabel(it.id) : cLabel(it.id)} перенесено: ${fmtCoord(it)}.`); }
      return true;
    }
    if (S.tool === "control") {
      if (S.points.length >= LIM.points) { say(`Не больше ${LIM.points} контрольных точек — удалите одну из списка.`); return false; }
      const p = { id: `cp-${S.nextP++}`, lon, lat, weight: 1 };
      S.points.push(p); problemChanged("добавлена точка");
      say(`${pLabel(p.id)} поставлена (вес 1): ${fmtCoord(p)}. Точек ${S.points.length} из ${LIM.points}.`);
      return true;
    }
    if (S.tool === "candidate") {
      if (S.cands.length >= LIM.cands) { say(`Не больше ${LIM.cands} кандидатных мест — точный перебор ограничен 65 536 наборами.`); return false; }
      const c = { id: `site-${S.nextC++}`, lon, lat, cost: DEF.cost, status: "free" };
      S.cands.push(c); problemChanged("добавлено место");
      say(`${cLabel(c.id)} поставлено: стоимость ${units(DEF.cost)} — условное значение, задайте свою. Мест ${S.cands.length} из ${LIM.cands}.`);
      return true;
    }
    return false;
  }
  function removePoint(id) { S.points = S.points.filter((p) => p.id !== id); if (S.pending && S.pending.id === id) S.pending = null; problemChanged("удалена точка"); say(`${pLabel(id)} удалена.`); }
  function removeCand(id) { S.cands = S.cands.filter((c) => c.id !== id); S.selected.delete(id); if (S.pending && S.pending.id === id) S.pending = null; problemChanged("удалено место"); say(`${cLabel(id)} удалено из кандидатов и из ручного плана.`); }
  function startMove(type, id) { S.pending = { type, id }; say(`Перенос: ${type === "point" ? pLabel(id) : cLabel(id)}. Нажмите на карту в квадрате (или Enter — в центр карты). Escape — отмена.`); }
  function cancelMove() { if (!S.pending) return false; S.pending = null; say("Перенос отменён."); return true; }
  function intIn(raw, [lo, hi]) { const v = Number(raw); return raw !== "" && Number.isInteger(v) && v >= lo && v <= hi ? v : null; }
  function setNum(what, raw, apply, lim, text) {
    const v = intIn(String(raw).trim(), lim);
    if (v === null) { say(`${text}: нужно целое число ${nf.format(lim[0])}…${nf.format(lim[1])}. Значение не изменено.`); return false; }
    apply(v); problemChanged(`изменено: ${text.toLowerCase()}`); return true;
  }
  function setStatus(id, st) {
    const c = S.cands.find((x) => x.id === id); if (!c || !STATUS[st]) return;
    c.status = st;
    if (st === "required") { S.selected.add(id); say(`${cLabel(id)} обязательно: включено в ручной план и в каждый найденный план.`); }
    else if (st === "excluded") { S.selected.delete(id); say(`${cLabel(id)} исключено: убрано из ручного плана и не войдёт в найденные планы.`); }
    else say(`${cLabel(id)}: ${STATUS.free}.`);
    problemChanged("изменены ограничения");
  }
  function toggleSelected(id, on) {
    const c = S.cands.find((x) => x.id === id); if (!c || c.status !== "free") return;
    if (on) S.selected.add(id); else S.selected.delete(id);
    S.undo = null; say(`${cLabel(id)} ${on ? "добавлено в ручной план" : "убрано из ручного плана"}.`);
  }
  function loadDemo() {
    const d = DEMO.syntheticDemo(bbox(), S.category);
    reset("");
    S.points = d.control_points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat, weight: p.weight }));
    S.cands = d.candidates.map((c) => ({ id: c.id, lon: c.lon, lat: c.lat, cost: c.cost, status: "free" }));
    Object.assign(S, { budget: d.budget, max: d.max_selected, radius: d.coverage_radius_m, nextP: S.points.length + 1, nextC: S.cands.length + 1, synthetic: true });
    say(`Загружен демо-набор SYNTHETIC: ${S.points.length} точек, ${S.cands.length} мест, бюджет ${units(S.budget)}. Это не данные города.`);
  }
  function setOpen(on) {
    S.open = !!on;
    if (S.open) { if (!S.city) S.city = APP.state.city; exclusive(); }
    else { S.pending = null; say(S.points.length || S.cands.length ? "План скрыт; точки и места сохраняются до смены города или категории." : ""); }
  }
  function setTool(t) { S.tool = t; S.pending = null; if (placing()) exclusive(); say(t === "none" ? "Постановка выключена: клики по карте выбирают записи, как обычно." : `Клик или Enter на карте ставит: ${t === "control" ? "контрольную точку" : "кандидатное место"}.`); }
  function exclusive() {  // one map tool at a time: the base point mode and what-if v1 placement are switched off
    if (!placing() || !APP) return;
    if (APP.state.pointMode && APP.setPointMode) APP.setPointMode(false);
    if (APP.state.wi && APP.state.wi.mode && APP.setWiMode) APP.setWiMode(null, true);
  }
  const placing = () => S.open && S.tool !== "none";

  // ---------- rendering ----------
  let focusAfter = null;
  function render() {
    const card = $("planCard"); if (!card || !APP) return;
    const fa = document.activeElement, fk = fa && fa.dataset ? fa.dataset.fk : null;
    card.hidden = !S.open;
    $("planBtn").setAttribute("aria-pressed", String(S.open));
    $("map").classList.toggle("planmode", placing());
    const m = $("map"); if (placing()) m.setAttribute("aria-describedby", "plMapHelp"); else if (m.getAttribute("aria-describedby") === "plMapHelp") m.removeAttribute("aria-describedby");
    const body = $("planBody"); body.replaceChildren();
    if (S.open) {
      renderEditor(body);
      const res = el("div", { id: "plResults" }); body.append(res); fillResults(res);
    }
    APP.renderMap(); APP.updateStatus();
    const want = focusAfter || fk; focusAfter = null;
    if (want && S.open) { const n = body.querySelector(`[data-fk="${want}"]`) || $(want); if (n && document.activeElement !== n) n.focus(); }
  }
  // Results only (manual plan, search, map): value edits keep the editor DOM, so Tab after typing is not disturbed.
  function fillResults(res) { res.replaceChildren(); renderManual(res); if (PLAN_UI.renderSearch) PLAN_UI.renderSearch(res); }
  function renderResults() {
    if (!S.open) return;
    const m = $("plMsg"); if (m) m.textContent = S.msg;
    const res = $("plResults"); if (res) fillResults(res);
    APP.renderMap(); APP.updateStatus();
  }
  function numInput(fk, value, lim, label, onChange, cls) {
    const i = el("input", { type: "number", min: lim[0], max: lim[1], step: 1, inputmode: "numeric", value, "data-fk": fk, "aria-label": label, class: cls || "pl-num" });
    let last = String(value);
    i.addEventListener("change", () => { if (onChange(i.value)) last = i.value.trim(); else i.value = last; renderResults(); });
    return i;
  }
  function renderEditor(body) {
    if (S.synthetic) body.append(el("p", { class: "pl-synth", id: "plSynth" }, DEMO.LABEL + "."));
    const r1 = el("div", { class: "pl-row" });
    const sel = el("select", { id: "plCat", "data-fk": "plCat" });
    for (const [k, v] of Object.entries(CAT)) { const o = el("option", { value: k }, v); if (k === S.category) o.selected = true; sel.append(o); }
    sel.addEventListener("change", () => { const had = S.points.length || S.cands.length; S.category = sel.value; reset(had ? `Категория изменена на «${CAT[sel.value]}» — план сброшен: места относятся к одной категории.` : ""); render(); });
    r1.append(el("label", { for: "plCat" }, "Категория "), sel,
      btn("plDemo", "Демо-набор (SYNTHETIC)", () => { loadDemo(); render(); }),
      btn("plReset", "Сбросить план", () => { reset("План сброшен."); focusAfter = "plCat"; render(); }, { disabled: !S.points.length && !S.cands.length }));
    body.append(r1);
    const fs = el("fieldset", { class: "pl-tools" });
    fs.append(el("legend", null, "Что ставить кликом или Enter на карте"));
    for (const [v, t] of [["control", `Контрольная точка (${S.points.length} из ${LIM.points})`], ["candidate", `Кандидатное место (${S.cands.length} из ${LIM.cands})`], ["none", "Ничего (просмотр карты)"]]) {
      const lab = el("label", { class: "chk" }), r = el("input", { type: "radio", name: "plTool", value: v, "data-fk": "plTool-" + v });
      r.checked = S.tool === v; r.addEventListener("change", () => { setTool(v); render(); });
      lab.append(r, el("span", null, t)); fs.append(lab);
    }
    body.append(fs, el("p", { class: "pl-msg", id: "plMsg", role: "status", "aria-live": "polite" }, S.msg));
    if (S.pending) body.append(btn("plCancelMove", "Отменить перенос", () => { const was = S.pending; cancelMove(); focusAfter = (was.type === "point" ? "mvp-" : "mvc-") + was.id; render(); }));
    // parameters
    const pr = el("div", { class: "pl-params" });
    const prm = (id, text, hint, value, lim, apply) => {
      const w = el("label", { class: "pl-param", for: id }); w.append(el("span", null, text));
      const i = numInput(id, value, lim, text, (raw) => setNum(id, raw, apply, lim, text)); i.id = id;
      w.append(i, el("small", { class: "muted" }, hint)); pr.append(w);
    };
    prm("plBudget", "Бюджет", "условные единицы, не тенге и не смета", S.budget, LIM.budget, (v) => { S.budget = v; });
    prm("plMax", "Максимум объектов", "сколько мест можно выбрать (0–5)", S.max, LIM.max, (v) => { S.max = v; });
    prm("plRadius", "Радиус охвата, м", "параметр анализа по прямой, не норматив пешей доступности", S.radius, LIM.radius, (v) => { S.radius = v; });
    body.append(el("h3", { id: "plParamTitle" }, "Условия"), pr);
    // control points
    body.append(el("h3", { id: "plPtsTitle", tabindex: "-1", "data-fk": "plPtsTitle" }, `Контрольные точки (${S.points.length})`));
    body.append(el("p", { class: "muted" }, "Вес — приоритет точки, заданный пользователем (1–100), не число жителей."));
    const ol = el("ol", { class: "pl-list", id: "plPts", "aria-labelledby": "plPtsTitle" });
    if (!S.points.length) ol.append(el("li", { class: "muted" }, "Точек нет. Выберите «Контрольная точка» и нажмите на карту (1–25 точек)."));
    S.points.forEach((p, i) => {
      const li = el("li", { "data-pl-point": p.id, class: S.pending && S.pending.id === p.id ? "pl-pending" : null });
      li.append(el("span", { class: "pl-label", title: `${pLabel(p.id)} · ${fmtCoord(p)}` }, pShort(p.id)),
        el("span", { class: "pl-inline" }, "вес"), numInput("w-" + p.id, p.weight, LIM.weight, `Вес: ${pLabel(p.id)}`, (raw) => setNum("w", raw, (v) => { p.weight = v; }, LIM.weight, `Вес ${pLabel(p.id)}`), "pl-num pl-w"),
        btn("mvp-" + p.id, "Перенести", () => { startMove("point", p.id); focusAfter = "map"; render(); }, { "aria-label": `Перенести: ${pLabel(p.id)}` }),
        btn("dlp-" + p.id, "Удалить", () => { removePoint(p.id); const nx = S.points[i] || S.points[i - 1]; focusAfter = nx ? "dlp-" + nx.id : "plPtsTitle"; render(); }, { "aria-label": `Удалить: ${pLabel(p.id)}` }));
      ol.append(li);
    });
    body.append(ol);
    // candidates
    body.append(el("h3", { id: "plCandTitle", tabindex: "-1", "data-fk": "plCandTitle" }, `Кандидатные места (${S.cands.length}) `, null));
    body.lastChild.append(el("span", { class: "pill" }, "гипотеза"));
    body.append(el("p", { class: "muted" }, "Места и стоимости задаёт пользователь: это не существующие учреждения, не адреса и не цены в тенге."));
    const cl = el("ol", { class: "pl-list", id: "plCands", "aria-labelledby": "plCandTitle" });
    if (!S.cands.length) cl.append(el("li", { class: "muted" }, "Мест нет. Выберите «Кандидатное место» и нажмите на карту (0–16 мест)."));
    S.cands.forEach((c, i) => {
      const li = el("li", { "data-pl-cand": c.id, class: S.pending && S.pending.id === c.id ? "pl-pending" : null });
      const st = el("select", { "data-fk": "st-" + c.id, "aria-label": `Ограничение: ${cLabel(c.id)}` });
      for (const [k, v] of Object.entries(STATUS)) { const o = el("option", { value: k }, v); if (k === c.status) o.selected = true; st.append(o); }
      st.addEventListener("change", () => { setStatus(c.id, st.value); render(); });
      const cb = el("input", { type: "checkbox", "data-fk": "sel-" + c.id, "aria-label": `В ручном плане: ${cLabel(c.id)}`, disabled: c.status !== "free" });
      cb.checked = S.selected.has(c.id);
      cb.addEventListener("change", () => { toggleSelected(c.id, cb.checked); render(); });
      const inPlan = el("label", { class: "chk" }); inPlan.append(cb, el("span", null, "в плане"));
      li.append(el("span", { class: "pl-label", title: `${cLabel(c.id)} · ${fmtCoord(c)}` }, cShort(c.id)),
        numInput("c-" + c.id, c.cost, LIM.cost, `Стоимость, условные единицы: ${cLabel(c.id)}`, (raw) => setNum("c", raw, (v) => { c.cost = v; }, LIM.cost, `Стоимость ${cLabel(c.id)}`), "pl-num pl-c"),
        el("span", { class: "pl-inline" }, "усл. ед."), inPlan, el("span", { class: "pl-break", "aria-hidden": "true" }), st,
        btn("mvc-" + c.id, "Перенести", () => { startMove("cand", c.id); focusAfter = "map"; render(); }, { "aria-label": `Перенести: ${cLabel(c.id)}` }),
        btn("dlc-" + c.id, "Удалить", () => { removeCand(c.id); const nx = S.cands[i] || S.cands[i - 1]; focusAfter = nx ? "dlc-" + nx.id : "plCandTitle"; render(); }, { "aria-label": `Удалить: ${cLabel(c.id)}` }));
      cl.append(li);
    });
    body.append(cl);
  }
  function placeById(id) { return D.cities[S.city].places.find((p) => p.id === id); }
  function nearestText(n) {
    if (!n) return "—";
    if (n.kind === "hypothetical") return `${cShort(n.id)} — ${cLabel(n.id)} (гипотеза)`;
    const p = placeById(n.id), qa = p && F && F.qaOf ? F.qaOf(S.city, p) : [];
    const src = p && p.sources && p.sources.length ? p.sources.map((s) => s.dataset).join("/") : "источник не указан";
    return `${p ? p.name || "Без названия" : n.id} · запись среза (${src})${qa.length ? " · ⚠ " + qa.map((q) => q.code).join(", ") : ""}`;
  }
  function metricRows(m) {
    return [
      ["Средневзвешенное расстояние", m.weighted_mean_mm === null ? `не определено: ${m.unknown_count} точ. без объектов` : fmtM(m.weighted_mean_mm)],
      ["Худшая точка", m.max_mm === null ? "не определено" : fmtM(m.max_mm)],
      ["Охват (вес точек в радиусе)", `${nf.format(m.covered_weight)} из ${nf.format(m.total_weight)} (${nf.format(Math.round(m.coverage_fraction * 100))} %)`],
      ["Стоимость", units(m.cost)],
    ];
  }
  function renderManual(body) {
    body.append(el("h3", { id: "plManTitle" }, "Ручной план"));
    const box = el("div", { id: "plManual" }); body.append(box);
    S.lastEval = null;
    if (!S.points.length) { box.append(el("p", { class: "muted" }, "Расчёт появится после первой контрольной точки.")); return; }
    const v = validated();
    if (!v.ok) { box.append(el("p", { class: "err", role: "alert" }, `Сценарий не прошёл проверку (${v.error.code}, ${v.error.path}): ${v.error.detail}`)); return; }
    let ev, ev0;
    try { ev = CALC.evaluatePlan(ctx(), v.scenario); ev0 = CALC.evaluatePlan(ctx(), v.scenario, []); }
    catch (e) { box.append(el("p", { class: "err", role: "alert" }, "Расчёт не выполнен: " + (e.detail || e.message))); return; }
    S.lastEval = ev;
    const ids = ev.selected_ids;
    box.append(el("p", { id: "plManSel" }, end(ids.length ? `Выбрано: ${ids.map(cLabel).join(", ")} — ${ids.length} из максимум ${S.max}; ${units(ev.metrics.cost)} из бюджета ${units(S.budget)}.` : `Ничего не выбрано: показан исходный срез. Бюджет ${units(S.budget)}.`)));
    const REASON = { over_budget: "стоимость больше бюджета", too_many: "мест больше, чем «Максимум объектов»", missing_required: "нет обязательного места", has_excluded: "есть исключённое место" };
    box.append(el("p", { id: "plFeas", class: ev.feasibility.feasible ? "pl-ok" : "pl-bad" }, ev.feasibility.feasible ? "✓ План допустим по бюджету, числу мест и ограничениям."
      : "✗ План недопустим: " + ev.feasibility.reasons.map((r) => `${REASON[r.code] || r.code} (${r.detail})`).join("; ") + ". Расчёт показан, но такой план нарушает условия."));
    if (!ev.baseline_records) box.append(el("p", { class: "warn", id: "plNoBase" }, `В срезе нет записей категории «${CAT[S.category]}»: «не определено» означает отсутствие записей в этом наборе данных, а не отсутствие услуги в городе.`));
    const mt = el("table", { class: "pl-metrics", id: "plMetrics", "aria-label": "Показатели ручного плана и исходного среза" });
    const hr = el("tr"); for (const h of ["Показатель", "Исходный срез", "Ручной план"]) hr.append(el("th", null, h));
    const th = el("thead"); th.append(hr); mt.append(th);
    const tb = el("tbody"), a = metricRows(ev0.metrics), b = metricRows(ev.metrics);
    a.forEach((r, i) => { const tr = el("tr"); tr.append(el("td", null, r[0]), el("td", null, r[1]), el("td", null, b[i][1])); tb.append(tr); });
    mt.append(tb); box.append(mt);
    const t = el("table", { class: "pl-table", id: "plTable", "aria-label": "Расстояние по прямой до ближайшей записи среза или выбранного места: до и после" });
    const h2 = el("tr"); ["Т (вес)", "До", "После", "Разница"].forEach((h, i) => h2.append(el("th", { class: i ? "num" : null }, h)));
    const t2 = el("thead"); t2.append(h2); t.append(t2);
    const b2 = el("tbody");
    for (const r of ev.rows) {
      const tr = el("tr", { "data-pl-row": r.control_point_id });
      const delta = r.delta_mm === null ? "—" : r.delta_mm > 0 ? "−" + fmtM(r.delta_mm) : "0";
      [`${pShort(r.control_point_id)} (×${nf.format(r.weight)})`, fmtM(r.before_mm), fmtM(r.after_mm), delta].forEach((x, i) => tr.append(el("td", { class: i ? "num" : null }, x)));
      const sub = el("tr", { class: "pl-sub", "data-pl-near": r.control_point_id });
      sub.append(el("td", { colspan: 4 }, "ближайшее после: " + nearestText(r.nearest_after)));
      b2.append(tr, sub);
    }
    t.append(b2); box.append(t);
    box.append(el("p", { class: "muted" }, `По прямой, в мм с округлением ${ev.metric_version}; «Разница» — уменьшение расстояния до ближайшей записи или места, не время пешком и не улучшение услуги. Охват — доля веса выбранных точек, не жителей. Вместимость, население и трафик не учитываются.`));
  }

  // ---------- map layer (called by app.js renderMap) ----------
  function drawLayer(g, info) {
    if (!S.open || (!S.points.length && !S.cands.length && !placing())) return;
    const ev = S.lastEval && S.points.length ? S.lastEval : null;
    if (ev) for (const r of ev.rows) {  // thin lines: point → its nearest object in the manual plan
      const p = S.points.find((x) => x.id === r.control_point_id), n = r.nearest_after;
      const o = !n ? null : n.kind === "hypothetical" ? S.cands.find((c) => c.id === n.id) : placeById(n.id);
      if (!p || !o) continue;
      const [x1, y1] = info.toScreen(p.lon, p.lat), [x2, y2] = info.toScreen(o.lon, o.lat);
      g.append(sv("line", { x1, y1, x2, y2, stroke: "var(--muted)", "stroke-width": 1, "stroke-dasharray": "2 3", "aria-hidden": "true" }));
    }
    for (const c of S.cands) {
      const [x, y] = info.toScreen(c.lon, c.lat), on = S.selected.has(c.id);
      const m = sv("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`, "data-plan": c.id, "aria-hidden": "true" });
      m.append(sv("rect", { x: -8, y: -8, width: 16, height: 16, rx: 2, fill: on ? "var(--focus)" : "var(--surface)", stroke: c.status === "excluded" ? "var(--muted)" : "var(--ink)",
        "stroke-width": c.status === "required" ? 3 : 1.5, "stroke-dasharray": on ? null : "3 2" }));
      if (c.status === "excluded") m.append(sv("path", { d: "M-6 -6L6 6M6 -6L-6 6", stroke: "var(--muted)", "stroke-width": 1.5 }));
      const t = sv("text", { x: 11, y: 4, "font-size": 10, fill: "var(--ink)" }); t.textContent = "М" + c.id.replace(/^site-/, "");
      m.append(t); g.append(m);
    }
    for (const p of S.points) {
      const [x, y] = info.toScreen(p.lon, p.lat);
      const m = sv("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`, "data-plan": p.id, "aria-hidden": "true" });
      m.append(sv("circle", { r: 8, fill: "var(--surface)", stroke: "var(--ink)", "stroke-width": 2, "stroke-dasharray": S.pending && S.pending.id === p.id ? "3 2" : null }));
      const t = sv("text", { "text-anchor": "middle", y: 3.5, "font-size": 9, "font-weight": 700, fill: "var(--ink)" }); t.textContent = p.id.replace(/^cp-/, "");
      m.append(t); g.append(m);
    }
    if (placing()) {  // keyboard target; shown by CSS only while the map itself has focus (no re-render on focus/blur)
      const svg = $("map"), cx = svg.clientWidth / 2, cy = svg.clientHeight / 2, tg = sv("g", { class: "pl-target", "data-plan": "target", "aria-hidden": "true" });
      tg.append(sv("circle", { cx, cy, r: 11, fill: "none", stroke: "var(--focus)", "stroke-width": 2 }),
        sv("path", { d: `M${cx - 15} ${cy}H${cx - 6}M${cx + 6} ${cy}H${cx + 15}M${cx} ${cy - 15}V${cy - 6}M${cx} ${cy + 6}V${cy + 15}`, stroke: "var(--focus)", "stroke-width": 2 }));
      g.append(tg);
    }
  }

  // ---------- hooks for app.js ----------
  function onMapClick(lonlat, ev) {
    if (!placing()) return false;
    if (ev && ev.target && ev.target.closest && ev.target.closest("[data-plan]") && !S.pending) return true;  // own marker: nothing new
    place(lonlat[0], lonlat[1]); render(); return true;
  }
  function onMapEnter(lonlat) { if (!placing()) return false; place(lonlat[0], lonlat[1]); render(); return true; }
  function onCitySwitch(city) {
    if (S.city && city !== S.city) {
      const had = S.points.length || S.cands.length || S.result || S.run;
      reset(had ? "Город изменён — план сброшен: точки, места и найденные планы между городами не переносятся." : "");
    }
    S.city = city;
    if (S.open) render();
  }
  function onOtherMode() { if (placing()) { S.tool = "none"; S.pending = null; say("Постановка плана выключена: включён другой режим карты."); render(); } }
  function statusText() { return placing() ? (S.msg || "План: нажмите на карту, чтобы поставить выбранный элемент (Enter — в центр карты). Escape — выключить постановку.") : ""; }
  function setCalculator(engine, opts = {}) {
    for (const f of ["validatePlanScenario", "evaluatePlan", "optimizePlans"]) if (typeof engine[f] !== "function") throw new Error("calculator without " + f);
    CALC = engine; makeCtx = opts.makeContext || engine.makeContext || window.CITY_PLAN_CALC.makeContext;
    for (const k of Object.keys(ctxCache)) delete ctxCache[k];
    reset("Подключён другой расчётный модуль — план сброшен."); render();
  }
  function init(app) {
    APP = app; S.city = app.state.city;
    if (!CALC || !F || !F.sha256hex || !F.placesDigest || !D) { const b = $("planBtn"); if (b) b.hidden = true; return; }
    $("planBtn").addEventListener("click", () => { setOpen(!S.open); if (S.open) focusAfter = "plCat"; render(); });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !S.open) return;
      if (cancelMove()) { render(); return; }
      if (placing()) { setTool("none"); render(); }
    });
    render();
  }
  const PLAN_UI = { init, drawLayer, placing, onMapClick, onMapEnter, onCitySwitch, onOtherMode, statusText, setCalculator, render, renderResults,
    _state: S, _scenario: scenario, _ctx: ctx, _units: units, _fmtM: fmtM, _cLabel: cLabel, _pLabel: pLabel, _metricRows: metricRows,
    _btn: btn, _el: el, _problemChanged: problemChanged, _say: say, _RUN: RUN, _calc: () => CALC, _validated: validated };
  window.CITY_PLAN_UI = PLAN_UI;
})();
