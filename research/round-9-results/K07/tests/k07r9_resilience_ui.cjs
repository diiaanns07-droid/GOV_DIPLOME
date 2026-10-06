// K07 round 9: browser tests of the REAL BUILD page with the K07 «Устойчивость к допущениям» panel (plan card of BUILD).
// Usage: node k07r9_resilience_ui.cjs --app-root <BUILD extraction (+ K07 r9 patches)> [--label …] [--sha …] [--out …]
// Desktop 1400 px and 390 px: number editing, choosing / un-choosing source records, adding / deleting cases (keyboard),
// compare / cancel / stale, apply / restore, null messages, the 12-candidate limit, city and category switches.
// Numbers are compared with the engine in the page (window.CITY_RESILIENCE or CITY_RESILIENCE_K07, synchronous path).
// Data: BUILD's own SYNTHETIC demo set (weights, sites, costs invented) on the real K10 slices; real source record IDs.
// Verdicts: PASS | FAIL | TEST_INCOMPATIBLE (precondition not met — never PASS).
const path = require("path"), fs = require("fs"), { pathToFileURL } = require("url");
const { chromium } = require("playwright");
const a = process.argv.slice(2), OPT = { label: "res", sha: null, out: null, appRoot: null };
for (let i = 0; i < a.length; i++) { const k = a[i], v = a[i + 1]; if (k === "--app-root") { OPT.appRoot = v; i++; } else if (k === "--label") { OPT.label = v; i++; } else if (k === "--sha") { OPT.sha = v; i++; } else if (k === "--out") { OPT.out = v; i++; } else { console.error("unknown argument " + k); process.exit(2); } }
const ROOT = path.resolve(OPT.appRoot), WEB = fs.existsSync(path.join(ROOT, "web")) ? path.join(ROOT, "web") : ROOT;
const URL_ = pathToFileURL(path.join(WEB, "index.html")).href;
const OUT = path.resolve(OPT.out || path.join(__dirname, "..", "results", OPT.label)), SHOTS = path.join(OUT, "screenshots");
const checks = [];
const check = (id, area, expect, ok, observed, pre) => checks.push({ id, area, expect, verdict: pre === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL", observed: observed === undefined ? null : observed });

async function open(browser, vp) {
  const ctx = await browser.newContext({ viewport: vp || { width: 1400, height: 1000 } }), p = await ctx.newPage(), errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  p.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  await p.goto(URL_);
  await p.waitForSelector("#map g[data-id]", { timeout: 15000 });
  return { p, ctx, errors };
}
const srcSel = (id) => `[id="rsSrc_${id}"]`;
const rs = (p) => p.evaluate(() => {
  const S = window.CITY_RESILIENCE_UI.state, PS = window.CITY_PLAN_UI.state;
  return { cases: S.cases.map((c) => ({ id: c.id, label: c.label, ids: c.ids.slice() })), sel: [...S.sel], running: !!S.run, result: S.result && { status: S.result.status, digest: S.result.resilience_problem_digest },
    msg: (document.getElementById("rsMsg") || {}).textContent || "", stale: !!document.getElementById("rsStale"), selected: PS.selected.slice().sort(), city: window.CITY_APP.state.city, category: PS.category,
    sources: [...document.querySelectorAll("#rsSources li")].map((li) => li.dataset.rsSource), focus: document.activeElement.id || document.activeElement.tagName };
});
const engineResult = (p) => p.evaluate(() => { const RE = window.CITY_RESILIENCE || window.CITY_RESILIENCE_K07, U = window.CITY_PLAN_UI;
  const r = RE.optimizeResilience(U.ctxOf(window.CITY_APP.state.city), window.CITY_RESILIENCE_UI.envelope(), { F: window.CITY_FACTS });
  return { status: r.status, nominal: r.nominal && r.nominal.selected_ids, robust: r.robust && r.robust.selected_ids, price: r.price_of_robustness_m, worstR: r.robust && r.robust.worst_case_ids }; });
async function setup(p) { await p.click('#toolSeg button[data-tool="v2"]'); await p.click("#plDemo"); await p.evaluate(() => { const d = document.getElementById("rsSec"); if (d) d.open = true; }); }
async function addCaseByKeyboard(p, ids, label) {
  for (const id of ids) { await p.focus(srcSel(id)); await p.keyboard.press("Space"); }
  let tabs = 0; for (; tabs < 40; tabs++) { await p.keyboard.press("Tab"); if ((await p.evaluate(() => document.activeElement.id)) === "rsLabel") break; }
  await p.keyboard.type(label); await p.keyboard.press("Enter");
  await p.waitForTimeout(50);
  return tabs + 1;
}
const records = (p) => p.evaluate(() => {
  const city = window.CITY_APP.state.city, cat = window.CITY_PLAN_UI.state.category;
  return window.CITY_EVIDENCE.cities[city].places.filter((x) => x.group === cat).map((x) => ({ id: x.id, qa: window.CITY_APP.ui.qaOf(x).length }));
});

async function desktop(browser) {
  const { p, ctx, errors } = await open(browser);
  await setup(p);
  let s = await rs(p);
  const recs = await records(p);
  const note = await p.textContent("#rsNote");
  const names = await p.evaluate(() => [...document.querySelectorAll("#rsSources li label")].map((l) => l.textContent));
  check("RS1", "selector", "the panel lists the real source records of the plan category (names, source, QA marks) and says «Условно исключаем … не подтверждение закрытия»",
    s.sources.length === recs.length && recs.length > 0 && names.every((t) => /·/.test(t)) && /Условно исключаем/.test(note) && /не подтверждение закрытия/.test(note) && /не означают отсутствие услуги/.test(note), { n: s.sources.length, recs: recs.length });
  await p.selectOption("#rsQa", "qa");
  const qaShown = (await rs(p)).sources.length, qaWant = recs.filter((r) => r.qa).length;
  await p.selectOption("#rsQa", "noqa");
  const noShown = (await rs(p)).sources.length;
  await p.selectOption("#rsQa", "all");
  check("RS2", "selector", "QA filter: «с QA-флагом» / «без QA-флага» show exactly the records with / without QA flags (QA does not exclude anything by itself)", qaShown === qaWant && noShown === recs.length - qaWant, { qaShown, qaWant, noShown });
  // keyboard: choose two records, un-choose one (delete a selected source), add the case with Enter
  const [r0, r1, r2] = recs.map((r) => r.id).sort();
  for (const id of [r0, r1, r2]) { await p.focus(srcSel(id)); await p.keyboard.press("Space"); }
  await p.focus(srcSel(r2)); await p.keyboard.press("Space");  // un-choose
  s = await rs(p);
  const unchoose = s.sel.length === 2 && !s.sel.includes(r2) && (await p.textContent("#rsSelCount")).startsWith("Выбрано 2");
  let tabs = 0; await p.focus(srcSel(r1)); for (; tabs < 40; tabs++) { await p.keyboard.press("Tab"); if ((await p.evaluate(() => document.activeElement.id)) === "rsLabel") break; }
  await p.keyboard.type("две записи"); await p.keyboard.press("Enter"); await p.waitForTimeout(50);
  s = await rs(p);
  check("RS3", "cases", "keyboard only: Space chooses / un-chooses records, Tab reaches «Название случая», Enter adds case C1 with the 2 chosen records; selection cleared, focus back on the name field",
    unchoose && s.cases.length === 1 && s.cases[0].id === "C1" && s.cases[0].ids.join() === [r0, r1].sort().join() && s.sel.length === 0 && s.focus === "rsLabel" && tabs < 40, { unchoose, cases: s.cases, focus: s.focus, tabs: tabs + 1 });
  await addCaseByKeyboard(p, [r0, r1], "то же самое");
  s = await rs(p);
  check("RS4", "cases", "a second case with the same records is allowed and marked «тот же набор, что C1»; the message says the result does not change", s.cases.length === 2 && (await p.locator('[data-rs-case="C2"] .pill').textContent()).includes("C1") && /совпадает со случаем C1/.test(s.msg), { cases: s.cases.map((c) => c.id), msg: s.msg });
  await p.focus("#rsDel_C2"); await p.keyboard.press("Enter"); await p.waitForTimeout(50);
  s = await rs(p);
  check("RS5", "cases", "deleting a case with the keyboard removes it and keeps the focus in the panel (previous «Удалить» or the name field)", s.cases.length === 1 && ["rsDel_C1", "rsLabel"].includes(s.focus), { cases: s.cases.map((c) => c.id), focus: s.focus });
  // all records of the category in one case → per-case nulls for plans without sites
  const all = recs.map((r) => r.id);
  for (const id of all) await p.check(srcSel(id));
  await p.fill("#rsLabel", "все записи категории"); await p.click("#rsAdd");
  // compare (slow) → focus on cancel, progress; result focus; numbers = engine
  await p.evaluate(() => { window.CITY_RESILIENCE_UI.state.runOpts = { chunk: 8, delayMs: 20 }; });
  await p.focus("#rsRun"); await p.keyboard.press("Enter");
  await p.waitForSelector("#rsProgress", { timeout: 5000 });
  await p.waitForTimeout(80);
  const mid = await rs(p);
  await p.waitForSelector("#rsResultTitle", { timeout: 30000 }); await p.waitForTimeout(50);
  s = await rs(p);
  const ref = await engineResult(p);
  const cards = await p.evaluate(() => Object.fromEntries([...document.querySelectorAll("[data-rs-plan]")].map((c) => [c.dataset.rsPlan, c.querySelector("dd").textContent])));
  const rows = await p.evaluate(() => [...document.querySelectorAll("#rsTable tbody tr")].map((r) => r.dataset.rsRow));
  check("RS7", "compare", "«Сравнить планы» (Enter): progress and focus on «Отменить сравнение» while running; at the end focus on the result heading; cards = engine (nominal, robust IDs), table rows base + cases",
    mid.running && mid.focus === "rsCancel" && s.result && s.result.status === "optimal" && s.focus === "rsResultTitle" && cards.nominal === (ref.nominal.length ? ref.nominal.join(", ") : "без новых объектов") &&
    cards.robust === (ref.robust.length ? ref.robust.join(", ") : "без новых объектов") && rows.join() === "base,C1,C3", { mid: { running: mid.running, focus: mid.focus }, focus: s.focus, cards, ref, rows });
  const price = await p.textContent("#rsPrice");
  check("RS7b", "compare", "the price of robustness is shown in metres of the base mean (or «совпадает … 0 м»), never as money or probability", /Цена устойчивости/.test(price) && /м/.test(price) && !/тенге|вероятн|риск/.test(price), price);
  // null messages: the «all records» case for the manual plan (no sites selected) has no distance
  const nullCell = await p.evaluate(() => { const r = document.querySelector('#rsTable tr[data-rs-row="C3"]'); return r && r.cells[1].textContent; });
  const manualW = await p.evaluate(() => { const c = document.querySelector('[data-rs-plan="manual"]'); return c && [...c.querySelectorAll("dd")].pop().textContent; });
  check("RS11", "null", "with every record excluded and no site in the manual plan, the cell says «нет данных: у N точ. …» and the worst-case line names the unknown points without a «сумма 0 м»",
    !!nullCell && /нет данных: у \d+ точ\./.test(nullCell) && !/ 0 м/.test(nullCell) && !!manualW && /без расстояния/.test(manualW) && !/сумма 0/.test(manualW), { nullCell, manualW });
  // apply robust → restore
  const before = (await rs(p)).selected;
  if (await p.isEnabled("#rsApply_robust")) { await p.focus("#rsApply_robust"); await p.keyboard.press("Enter"); }
  await p.waitForTimeout(50);
  const sA = await rs(p);
  await p.focus("#rsRestore"); await p.keyboard.press("Enter"); await p.waitForTimeout(50);
  const sR = await rs(p);
  check("RS10", "apply", "«Применить» (устойчивый) replaces the manual plan only on Enter/click; «Вернуть ручной план» restores it", JSON.stringify(sA.selected) === JSON.stringify(ref.robust.slice().sort()) && JSON.stringify(sR.selected) === JSON.stringify(before), { before, applied: sA.selected, restored: sR.selected });
  // number editing after the result → stale; Tab moves on (K3 of the keyboard patch)
  await p.evaluate(() => { for (const d of document.querySelectorAll("#planCard details")) d.open = true; });
  await p.focus("#plBudget"); await p.keyboard.press("Control+A"); await p.keyboard.type("700"); await p.keyboard.press("Tab"); await p.waitForTimeout(120);
  s = await rs(p);
  const applyDisabled = await p.isDisabled("#rsApply_robust").catch(() => true);
  check("RS9", "stale", "editing the budget after the comparison (type + Tab): focus moves on, the result is marked stale and «Применить» is disabled", s.stale && applyDisabled && s.focus !== "BODY", { stale: s.stale, applyDisabled, focus: s.focus });
  // change during a run → stopped, no late answer
  await p.click("#rsRun"); await p.waitForTimeout(80);
  await p.locator("#plBudget").fill("650"); await p.locator("#plBudget").press("Enter"); await p.waitForTimeout(1500);
  s = await rs(p);
  check("RS9b", "stale", "changing the budget while comparing stops the run («Условия изменены»); its answer never appears", !s.running && !s.result && /Условия изменены/.test(s.msg), { msg: s.msg, result: s.result });
  // cancel
  await p.click("#rsRun"); await p.waitForTimeout(80);
  await p.focus("#rsCancel"); await p.keyboard.press("Enter"); await p.waitForTimeout(800);
  s = await rs(p);
  check("RS8", "cancel", "«Отменить сравнение»: no result, message, focus back on «Сравнить планы», nothing arrives later", !s.running && !s.result && /отменено/.test(s.msg) && s.focus === "rsRun", { msg: s.msg, focus: s.focus });
  await p.evaluate(() => { window.CITY_RESILIENCE_UI.state.runOpts = { chunk: 256, delayMs: 0 }; });
  // focusable elements of the panel: a short list, no thousands of Tab stops; map placement keeps roads out of the Tab order
  const tabStops = await p.evaluate(() => [...document.querySelectorAll("#rsSec a, #rsSec button, #rsSec input, #rsSec select, #rsSec [tabindex]")].filter((e) => !e.disabled && e.tabIndex >= 0 && e.offsetParent !== null).length);
  check("RS16", "keyboard", "the panel adds a bounded number of Tab stops (≤ 2 × records + 20) and no map mode", tabStops <= 2 * recs.length + 20, { tabStops, records: recs.length });
  await p.screenshot({ path: path.join(SHOTS, "RS_1400_panel.png"), fullPage: false });
  // the 12-candidate limit: add sites on the map until 13
  await p.click("#plModeCands");
  await p.evaluate(() => document.querySelector(".mapwrap").scrollIntoView({ block: "start" }));
  const spots = await p.evaluate(() => { const sq = document.querySelector('#map rect[stroke-dasharray="6 4"]').getBoundingClientRect(), out = [];
    for (let y = Math.max(sq.top, 0) + 20; y < Math.min(sq.bottom, innerHeight) - 20 && out.length < 8; y += 47) for (let x = sq.left + 30; x < sq.right - 30 && out.length < 8; x += 61) {
      const e = document.elementFromPoint(x, y); if (e && e.closest("#map") && !e.closest("g[data-id],[data-plan-point],[data-plan-cand]") && e.tagName !== "text") out.push({ x, y }); } return out; });
  for (const q of spots.slice(0, 5)) await p.mouse.click(q.x, q.y);
  await p.keyboard.press("Escape");
  const nc = await p.evaluate(() => window.CITY_PLAN_UI.state.cands.length);
  const tooMany = await p.evaluate(() => (document.getElementById("rsTooMany") || {}).textContent || null);
  check("RS12", "limits", "13 candidates: the panel says too_many_candidates (nothing removed automatically) and «Сравнить» is disabled; v2 still has all 13", nc === 13 && !!tooMany && /too_many_candidates/.test(tooMany) && (await p.isDisabled("#rsRun")), { nc, tooMany });
  // category and city switches
  await p.selectOption("#plCat", "outpatient_clinic"); await p.waitForTimeout(50);
  s = await rs(p);
  const recC = await records(p);
  check("RS14", "reset", "category change: cases and result reset (no IDs carried), the selector now lists the other category", s.cases.length === 0 && !s.result && s.sources.length === recC.length && !s.sources.includes(r0), { cases: s.cases.length, sources: s.sources.length });
  await setup(p);
  await addCaseByKeyboard(p, [(await records(p))[0].id], "одна запись");
  const had = (await rs(p)).cases.length;
  await p.click('#citySeg button[data-city="astana"]'); await p.waitForTimeout(50);
  s = await rs(p);
  const recA = await records(p);
  check("RS13", "reset", "city switch: cases reset with a reason; the list shows Astana records; nothing from Shymkent is carried", had === 1 && s.city === "astana" && s.cases.length === 0 && /Город изменён/.test(s.msg) && s.sources.length === recA.length, { had, city: s.city, msg: s.msg, sources: s.sources.length });
  check("RS18", "general", "no console or page errors on the desktop path", errors.length === 0, errors);
  await ctx.close();
}

async function narrow(browser) {
  const { p, ctx, errors } = await open(browser, { width: 390, height: 844 });
  await setup(p);
  const recs = (await records(p)).map((r) => r.id).sort();
  await addCaseByKeyboard(p, recs.slice(0, 3), "три записи");
  for (const id of recs) await p.check(srcSel(id));
  await p.fill("#rsLabel", "все записи"); await p.click("#rsAdd");
  await p.click("#rsRun");
  await p.waitForSelector("#rsResultTitle", { timeout: 30000 });
  const fit = await p.evaluate(() => {
    const card = document.getElementById("planCard"), cr = card.getBoundingClientRect(), iw = innerWidth;
    const out = [...document.querySelectorAll("#rsSec button, #rsSec input, #rsSec select, #rsSec li, #rsSec p, #rsSec .pl-cmp, #rsSec .tablewrap")].filter((e) => e.getBoundingClientRect().width > 0)
      .filter((e) => { const r = e.getBoundingClientRect(); return r.right > cr.right + 1 || r.left < cr.left - 1; }).map((e) => e.tagName + "#" + (e.id || "") + ":" + e.textContent.slice(0, 20));
    const w = document.querySelector("#rsSec .tablewrap");
    return { pageScroll: document.documentElement.scrollWidth > iw, outside: out.slice(0, 8), tableScrolls: !!w && w.scrollWidth > w.clientWidth + 1,
      region: w && { role: w.getAttribute("role"), name: w.getAttribute("aria-label"), tabindex: w.getAttribute("tabindex") } };
  });
  check("RS17", "390px", "390 px: no horizontal page scroll, nothing sticks out of the plan card; the per-case table, if wider, scrolls inside a named, focusable region",
    !fit.pageScroll && fit.outside.length === 0 && (!fit.tableScrolls || (fit.region.role === "region" && !!fit.region.name && fit.region.tabindex === "0")), fit);
  const nullCell = await p.evaluate(() => { const r = [...document.querySelectorAll("#rsTable tbody tr")].pop(); return r && r.cells[1].textContent; });
  check("RS11b", "null", "390 px: the «все записи» row of the manual plan shows the null message (no distance), not 0", !!nullCell && /нет данных/.test(nullCell), nullCell);
  await p.locator("#rsCompare").scrollIntoViewIfNeeded();
  await p.screenshot({ path: path.join(SHOTS, "RS_390_compare.png") });
  check("RS18b", "general", "no console or page errors at 390 px", errors.length === 0, errors);
  await ctx.close();
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const { p, ctx } = await open(browser);
  const has = await p.evaluate(() => ({ panel: !!window.CITY_RESILIENCE_UI, engine: !!(window.CITY_RESILIENCE || window.CITY_RESILIENCE_K07), plan: !!(window.CITY_PLAN_UI && window.CITY_PLAN_UI.OPT) }));
  await ctx.close();
  if (!has.panel || !has.engine || !has.plan) check("P0", "precondition", "the page contains the K07 resilience panel (CITY_RESILIENCE_UI) and an engine (CITY_RESILIENCE or CITY_RESILIENCE_K07)", false, has, false);
  else { await desktop(browser); await narrow(browser); }
  await browser.close();
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K07 round-9 browser tests: resilience panel on the real BUILD page", label: OPT.label, sha: OPT.sha, app_root: path.basename(ROOT),
    total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"),
    note: "BUILD's SYNTHETIC demo plan on the real slices; source record IDs are real; exclusions are conditional assumptions, not closures.", checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} [${c.area}] ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 400)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  process.exitCode = out.fail.length || out.test_incompatible.length ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
