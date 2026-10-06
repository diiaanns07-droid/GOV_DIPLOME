// K07 r10: сценарий «Выбрать участок → Проверить школы и точки → Сравнить два места → Посмотреть результат» в браузере.
// Usage: node k07r10_walkthrough.cjs --url http://127.0.0.1:8502/ --shots DIR --out result.json
// Только клавиатура и клики по видимым элементам; ошибки страницы собираются.
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const URL = arg("--url", "http://127.0.0.1:8502/"), SHOTS = arg("--shots", "."), OUT = arg("--out", null);
fs.mkdirSync(SHOTS, { recursive: true });
const results = []; const check = (id, ok, info) => { results.push({ id, ok: !!ok, info }); console.log(`${ok ? "PASS" : "FAIL"} ${id} ${info ? JSON.stringify(info).slice(0, 240) : ""}`); };
const shot = (pg, n) => pg.screenshot({ path: path.join(SHOTS, n) });
async function open(b, vp, mobile) {
  const pg = await b.newPage({ viewport: vp, ...(mobile ? { hasTouch: true, isMobile: true } : {}) }); const errs = [];
  pg.on("pageerror", (e) => errs.push(String(e))); pg.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|ERR_TUNNEL|openfreemap/i.test(m.text())) errs.push(m.text()); });
  await pg.goto(URL, { waitUntil: "load" }); await pg.waitForTimeout(900);
  return { pg, errs };
}
const ST = (pg) => pg.evaluate(() => { const s = CITY_SCHOOL_PATH.state; const r = CITY_SCHOOL_PATH.compute();
  return { step: s.step, pts: s.points.length, A: !!s.A, B: !!s.B, view: s.view, msg: s.msg, reasons: r.reasons,
    now: r.now && r.now.metrics, a: r.A && r.A.metrics, b: r.B && r.B.metrics, changedA: r.A ? r.A.rows.filter((x) => x.nearest_after?.kind === "hypothetical").length : null,
    active: GOVTECH.active, page: GOVTECH.page, focus: document.activeElement?.id || document.activeElement?.tagName,
    lines: document.querySelectorAll("#gov-overlay line").length, changedLines: document.querySelectorAll("#gov-overlay line.sp-changed").length,
    hyp: [...document.querySelectorAll("#gov-overlay text")].map((t) => t.textContent).filter((t) => /гипотеза/.test(t)),
    offline: !document.getElementById("gov-offline").hidden, mapStatusVisible: getComputedStyle(document.getElementById("map-status")).display !== "none" && !document.getElementById("map-status").classList.contains("hidden"),
    kpi: document.getElementById("gov-kpi").innerText.replace(/\s+/g, " ").trim(), mapReady: typeof mapReady !== "undefined" && mapReady }; });
