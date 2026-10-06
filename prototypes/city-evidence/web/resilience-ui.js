/* «Устойчивость к допущениям» — UI of city-resilience-v1 (round 9) on top of the v2 planner (plan-ui.js).
 * The user names cases in which chosen SOURCE records are conditionally left out of the calculation (never deleted,
 * never marked as closed). Every number comes from resilience.js; this file edits state, draws and handles files.
 * Strings are inserted with textContent only. The manual plan changes only through «Применить».
 */
(function () {
  "use strict";
  const APP = window.CITY_APP, U = window.CITY_PLAN_UI, RS = window.CITY_RESILIENCE, PL = window.CITY_PLAN;
  if (!APP || !APP.ui || !U || !RS || !PL) return;
  const { el, sv, $, D, F, EXT, toScreen, renderMap, updateStatus, qaOf, selectPlace } = APP.ui;
  const STATE = APP.state;
  const RSS = { cases: [], seq: 1, key: null, msg: "", status: "idle", request_id: 0, digest: null, examined: 0, total: 0, result: null, expl: null, backup: null, show: null, open: {} };
  const CHUNK = 256;
  const keyNow = () => `${STATE.city}|${U.state.category}`;
  const mm = (v) => U.mmText(v);
  const ctx = () => U.ctxOf(STATE.city);
  function sources() {
    return D.cities[STATE.city].places.filter((p) => p.group === U.state.category).slice()
      .sort((a, b) => (a.name || "").localeCompare(b.name || "", "ru") || (a.id < b.id ? -1 : 1));
  }
  function envelope() {
    return { schema_version: RS.SCHEMA, plan: U.rawScenario(), cases: RSS.cases.map((c) => ({ id: c.id, label: c.label, disabled_source_ids: [...c.ids] })) };
  }
  function validated() { return RS.validateResilience(envelope(), ctx()); }
  function digestNow() { try { return RS.resilienceProblemDigest(validated(), F); } catch (e) { return null; } }

  // ---------- state changes: cases are tied to city + category; any input change invalidates an answer ----------
  function resetCases(reason) {
    if (RSS.status === "running") for (const j of RSS.jobs || []) j.cancel();
    Object.assign(RSS, { cases: [], seq: 1, key: keyNow(), status: "idle", result: null, expl: null, backup: null, show: null, msg: reason || "" });
    RSS.request_id++;
  }
  function invalidate() {
    const d = digestNow();
    if (RSS.status === "running" && d !== RSS.digest) { for (const j of RSS.jobs || []) j.cancel(); RSS.status = "stale"; RSS.request_id++; RSS.msg = "Входные данные изменились — поиск остановлен, его ответ не будет показан."; }
    else if (RSS.status === "done" && d !== RSS.digest) { RSS.status = "stale"; RSS.result = null; RSS.msg = "Входные данные изменились — прежнее сравнение устарело. Запустите снова."; }
  }
  function changed(msg) { if (msg !== undefined) RSS.msg = msg; invalidate(); render(); renderMap(); }
  function ensureKey() {
    if (RSS.key === null) RSS.key = keyNow();
    if (RSS.key !== keyNow()) resetCases(RSS.cases.length ? "Город или категория изменились — случаи сброшены: ID исходных записей не переносятся." : "");
  }
  function addCase() { U.flush();
    if (RSS.cases.length >= RS.LIMITS.user_cases) { changed(`Не больше ${RS.LIMITS.user_cases} случаев (плюс базовый).`); return; }
    let id; do { id = "c" + RSS.seq++; } while (RSS.cases.some((c) => c.id === id));
    RSS.cases.push({ id, label: `Случай ${id.slice(1)}`, ids: new Set() });
    RSS.open[id] = true;
    changed(`Случай ${id} добавлен. Отметьте записи, которые условно не учитывать.`);
    focus(`rsLabel_${id}`);
  }
  function removeCase(id) {
    const i = RSS.cases.findIndex((c) => c.id === id);
    RSS.cases = RSS.cases.filter((c) => c.id !== id);
    if (RSS.show === id) RSS.show = null;
    changed(`Случай ${id} удалён.`);
    const nx = RSS.cases[i] || RSS.cases[i - 1];
    focus(nx ? `rsDel_${nx.id}` : "rsAdd");
  }
  function setLabel(id, raw) {
    const c = RSS.cases.find((x) => x.id === id); if (!c) return;
    const v = String(raw);
    if (!v.trim() || [...v].length > RS.LIMITS.label || /[\u0000-\u001f\u007f-\u009f]/.test(v)) { changed("Название случая: непустой текст до 120 символов; значение не применено."); return; }
    c.label = v; changed();
  }
  function toggleRecord(id, recId, on) { const c = RSS.cases.find((x) => x.id === id); if (!c) return; if (on) c.ids.add(recId); else c.ids.delete(recId); changed(); }
  function focus(id) { setTimeout(() => { const f = document.getElementById(id); if (f && f.getClientRects().length) f.focus(); }, 0); }

  // ---------- search: chunked on the event loop; request_id + problem digest guard against late answers ----------
  function start() { U.flush();
    let env;
    try { env = validated(); } catch (e) { RSS.msg = "Сравнение не запущено: " + (e.detail || e.message); render(); return; }
    const rid = ++RSS.request_id, s = RS.createResilienceSearch(ctx(), env, { F, request_id: rid }), digest = RS.resilienceProblemDigest(env, F);
    Object.assign(RSS, { status: "running", digest, examined: 0, total: s.total, result: null, expl: null, msg: "", jobs: [s] });
    render();
    const tick = () => {
      if (RSS.request_id !== rid || RSS.status !== "running") { s.cancel(); return; }
      const done = s.step(CHUNK);
      RSS.examined = s.examined;
      const pr = $("rsProgress"); if (pr) pr.value = s.examined;
      const pt = $("rsProgressText"); if (pt) pt.textContent = ` просмотрено ${s.examined} из ${s.total} наборов`;
      if (!done) { setTimeout(tick, 0); return; }
      const r = s.result();
      if (RSS.request_id !== rid || digestNow() !== digest || r.resilience_problem_digest !== digest) { RSS.status = "stale"; RSS.msg = "Ответ устарел и отброшен."; render(); return; }
      RSS.result = r; RSS.status = "done";
      RSS.msg = r.status === "infeasible" ? "Нет допустимых планов: " + r.reasons.map((x) => x.text).join("; ") : `Готово: просмотрены все ${r.evaluated} наборов, допустимых ${r.feasible_count}.`;
      render();
    };
    setTimeout(tick, 0);
  }
  function cancel() {
    if (RSS.status !== "running") return;
    for (const j of RSS.jobs || []) j.cancel();
    RSS.status = "cancelled"; RSS.request_id++; RSS.result = null;
    RSS.msg = `Сравнение отменено (просмотрено ${RSS.examined} из ${RSS.total}); неполный результат не показывается, ручной план не изменён.`;
    render();
  }
  function apply(which) { U.flush();
    const r = RSS.result;
    if (RSS.status !== "done" || !r || r.status !== "optimal" || r.resilience_problem_digest !== digestNow()) { RSS.msg = "Нечего применять: результат отсутствует или устарел."; render(); return false; }
    if (!RSS.backup) RSS.backup = U.state.selected.slice();
    U.state.selected = r[which].selected_ids.slice();
    U.changed(`План «${which === "robust" ? "Устойчивый" : "Обычный"}» применён как ручной (условное предложение). «Вернуть ручной план» отменит это.`);
    RSS.msg = `Применён план «${which === "robust" ? "Устойчивый" : "Обычный"}».`;
    render(); focus(`rsApply_${which}`);
    return true;
  }
  function restore() { if (!RSS.backup) return; U.state.selected = RSS.backup; RSS.backup = null; U.changed("Ручной план восстановлен."); RSS.msg = "Ручной план восстановлен."; render(); focus("rsRun"); }

  // ---------- files and report ----------
  function download(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = el("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportText() { return RS.exportResilience(ctx(), envelope()); }
  function exportFile() { U.flush();
    let t; try { t = exportText(); } catch (e) { RSS.msg = "Сохранить нельзя: " + (e.detail || e.message); render(); return; }
    download(`city-resilience-${STATE.city}-${U.state.category}.json`, t, "application/json");
    RSS.msg = `Сохранено: city-resilience-${STATE.city}-${U.state.category}.json (только входные данные: план и случаи).`; render();
  }
  // import: the whole file is validated first; on failure nothing changes (plan, cases, city)
  function importText(text) {
    let r;
    try { r = RS.importResilience(text, (c) => U.ctxOf(c)); } catch (e) { RSS.msg = "Файл не принят, текущее состояние не изменено: " + String(e.detail || e.message).slice(0, 240); render(); return false; }
    const env = r.envelope;
    U.loadScenario(env.plan, `План загружен из файла устойчивости (${D.cities[env.plan.city_id].label}, ${PL.CATEGORIES[env.plan.category]}).`);
    resetCases("");
    RSS.cases = env.cases.map((c) => ({ id: c.id, label: c.label, ids: new Set(c.disabled_source_ids) }));
    RSS.seq = RSS.cases.length + 1; RSS.key = keyNow();
    changed(`Файл устойчивости загружен: ${env.cases.length} случаев; результаты пересчитываются заново — запустите сравнение.`);
    return true;
  }
  function importFile(f) {
    if (f.size > 262144) { RSS.msg = `Файл не принят: ${f.size} байт больше 262144. Текущее состояние не изменено.`; render(); return; }
    f.text().then(importText, () => { RSS.msg = "Файл не прочитан; текущее состояние не изменено."; render(); });
  }
  function manualEval(env) { return env.plan.control_points.length ? RS.evaluateResilience(ctx(), env, env.plan.selected_ids) : null; }
  function currentResult(env) { const r = RSS.result; return RSS.status === "done" && r && r.resilience_problem_digest === RS.resilienceProblemDigest(env, F) ? r : null; }
  function reportText() {
    const env = validated(), c = D.cities[STATE.city], res = currentResult(env);
    const qa = {}, names = {};
    for (const p of c.places) { names[p.id] = p.name || "Без названия"; const q = qaOf(p); if (q.length) qa[p.id] = q.map((x) => x.code); }
    const att = [...new Set((c.attribution || []).map((a) => a.dataset))].join("; ");
    return RS.reportHtml({ envelope: env, city_label: c.label, release: `Overture ${c.release}`, problem_digest: RS.resilienceProblemDigest(env, F), exclusions_digest: RS.exclusionsDigest(env, F),
      generated: new Date().toISOString().slice(0, 19).replace("T", " ") + " UTC", manual: manualEval(env), result: res, names, qa, demo: U.state.demo,
      explanation: RSS.expl && RSS.expl.digest === explDigest() ? RSS.expl.text : null,
      attribution: `Источники записей: ${att || "не указаны"} (через Overture Maps ${c.release}); лицензии — web/attribution/ATTRIBUTION.md.` });
  }
  function reportFile() { U.flush();
    let t; try { t = reportText(); } catch (e) { RSS.msg = "Отчёт не создан: " + (e.detail || e.message); render(); return; }
    download(`city-resilience-report-${STATE.city}-${U.state.category}.html`, t, "text/html");
    RSS.msg = "HTML-отчёт сохранён (пересчитан, без скриптов)."; render();
  }
  function explDigest() { try { const env = validated(); return F.sha256hex(JSON.stringify([RS.resilienceScenarioDigest(env, F), currentResult(env) ? RSS.result.resilience_problem_digest : null])).slice(0, 16); } catch (e) { return null; } }
  function explain() { U.flush();
    let env; try { env = validated(); } catch (e) { RSS.msg = "Объяснение недоступно: " + (e.detail || e.message); render(); return; }
    RSS.expl = { digest: explDigest(), text: RS.explainResilience(env, manualEval(env), currentResult(env)) };
    render();
  }

  // ---------- map: excluded records of the case chosen for display (dashed red cross; records stay on the map) ----------
  EXT.layers.push((g, gLabel) => {
    if (STATE.tool !== "v2" || !RSS.show) return;
    const c = RSS.cases.find((x) => x.id === RSS.show); if (!c) return;
    for (const p of D.cities[STATE.city].places) {
      if (!c.ids.has(p.id)) continue;
      const [x, y] = toScreen(p.lon, p.lat);
      g.append(sv("path", { d: `M${x - 9} ${y - 9}L${x + 9} ${y + 9}M${x + 9} ${y - 9}L${x - 9} ${y + 9}`, stroke: "var(--critical)", "stroke-width": 2, "stroke-dasharray": "3 2", "data-rs-off": p.id }));
    }
    const t = sv("text", { x: 12, y: 18, "font-size": 11, fill: "var(--critical)" }); t.textContent = `Случай ${c.id}: ✕ — условно не учитываются (не закрыты)`; gLabel.append(t);
  });

  // ---------- card ----------
  const btn = (id, text, onClick, extra) => { const b = el("button", { type: "button", class: "tool", id, ...(extra || {}) }, text); b.addEventListener("click", onClick); return b; };
  const idsText = (ids) => (ids.length ? ids.join(", ") : "без новых объектов");
  function render() {
    const card = $("resCard"), b = $("resBody");
    if (!card) return;
    card.hidden = STATE.tool !== "v2";
    if (card.hidden) return;
    ensureKey();
    const act = document.activeElement, focusId = act && act.id && b.contains(act) ? act.id : null;
    b.replaceChildren();
    b.append(el("p", { class: "warn", id: "rsNotice" }, "Условно исключаем из расчёта; это не подтверждение закрытия. Пустые исходные данные не означают отсутствие услуги. Сравнение использует план v2 выше: те же точки, кандидаты, стоимости и ограничения."));
    const nC = U.state.cands.length;
    if (nC > RS.LIMITS.candidates) b.append(el("p", { class: "err", id: "rsLimit" }, `Анализ устойчивости — до ${RS.LIMITS.candidates} кандидатов, сейчас ${nC}. Ничего не отбрасывается автоматически: удалите лишних кандидатов в плане v2 (обычный v2 по-прежнему решает до 16).`));
    const src = sources();
    if (!src.length) b.append(el("p", { class: "warn" }, "В срезе нет исходных записей этой категории — исключать нечего; это не значит, что услуги нет."));
    // cases
    b.append(el("h3", null, `Случаи (${RSS.cases.length} из ${RS.LIMITS.user_cases}) + базовый «все записи»`));
    const row = el("div", { class: "wi-ctl" });
    const add = btn("rsAdd", "Добавить случай", addCase); add.disabled = RSS.cases.length >= RS.LIMITS.user_cases || !src.length;
    row.append(add); b.append(row);
    const dupGroups = (() => { const by = new Map(); for (const c of RSS.cases) { const k = [...c.ids].sort().join("|"); if (!k) continue; by.set(k, [...(by.get(k) || []), c.id]); } return [...by.values()].filter((g) => g.length > 1); })();
    if (dupGroups.length) b.append(el("p", { class: "pill", id: "rsDup" }, "Одинаковые наборы исключений: " + dupGroups.map((g) => g.join(" = ")).join("; ") + " — допустимо, результат от повтора не меняется."));
    for (const c of RSS.cases) {
      const d = el("details", { id: `rsCase_${c.id}`, class: "pl-sec" });
      d.open = !!RSS.open[c.id];
      const sm = el("summary", { id: `rsCase_${c.id}_sum` }, `${c.id}: ${c.label} — исключено ${c.ids.size} из ${src.length}`);
      sm.addEventListener("click", () => { RSS.open[c.id] = !d.open; });
      d.append(sm);
      const ctl = el("div", { class: "wi-ctl" });
      const lab = el("label", { class: "ctl", for: `rsLabel_${c.id}` }, "Название ");
      const inp = el("input", { type: "text", id: `rsLabel_${c.id}`, value: c.label, maxlength: 120, class: "rs-label" });
      inp.addEventListener("change", () => { const v = inp.value; U.defer(() => setLabel(c.id, v)); });
      lab.append(inp);
      ctl.append(lab, btn(`rsShow_${c.id}`, RSS.show === c.id ? "Скрыть на карте" : "Показать на карте", () => { RSS.show = RSS.show === c.id ? null : c.id; render(); renderMap(); }, { "aria-pressed": String(RSS.show === c.id) }),
        btn(`rsDel_${c.id}`, "Удалить случай", () => removeCase(c.id), { "aria-label": `Удалить случай ${c.id}` }));
      d.append(ctl);
      if (!c.ids.size) d.append(el("p", { class: "warn" }, "Не выбрано ни одной записи — отметьте хотя бы одну, иначе сравнение не запустится."));
      const t = el("table", { class: "rs-recs", "aria-label": `Исходные записи для случая ${c.id}` });
      const hr = el("tr"); for (const h of ["Не учитывать", "Запись (источник, QA)"]) hr.append(el("th", null, h));
      const th = el("thead"); th.append(hr); t.append(th);
      const tb = el("tbody");
      src.forEach((p, k) => {
        const tr = el("tr");
        const cb = el("input", { type: "checkbox", id: `rsX_${c.id}_${k}`, "data-rs-rec": p.id });
        cb.checked = c.ids.has(p.id);
        cb.addEventListener("change", () => toggleRecord(c.id, p.id, cb.checked));
        const td0 = el("td"); td0.append(cb);
        const qa = qaOf(p), lab2 = el("label", { for: `rsX_${c.id}_${k}` }, `${qa.length ? "⚠ " : ""}${p.name || "Без названия"}`);
        const td1 = el("td"); td1.append(lab2, el("div", { class: "muted" }, `${p.id} · ${(p.sources[0] || {}).dataset || "источник не указан"}${qa.length ? " · QA: " + qa.map((q) => q.code).join(", ") : ""}`));
        tr.append(td0, td1); tb.append(tr);
      });
      t.append(tb); d.append(t); b.append(d);
    }
    b.append(el("p", { class: "wi-msg warn", id: "rsMsg", role: "status", "aria-live": "polite" }, RSS.msg));
    // run
    let env = null, err = null;
    try { env = validated(); } catch (e) { err = e; }
    const r2 = el("div", { class: "wi-ctl" });
    const run = btn("rsRun", "Сравнить три плана (точный перебор)", start); run.disabled = !env || RSS.status === "running";
    const can = btn("rsCancel", "Отменить", cancel); can.disabled = RSS.status !== "running";
    r2.append(run, can);
    if (RSS.backup) r2.append(btn("rsRestore", "Вернуть ручной план", restore));
    b.append(r2);
    if (err && (RSS.cases.length || U.state.points.length)) b.append(el("p", { class: "muted", id: "rsWhyNot" }, "Пока нельзя запустить: " + (err.detail || err.message)));
    if (RSS.status === "running") {
      const pr = el("progress", { id: "rsProgress", max: Math.max(1, RSS.total), "aria-label": "Ход сравнения" }); pr.value = RSS.examined;
      b.append(pr, el("span", { id: "rsProgressText", class: "muted" }, ` просмотрено ${RSS.examined} из ${RSS.total} наборов`));
    }
    if (env) renderResults(b, env);
    // files
    b.append(el("h3", null, "Объяснение и файлы"));
    const r3 = el("div", { class: "wi-ctl" });
    const e1 = btn("rsExplain", "Объяснить", explain); e1.disabled = !env;
    const e2 = btn("rsExport", "Сохранить (JSON)", exportFile); e2.disabled = !env;
    const file = el("input", { type: "file", id: "rsFile", accept: ".json,application/json", hidden: "" });
    file.addEventListener("change", () => { const f = file.files && file.files[0]; file.value = ""; if (f) importFile(f); });
    const e3 = btn("rsImport", "Загрузить", () => file.click());
    const e4 = btn("rsReport", "Отчёт HTML", reportFile); e4.disabled = !env;
    r3.append(e1, e2, e3, e4, file); b.append(r3);
    if (RSS.expl) {
      if (RSS.expl.digest !== explDigest()) RSS.expl = null;
      else { const box = el("div", { class: "explain", id: "rsExplainText" }); box.append(el("div", { class: "who" }, `шаблонное объяснение по вычисленным фактам (не LLM) · ${RSS.expl.digest}`));
        for (const line of RSS.expl.text.split("\n")) box.append(el("p", null, line)); b.append(box); }
    }
    if (focusId) { let f = document.getElementById(focusId); if (f && f.disabled) f = document.getElementById({ rsRun: "rsCancel", rsCancel: "rsRun" }[focusId] || ""); if (f && !f.disabled) f.focus(); }
  }
  function renderResults(b, env) {
    const man = manualEval(env), res = currentResult(env);
    const tw = env.plan.control_points.reduce((t, p) => t + p.weight, 0);
    const labelOf = Object.fromEntries(RS.allCases(env).map((c) => [c.id, c.label]));
    const plans = [["manual", "Ручной", man], ...(res && res.status === "optimal" ? [["nominal", "Обычный", res.nominal], ["robust", "Устойчивый", res.robust]] : [])];
    if (!man) return;
    b.append(el("h3", null, "Сравнение планов по всем случаям"));
    if (res && res.status === "optimal") {
      const pr = res.price_of_robustness_m;
      b.append(el("p", { class: "pill", id: "rsPrice" }, pr === null ? `Цена устойчивости не вычисляется: ${res.price_reason}.` : `Цена устойчивости в базовом случае: ${pr >= 0 ? "+" : ""}${pr.toFixed(1).replace(".", ",")} м к взвешенному среднему по прямой.`));
      if (res.same_plan) b.append(el("p", { class: "muted", id: "rsSame" }, "Обычный и устойчивый планы совпали — при этих случаях устойчивость ничего не меняет."));
    }
    const box = el("div", { class: "pl-compare", id: "rsCompare", role: "list" });
    for (const [k, title, p] of plans) {
      const c = el("div", { class: "pl-cmp", role: "listitem", "data-rs-plan": k });
      c.append(el("h4", null, title));
      const notes = [];
      if (k === "manual" && !p.feasibility.feasible) notes.push("недопустим — не рекомендуется: " + p.feasibility.reasons.map((x) => x.text).join("; "));
      if (k === "robust" && res.same_plan) notes.push("тот же план, что «Обычный»");
      if (k !== "manual" && p.selected_ids.join() === man.selected_ids.join()) notes.push("совпадает с ручным");
      for (const n of notes) c.append(el("p", { class: "pill" }, n));
      const dl = el("dl"), add = (a, v) => dl.append(el("dt", null, a), el("dd", null, v));
      const base = p.per_case[0].metrics;
      add("Объекты", idsText(p.selected_ids)); add("Стоимость", `${p.cost} усл. ед.`);
      add("Базовый: среднее", mm(base.weighted_mean_mm));
      const wv = p.worst_vector;
      add("Худший исход", `${wv.unknown_count ? wv.unknown_count + " точек без расстояния; " : ""}среднее ${wv.unknown_count ? "не определено" : mm(wv.weighted_sum_mm / tw)}, худшая точка ${mm(wv.max_mm)}`);
      add("Худшие случаи", p.worst_case_ids.map((id) => `${id} (${labelOf[id]})`).join(", "));
      c.append(dl);
      if (k !== "manual") c.append(btn(`rsApply_${k}`, "Применить", () => apply(k), { "aria-label": `Применить план «${title}»` }));
      box.append(c);
    }
    b.append(box);
    // per-case table (accessible; map is optional)
    const t = el("table", { id: "rsTable", "aria-label": "Исходы планов по случаям" });
    t.append(el("caption", { class: "muted" }, "среднее и худшая точка — по прямой; ▲ — худший случай плана; «нет данных» — у точки нет ни записи, ни выбранного объекта"));
    const hr = el("tr"); hr.append(el("th", null, "Случай")); for (const [, title] of plans) hr.append(el("th", null, title));
    const th = el("thead"); th.append(hr); t.append(th);
    const tb = el("tbody");
    for (const c of RS.allCases(env)) {
      const tr = el("tr", { "data-rs-case": c.id }); tr.append(el("td", null, `${c.id}: ${c.label}${c.id === "base" ? "" : ` (−${c.disabled_source_ids.length})`}`));
      for (const [, , p] of plans) {
        const x = p.per_case.find((y) => y.case_id === c.id), m = x.metrics;
        const txt = `${mm(m.weighted_mean_mm)} · худшая ${mm(m.max_mm)} · охват ${m.covered_weight}/${tw}${m.unknown_count ? ` · без расстояния: ${m.unknown_count}` : ""}`;
        tr.append(el("td", { class: p.worst_case_ids.includes(c.id) ? "rs-worst" : null }, (p.worst_case_ids.includes(c.id) ? "▲ " : "") + txt));
      }
      tb.append(tr);
    }
    t.append(tb);
    const wrap = el("div", { class: "tablewrap" }); wrap.append(t); b.append(wrap);
    if (res && res.status === "optimal") b.append(el("p", { class: "muted" }, `Просмотрено ${res.evaluated} наборов, допустимых ${res.feasible_count}. Результат — только предложение; ручной план меняется кнопкой «Применить». Отпечаток ${res.resilience_problem_digest.slice(7, 23)}.`));
  }

  // ---------- registration ----------
  U.onProblemChange(() => { invalidate(); });
  U.afterRender(() => setTimeout(render, 0));
  // hooks run before STATE.city changes: the key is set for the NEW city so the next render does not reset a second time
  EXT.onCity.push((key, changedCity) => { if (changedCity) { resetCases(RSS.cases.length ? "Город изменён — случаи сброшены: ID записей другого города не переносятся." : ""); RSS.key = `${key}|${U.state.category}`; } });
  EXT.onTool.push(() => render());
  EXT.cards.push(() => render());
  window.CITY_RESILIENCE_UI = { state: RSS, addCase, removeCase, setLabel, toggleRecord, start, cancel, apply, restore, envelope, exportText, importText, reportText, explain, render, sources };
  render();
})();
