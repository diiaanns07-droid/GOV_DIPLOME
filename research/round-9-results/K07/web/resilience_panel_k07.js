/* K07 round 9 — panel «Устойчивость к допущениям» for the BUILD plan card (plan-ui.js @ d865dd4).
 * Plugs into BUILD's own hooks (CITY_PLAN_UI.OPT.render / onProblemChange, CITY_APP.ui.EXT.onCity); plan-ui.js is not
 * rewritten. Engine: window.CITY_RESILIENCE (BUILD, if present) or window.CITY_RESILIENCE_K07 (K07 adapter on plan.js).
 * Source records are chosen in a keyboard list (≤ 16 per category, QA filter); there is no map mode, so no extra Tab stops.
 * «Условно исключаем из расчёта; это не подтверждение закрытия.» No probabilities, risk, population or walking time.
 * Strings from data and labels are inserted with textContent only.
 */
(function () {
  "use strict";
  const U = window.CITY_PLAN_UI, APP = window.CITY_APP, F = window.CITY_FACTS, D = window.CITY_EVIDENCE;
  const RE = window.CITY_RESILIENCE || window.CITY_RESILIENCE_K07;
  if (!U || !U.OPT || !APP || !APP.ui || !RE || !F) return;
  const { el, btn } = U, PS = U.state, $ = (id) => document.getElementById(id);
  const RS = { city: APP.state.city, category: PS.category, qa: "all", sel: new Set(), label: "", cases: [], seq: 1,
    run: null, progress: null, result: null, backup: null, msg: "", open: true, runOpts: { chunk: 256, delayMs: 0 } };
  const LIM = RE.LIMITS || { candidates: 12, cases: 7, label: 120 };
  const nf = new Intl.NumberFormat("ru-RU");
  const mText = (mm) => (mm === null || mm === undefined ? null : U.mmText(mm));
  const units = (v) => `${nf.format(v)} усл. ед.`;
  let focusAfter = null;

  // ---------- data ----------
  const records = () => {
    const places = D.cities[APP.state.city].places.filter((p) => p.group === PS.category);
    return places.map((p) => { const qa = APP.ui.qaOf(p); return { id: p.id, name: p.name || "Без названия", qa: qa.map((q) => q.code), src: [...new Set((p.sources || []).map((s) => s.dataset))].join("/") || "источник не указан" }; })
      .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : a.id < b.id ? -1 : 1));
  };
  const nameOf = (id) => { const p = D.cities[APP.state.city].places.find((x) => x.id === id); return p ? p.name || "Без названия" : id; };
  const envelope = () => ({ schema_version: "city-resilience-v1", plan: U.rawScenario(), cases: RS.cases.map((c) => ({ id: c.id, label: c.label, disabled_source_ids: c.ids.slice() })) });
  function validEnv() { try { return { env: RE.validateResilience(envelope(), U.ctxOf(APP.state.city)) }; } catch (e) { return { error: e }; } }
  function currentDigest() { const v = validEnv(); return v.env ? RE.resilienceProblemDigest(v.env, F) : null; }

  // ---------- state changes ----------
  function reset(msg) {
    if (RS.run) { const r = RS.run; RS.run = null; r.cancel(); }
    Object.assign(RS, { city: APP.state.city, category: PS.category, sel: new Set(), label: "", cases: [], seq: 1, progress: null, result: null, backup: null, msg: msg || "" });
  }
  function addCase() {
    const label = RS.label.trim();
    if (!RS.sel.size || !label) { RS.msg = "Нужны название случая и хотя бы одна выбранная запись."; return false; }
    if (RS.cases.length >= LIM.cases) { RS.msg = `Не больше ${LIM.cases} случаев (исходный срез добавляется сам).`; return false; }
    if ([...label].length > LIM.label) { RS.msg = `Название длиннее ${LIM.label} символов.`; return false; }
    let id; do { id = "C" + RS.seq++; } while (RS.cases.some((c) => c.id === id));
    const ids = [...RS.sel].sort();
    const same = RS.cases.find((c) => c.ids.join() === ids.join());
    RS.cases.push({ id, label, ids });
    RS.sel = new Set(); RS.label = "";
    RS.msg = `Случай ${id} «${label}» добавлен: условно исключено ${ids.length} записей.${same ? ` Набор совпадает со случаем ${same.id} — результат от повтора не меняется.` : ""}`;
    return true;
  }
  function removeCase(id) { RS.cases = RS.cases.filter((c) => c.id !== id); RS.msg = `Случай ${id} удалён.`; }
  function stopRun(msg) { if (RS.run) { const r = RS.run; RS.run = null; RS.progress = null; r.cancel(); RS.msg = msg; } }
  function startRun() {
    const v = validEnv();
    if (!v.env) { RS.msg = `Сравнение не запущено: ${v.error.code ? v.error.code + " — " : ""}${v.error.detail || v.error.message}`; return; }
    stopRun("");
    const s = RE.createResilienceSearch(U.ctxOf(APP.state.city), v.env, { F }), digest = RE.resilienceProblemDigest(v.env, F);
    const run = { s, digest, cancel: () => s.cancel() };
    RS.run = run; RS.result = null; RS.progress = { examined: 0, total: s.total };
    RS.msg = `Идёт точный перебор ${nf.format(s.total)} наборов по ${v.env.cases.length + 1} случаям…`;
    focusAfter = "rsCancel";
    const tick = () => {
      if (RS.run !== run) return;  // cancelled or superseded: the answer of an old request is never shown
      const done = s.step(RS.runOpts.chunk);
      RS.progress = { examined: s.examined, total: s.total };
      const pb = $("rsProgress"), pt = $("rsProgressText");
      if (pb) { pb.max = Math.max(1, s.total); pb.value = s.examined; }
      if (pt) pt.textContent = `просмотрено ${nf.format(s.examined)} из ${nf.format(s.total)} наборов`;
      if (!done) { setTimeout(tick, RS.runOpts.delayMs); return; }
      RS.run = null; RS.progress = null;
      const r = s.result();
      if (digest !== currentDigest()) { RS.msg = "Ответ устарел (условия изменены) и отброшен."; U.render(); return; }
      RS.result = r;
      RS.msg = r.status === "optimal" ? `Готово: просмотрено ${nf.format(r.evaluated)} наборов, допустимых ${nf.format(r.feasible_count)}. Ручной план меняется только кнопкой «Применить».`
        : `Нет допустимых планов: ${r.reasons.map((x) => x.text).join("; ")}.`;
      focusAfter = "rsResultTitle";
      U.render();
    };
    setTimeout(tick, RS.runOpts.delayMs);
  }
  function apply(kind) {
    const r = RS.result; if (!r || !r[kind] || r.resilience_problem_digest !== currentDigest()) { RS.msg = "Нечего применять: результат отсутствует или устарел."; return; }
    if (!RS.backup) RS.backup = PS.selected.slice();
    PS.selected = r[kind].selected_ids.slice();
    focusAfter = "rsRestore";
    U.changed(`План «${kind === "robust" ? "Устойчивый" : "Обычный"}» применён как ручной (условное предложение по введённым местам). «Вернуть ручной план» отменит это.`);
  }
  function restore() { if (!RS.backup) return; PS.selected = RS.backup; RS.backup = null; focusAfter = "rsApplyAnchor"; U.changed("Ручной план восстановлен."); }

  // ---------- hooks from BUILD ----------
  U.OPT.onProblemChange.push(() => {
    if (APP.state.city !== RS.city || PS.category !== RS.category) {  // category change (city is handled by onCity)
      const had = RS.cases.length || RS.result;
      reset(had ? "Категория изменена — случаи и результат сброшены: ID записей другой категории не переносятся." : "");
      return;
    }
    if (RS.run && RS.run.digest !== currentDigest()) stopRun("Условия изменены — сравнение остановлено, его ответ не будет показан. Запустите снова.");
  });
  APP.ui.EXT.onCity.push((key, changedCity) => {
    if (!changedCity) return;
    const had = RS.cases.length || RS.result || RS.run;
    reset(had ? "Город изменён — случаи устойчивости сброшены: ID записей между городами не переносятся." : "");
    RS.city = key;  // BUILD calls onCity before STATE.city changes: remember the new city, or the next render resets again
  });

  // ---------- rendering (inside the BUILD plan card) ----------
  const nullWhy = (m) => `нет данных: у ${m.unknown_count} точ. нет ни записи, ни выбранного места`;
  const metricLine = (m) => [m.weighted_mean_mm === null ? nullWhy(m) : `среднее ${mText(m.weighted_mean_mm)}`, m.max_mm === null ? null : `худшая ${mText(m.max_mm)}`,
    `охват ${nf.format(m.covered_weight)}/${nf.format(m.total_weight)}`].filter(Boolean).join(" · ");
  const caseLabel = (id) => (id === "base" ? "исходный срез" : `${id} «${(RS.cases.find((c) => c.id === id) || {}).label || id}»`);
  function wText(x) {
    const w = x.worst_vector, cs = x.worst_case_ids.map(caseLabel).join(", ");
    // unknown points first; a sum is shown only over points that have a distance (never «сумма 0 м» for unknown ones)
    const parts = w[0] ? [`${w[0]} точ. без расстояния (нет ни записи, ни выбранного места)`] : [];
    if (w[1] > 0) parts.push(`${w[0] ? "сумма по остальным" : "сумма"} ${mText(w[1])}`);
    if (w[2] !== null) parts.push(`худшая точка ${mText(w[2])}`);
    return `худший случай: ${cs} — ${parts.join(", ")}`;
  }
  U.OPT.render.push((b) => {
    if (APP.state.city !== RS.city || PS.category !== RS.category) reset("");
    const sec = el("details", { id: "rsSec", class: "pl-sec rs-sec" });
    sec.open = RS.open;
    const sm = el("summary", { id: "rsSec_sum" }, "Устойчивость к допущениям о данных");
    sm.addEventListener("click", () => { RS.open = !sec.open; });
    sec.append(sm);
    b.append(sec);
    sec.append(el("p", { class: "warn", id: "rsNote" }, "Условно исключаем из расчёта выбранные исходные записи; это не подтверждение закрытия, не прогноз и не оценка риска. Пустые исходные данные не означают отсутствие услуги в городе."));
    sec.append(el("p", { class: "muted" }, `Случаи сравниваются по худшему результату (вектор: точки без расстояния, сумма, худшая точка). До ${LIM.candidates} кандидатов и ${LIM.cases} случаев плюс исходный срез; перебор до 4096 наборов. Расчёт: ${window.CITY_RESILIENCE ? "модуль BUILD" : "адаптер K07 к plan.js"}.`));
    if (PS.cands.length > LIM.candidates) sec.append(el("p", { class: "warn", id: "rsTooMany", role: "alert" }, `too_many_candidates: в плане ${PS.cands.length} кандидатов > ${LIM.candidates}. Обычный план v2 считается как раньше; для анализа устойчивости уберите кандидатов сами — автоматически ничего не удаляется.`));
    // source selector
    const recs = records(), shown = recs.filter((r) => RS.qa === "all" || (RS.qa === "qa" ? r.qa.length : !r.qa.length));
    const fs = el("fieldset", { class: "rs-src" });
    fs.append(el("legend", null, `Исходные записи категории «${window.CITY_PLAN.CATEGORIES[PS.category]}» (${recs.length})`));
    const fl = el("label", { for: "rsQa" }, "Показать "), qs = el("select", { id: "rsQa" });
    for (const [k, v] of [["all", "все записи"], ["qa", "только с QA-флагом"], ["noqa", "без QA-флага"]]) { const o = el("option", { value: k }, v); if (k === RS.qa) o.selected = true; qs.append(o); }
    qs.addEventListener("change", () => { RS.qa = qs.value; U.render(); });
    fl.append(qs); fs.append(fl);
    if (!recs.length) fs.append(el("p", { class: "muted", id: "rsNoRecords" }, "В срезе нет записей этой категории — исключать нечего. Это не значит, что услуги нет в городе."));
    const ul = el("ul", { class: "rs-list", id: "rsSources" });
    for (const r of shown) {
      const li = el("li", { "data-rs-source": r.id }), cb = el("input", { type: "checkbox", id: "rsSrc_" + r.id });
      cb.checked = RS.sel.has(r.id);
      cb.addEventListener("change", () => { if (cb.checked) RS.sel.add(r.id); else RS.sel.delete(r.id); U.render(); });
      const lab = el("label", { for: "rsSrc_" + r.id });
      lab.append(document.createTextNode(r.name), el("span", { class: "muted" }, ` · ${r.src}${r.qa.length ? " · ⚠ " + r.qa.join(", ") : ""} · ${r.id.slice(0, 8)}`));
      li.append(cb, lab); ul.append(li);
    }
    fs.append(ul);
    const hidden = [...RS.sel].filter((id) => !shown.some((r) => r.id === id)).length;
    fs.append(el("p", { class: "muted", id: "rsSelCount" }, `Выбрано ${RS.sel.size}${hidden ? ` (из них скрыто фильтром ${hidden})` : ""}. QA-флаг не доказывает ошибку и не исключает запись сам.`));
    sec.append(fs);
    // new case
    const row = el("div", { class: "wi-ctl" });
    const lab = el("label", { for: "rsLabel" }, "Название случая ");
    const inp = el("input", { type: "text", id: "rsLabel", maxlength: String(LIM.label), value: RS.label, placeholder: "например: записи с QA-флагом", class: "rs-label" });
    const add = btn("rsAdd", "Добавить случай", () => { if (addCase()) focusAfter = "rsLabel"; U.render(); });
    add.disabled = !RS.sel.size || !RS.label.trim() || RS.cases.length >= LIM.cases;
    inp.addEventListener("input", () => { RS.label = inp.value; add.disabled = !RS.sel.size || !RS.label.trim() || RS.cases.length >= LIM.cases; });
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !add.disabled) { e.preventDefault(); add.click(); } });
    lab.append(inp); row.append(lab, add); sec.append(row);
    // cases
    sec.append(el("h4", { id: "rsCasesTitle", tabindex: "-1" }, `Случаи (${RS.cases.length} из ${LIM.cases}, плюс исходный срез)`));
    const ol = el("ol", { class: "rs-cases", id: "rsCases" });
    ol.append(el("li", { "data-rs-case": "base" }, "base — исходный срез, ничего не исключено"));
    RS.cases.forEach((c, i) => {
      const li = el("li", { "data-rs-case": c.id }), same = RS.cases.find((o) => o !== c && o.ids.join() === c.ids.join());
      li.append(el("strong", null, `${c.id} `), document.createTextNode(c.label), el("div", { class: "muted" }, "условно исключено: " + c.ids.map(nameOf).join("; ")));
      if (same) li.append(el("div", { class: "pill" }, `тот же набор, что ${same.id}`));
      li.append(btn("rsDel_" + c.id, "Удалить", () => { removeCase(c.id); const nx = RS.cases[i] || RS.cases[i - 1]; focusAfter = nx ? "rsDel_" + nx.id : "rsLabel"; U.render(); }, { "aria-label": `Удалить случай ${c.id} «${c.label}»` }));
      ol.append(li);
    });
    sec.append(ol);
    // run
    const rr = el("div", { class: "wi-ctl" });
    const run = btn("rsRun", "Сравнить планы по случаям", () => { startRun(); U.render(); });
    run.disabled = !!RS.run || !RS.cases.length || !PS.points.length || PS.cands.length > LIM.candidates;
    const cancel = btn("rsCancel", "Отменить сравнение", () => { stopRun("Сравнение отменено; ручной план не изменён, неполный результат не показывается."); focusAfter = "rsRun"; U.render(); });
    cancel.disabled = !RS.run;
    rr.append(run, cancel);
    if (RS.backup) rr.append(btn("rsRestore", "Вернуть ручной план", () => restore()));
    sec.append(rr);
    if (!RS.cases.length) sec.append(el("p", { class: "muted", id: "rsNoCases" }, "Добавьте хотя бы один случай, чтобы сравнить планы."));
    if (RS.run && RS.progress) {
      const pb = el("progress", { id: "rsProgress", max: Math.max(1, RS.progress.total), "aria-labelledby": "rsProgressText" }); pb.value = RS.progress.examined;
      sec.append(pb, el("span", { id: "rsProgressText", class: "muted" }, `просмотрено ${nf.format(RS.progress.examined)} из ${nf.format(RS.progress.total)} наборов`));
    }
    sec.append(el("p", { class: "wi-msg warn", id: "rsMsg", role: "status", "aria-live": "polite" }, RS.msg));
    renderResult(sec);
    if (focusAfter) { const want = focusAfter; focusAfter = null; setTimeout(() => { const f = $(want); if (f && !f.disabled) f.focus(); }, 0); }
  });
  function renderResult(sec) {
    const r = RS.result; if (!r) return;
    const stale = r.resilience_problem_digest !== currentDigest();
    sec.append(el("h4", { id: "rsResultTitle", tabindex: "-1" }, "Сравнение: ручной · обычный · устойчивый"));
    if (stale) { sec.append(el("p", { class: "warn", id: "rsStale", role: "alert" }, "Результат устарел: план или случаи изменены после сравнения. «Применить» недоступно — сравните снова.")); }
    if (r.status !== "optimal") { sec.append(el("p", { class: "warn", id: "rsInfeasible" }, "Нет допустимых планов: " + r.reasons.map((x) => x.text).join("; ") + ". Ограничения не снимались.")); return; }
    let man = null; try { man = RE.evaluateResilience(U.ctxOf(APP.state.city), envelope(), PS.selected); } catch (e) { man = null; }
    sec.append(el("p", { id: "rsPrice" }, r.price_of_robustness_m === null ? `Цена устойчивости: не определена — ${r.price_reason}.`
      : r.same_plan ? "Устойчивый план совпадает с обычным: цена устойчивости 0 м."
        : `Цена устойчивости: ${r.price_of_robustness_m > 0 ? "+" : ""}${nf.format(Math.round(r.price_of_robustness_m))} м среднего расстояния в исходном срезе (устойчивый минус обычный). Это расстояние по прямой, не деньги и не время.`));
    const box = el("div", { class: "pl-compare", id: "rsCompare", role: "list", "aria-label": "Ручной, обычный и устойчивый планы" });
    const card = (key, title, x, note, canApply) => {
      const c = el("div", { class: "pl-cmp", role: "listitem", "data-rs-plan": key });
      c.append(el("h4", null, title));
      if (note) c.append(el("p", { class: "pill" }, note));
      const dl = el("dl"), add = (k, v) => dl.append(el("dt", null, k), el("dd", null, v));
      add("Объекты", x.selected_ids.length ? x.selected_ids.join(", ") : "без новых объектов");
      add("Стоимость", units(x.cost));
      add("Исходный срез", metricLine(x.per_case[0].metrics));
      add("Худший результат", wText(x));
      c.append(dl);
      if (canApply) c.append(btn("rsApply_" + key, "Применить", () => apply(key), { disabled: stale || undefined, "aria-label": `Применить ${title.toLowerCase()} план` }));
      box.append(c);
    };
    if (man) card("manual", "Ручной", man, man.feasible ? null : "недопустим: " + man.feasibility.reasons.map((x) => x.text).join("; ") + " — не рекомендуется", false);
    card("nominal", "Обычный (лучшее среднее в исходном срезе)", r.nominal, null, true);
    card("robust", "Устойчивый (лучший худший случай)", r.robust, r.same_plan ? "тот же план, что «Обычный»" : null, true);
    sec.append(el("span", { id: "rsApplyAnchor", tabindex: "-1" }), box);
    // per-case table in an accessible scroll region (N2 r9)
    const t = el("table", { id: "rsTable", "aria-label": "Исходы по случаям" });
    const hr = el("tr"); for (const h of ["Случай", "Ручной", "Обычный", "Устойчивый"]) hr.append(el("th", null, h));
    const th = el("thead"); th.append(hr); t.append(th);
    const tb = el("tbody");
    r.nominal.per_case.forEach((pc, i) => {
      const tr = el("tr", { "data-rs-row": pc.case_id });
      tr.append(el("td", null, caseLabel(pc.case_id)));
      for (const x of [man, r.nominal, r.robust]) {
        if (!x) { tr.append(el("td", null, "—")); continue; }
        const m = x.per_case[i].metrics, worst = x.worst_case_ids.includes(pc.case_id);
        tr.append(el("td", null, (worst ? "★ " : "") + metricLine(m)));
      }
      tb.append(tr);
    });
    t.append(tb);
    const wrap = el("div", { class: "tablewrap", role: "region", "aria-label": "Исходы по случаям (прокручивается)", tabindex: "0" });
    wrap.append(t);
    sec.append(wrap, el("p", { class: "muted" }, `★ — худший случай этого плана. Без вероятностей и усреднения по случаям; цена устойчивости — только расстояние по прямой. Просмотрено ${nf.format(r.evaluated)} наборов; ${r.objective_version}, ${r.metric_version}.`));
  }
  window.CITY_RESILIENCE_UI = { state: RS, addCase, removeCase, startRun, stopRun, envelope, validEnv, currentDigest };
  U.render();
})();