(async () => {
  const b = await chromium.launch();
  for (const [tag, vp, mobile] of [["1440", { width: 1440, height: 900 }, false], ["390", { width: 390, height: 844 }, true]]) {
    const { pg, errs } = await open(b, vp, mobile);
    const tap = (sel) => (mobile ? pg.tap(sel) : pg.click(sel));
    await tap("#govtech-toggle"); await pg.waitForTimeout(500);
    let s = await ST(pg);
    check(`${tag}_open_path`, s.active && s.page === "path" && s.step === 1 && !s.mapStatusVisible, s);
    check(`${tag}_offline_note`, s.mapReady || s.offline, { mapReady: s.mapReady, offline: s.offline });
    const schoolDots = await pg.evaluate(() => document.querySelectorAll("#gov-overlay circle").length);
    check(`${tag}_schools_visible`, s.mapReady || schoolDots >= 15, { schoolDots });
    await shot(pg, `after_${tag}_1_initial.png`);
    await tap("#spNext"); await pg.waitForTimeout(200);
    // шаг 2: «Дальше» недоступна без точек
    check(`${tag}_next_disabled_without_points`, await pg.$eval("#spNext", (e) => e.disabled));
    await tap("#spExample"); await pg.waitForTimeout(200);
    s = await ST(pg); check(`${tag}_example_points`, s.pts === 9 && /ПРИМЕРНЫХ/.test(s.msg), { pts: s.pts });
    // одна точка кликом по карте, с первой попытки
    await tap("#spPlacePoints"); await pg.waitForTimeout(150);
    const bb = await pg.evaluate(() => { const c = D_ = CITY_APP.ui.D.cities[CITY_APP.state.city].bbox; const p = CITY_APP.ui.toScreen((c[0] + c[2]) / 2 + (c[2] - c[0]) * .1, (c[1] + c[3]) / 2); const r = document.getElementById("map").getBoundingClientRect(); return [p[0] + r.left, p[1] + r.top]; });
    if (mobile) await pg.touchscreen.tap(bb[0], bb[1]); else await pg.mouse.click(bb[0], bb[1]);
    await pg.waitForTimeout(200);
    s = await ST(pg); check(`${tag}_click_adds_point_first_try`, s.pts === 10, { pts: s.pts, at: bb, msg: s.msg });
    await tap("#spPlacePoints"); await tap("#spNext"); await pg.waitForTimeout(200);
    // шаг 3: A кликом, B клавиатурой (Enter на карте)
    await tap("#spPlaceA"); await pg.waitForTimeout(100);
    const pa = await pg.evaluate(() => { const c = CITY_APP.ui.D.cities[CITY_APP.state.city].bbox; const p = CITY_APP.ui.toScreen(c[0] + (c[2] - c[0]) * .3, c[1] + (c[3] - c[1]) * .3); const r = document.getElementById("map").getBoundingClientRect(); return [p[0] + r.left, p[1] + r.top]; });
    if (mobile) await pg.touchscreen.tap(pa[0], pa[1]); else await pg.mouse.click(pa[0], pa[1]);
    await pg.waitForTimeout(150);
    await pg.focus("#spPlaceB"); await pg.keyboard.press("Enter"); await pg.waitForTimeout(100);
    const mapFocusable = await pg.evaluate(() => { const m = document.querySelector("#map canvas") || document.getElementById("map"); m.focus(); return document.activeElement === m; });
    await pg.keyboard.press("Enter"); await pg.waitForTimeout(150);
    s = await ST(pg); check(`${tag}_place_A_click_B_keyboard`, s.A && s.B, { A: s.A, B: s.B, mapFocusable, msg: s.msg });
    await shot(pg, `after_${tag}_2_A_B_placed.png`);
    // порог: ввод и сразу «Посмотреть результат» (без Tab)
    await pg.fill("#spThreshold", "400");
    await tap("#spNext"); await pg.waitForTimeout(250);
    s = await ST(pg); check(`${tag}_threshold_then_result_first_try`, s.step === 4 && /400/.test(s.kpi), { step: s.step, kpi: s.kpi });
    check(`${tag}_result_metrics`, s.now && s.a && s.b && s.reasons.length === 0, { now: s.now, a: s.a, b: s.b, reasons: s.reasons });
    check(`${tag}_changed_paths_highlighted`, s.changedA > 0 && s.changedLines === s.changedA && s.lines >= 10 && s.hyp.length === 2, { lines: s.lines, changed: s.changedLines, changedA: s.changedA, hyp: s.hyp });
    const tradeoff = await pg.$eval(".sp-trade", (e) => e.textContent).catch(() => null);
    const src = await pg.$eval(".sp-src", (e) => e.textContent).catch(() => null);
    const methodOpen = await pg.$eval("#spMethod", (e) => e.open).catch(() => null);
    check(`${tag}_tradeoff_sources_collapsed`, !!tradeoff && /Overture/.test(src || "") && /по прямой/.test(src || "") && methodOpen === false, { tradeoff, src: (src || "").slice(0, 120) });
    check(`${tag}_focus_on_step_title`, s.focus === "pathStepTitle", { focus: s.focus });
    await shot(pg, `after_${tag}_3_result_A.png`);
    await tap("#spView_B"); await pg.waitForTimeout(150);
    s = await ST(pg); check(`${tag}_view_B_switch`, s.view === "B" && s.lines >= 10, { view: s.view, changed: s.changedLines });
    await shot(pg, `after_${tag}_4_result_B.png`);
    // источник рядом с числом → карточка записи
    await tap("#spWorstSrc"); await pg.waitForTimeout(200);
    const sel = await pg.evaluate(() => ({ page: GOVTECH.page, text: document.getElementById("gov-selection").innerText.slice(0, 160) }));
    check(`${tag}_source_record_opens`, sel.page === "data" && /Источник/.test(sel.text), sel);
    await tap('#gov-panel [data-page="path"]'); await pg.waitForTimeout(150);
    // Дополнительно → План (бюджет) доступен, но не в основном пути
    await tap('#gov-panel [data-page="more"]'); await pg.waitForTimeout(150);
    await tap('#moreCard [data-goto="plan"]'); await pg.waitForTimeout(200);
    const planVis = await pg.evaluate(() => ({ page: GOVTECH.page, budgetVisible: !!document.getElementById("plBudget")?.offsetParent }));
    check(`${tag}_advanced_plan_reachable`, planVis.page === "plan" && planVis.budgetVisible, planVis);
    await tap('#gov-panel [data-page="path"]'); await pg.waitForTimeout(150);
    const budgetOnPath = await pg.evaluate(() => !!document.getElementById("plBudget")?.offsetParent);
    check(`${tag}_no_budget_on_main_path`, !budgetOnPath);
    // смена города: сброс с понятным сообщением
    await tap('#gov-panel [data-city="astana"]'); await pg.waitForTimeout(300);
    s = await ST(pg); check(`${tag}_city_switch_resets`, s.pts === 0 && !s.A && /Город изменён/.test(s.msg) && s.step === 1, { msg: s.msg, step: s.step });
    await shot(pg, `after_${tag}_5_city_astana.png`);
    // возврат в учебный режим: Score учебной модели на месте, наши слои скрыты
    await tap("#govtech-toggle"); await pg.waitForTimeout(400);
    const back = await pg.evaluate(() => ({ active: GOVTECH.active, kpiHidden: document.getElementById("gov-kpi").hidden, overlay: getComputedStyle(document.getElementById("gov-overlay")).display,
      title: document.querySelector(".brand-title").textContent, body: document.body.innerText.includes("52.56") || document.body.innerText.includes("52,56") }));
    check(`${tag}_return_to_simulator`, !back.active && back.kpiHidden && back.overlay === "none" && /Аким/.test(back.title), back);
    await shot(pg, `after_${tag}_6_simulator.png`);
    check(`${tag}_no_page_errors`, errs.length === 0, errs.slice(0, 3));
    await pg.close();
  }
  await b.close();
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ url: URL, results }, null, 1));
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})();
