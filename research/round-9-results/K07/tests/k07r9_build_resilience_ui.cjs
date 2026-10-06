// K07 round 9: independent browser tests of the BUILD panel «Устойчивость к допущениям» (web/resilience-ui.js) on the real page.
// Usage: node k07r9_build_resilience_ui.cjs --app-root <BUILD extraction> [--label …] [--sha …] [--out …]
// Adapter to BUILD's DOM/API (#resCard, #rsAdd, #rsLabel_<case>, #rsX_<case>_<k> [data-rs-rec], #rsRun, #rsCancel, #rsCompare,
// #rsTable, #rsFile; window.CITY_RESILIENCE_UI.state). Desktop 1400 px and 390 px: number editing, choosing / un-choosing
// records, adding / deleting cases (keyboard), compare / cancel / stale, apply / restore, null and infeasible messages,
// the 12-candidate limit, import refusal, city and category switches; races of a typed value + an immediate click / a
// human-speed (100 ms) click / a touch tap (BR18–BR25, BRT1–BRT3). Plans in the page are compared with the independent
// K07 Python oracle (tests/oracle_resilience.py). Instrumentation (documented): for cancel/stale tests setTimeout in the page
// is slowed to ≥ 40 ms so that a 4096-subset run can be interrupted; nothing else is changed in the page.
// Data: BUILD's SYNTHETIC demo plan and K07 SYNTHETIC files (points/sites/costs invented) on the real slices.
const path = require("path"), fs = require("fs"), vm = require("vm"), { spawnSync } = require("child_process"), { pathToFileURL } = require("url");
const { chromium } = require("playwright");
const HERE = __dirname, K = path.join(HERE, ".."), R8 = path.join(K, "..", "..", "round-8-results", "K07");
const a = process.argv.slice(2), OPT = { label: "build_res", sha: null, out: null, appRoot: null };
for (let i = 0; i < a.length; i++) { const k = a[i], v = a[i + 1]; if (k === "--app-root") { OPT.appRoot = v; i++; } else if (k === "--label") { OPT.label = v; i++; } else if (k === "--sha") { OPT.sha = v; i++; } else if (k === "--out") { OPT.out = v; i++; } else { console.error("unknown argument " + k); process.exit(2); } }
const ROOT = path.resolve(OPT.appRoot), WEB = fs.existsSync(path.join(ROOT, "web")) ? path.join(ROOT, "web") : ROOT;
const URL_ = pathToFileURL(path.join(WEB, "index.html")).href;
const OUT = path.resolve(OPT.out || path.join(K, "results", OPT.label)), SHOTS = path.join(OUT, "screenshots");
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
const st = (p) => p.evaluate(() => {
  const S = window.CITY_RESILIENCE_UI.state, PS = window.CITY_PLAN_UI.state;
  return { cases: S.cases.map((c) => ({ id: c.id, label: c.label, ids: [...c.ids].sort() })), status: S.status, result: S.result && { status: S.result.status, nominal: S.result.nominal && S.result.nominal.selected_ids, robust: S.result.robust && S.result.robust.selected_ids, price: S.result.price_of_robustness_m },
    msg: (document.getElementById("rsMsg") || {}).textContent || "", selected: PS.selected.slice().sort(), city: window.CITY_APP.state.city, category: PS.category, cands: PS.cands.length,
    focus: document.activeElement.id || document.activeElement.tagName, body: document.activeElement === document.body };
});
const tick = (p, ms = 120) => p.waitForTimeout(ms);
async function setup(p) { await p.click('#toolSeg button[data-tool="v2"]'); await p.click("#plDemo"); await tick(p); }
async function openSections(p) {
  await tick(p, 80);
  for (let i = 0; i < 20; i++) { const sm = p.locator("#planCard details:not([open]) > summary, #resCard details:not([open]) > summary").first(); if (!(await sm.count())) break; await sm.click(); }
}
const recordsOf = (p, c) => p.evaluate((c) => [...document.querySelectorAll(`#rsCase_${c} input[data-rs-rec]`)].map((x) => ({ id: x.id, rec: x.dataset.rsRec })), c);
async function slow(p) { await p.evaluate(() => { if (window.__k07slow) return; window.__k07slow = 1; const o = window.setTimeout; window.setTimeout = (f, d, ...r) => o(f, Math.max(d || 0, 40), ...r); }); }
async function importText(p, name, text) { await p.setInputFiles("#rsFile", { name, mimeType: "application/json", buffer: Buffer.from(text, "utf8") }); await tick(p, 200); }
function oracle(envelope, dataJs) {
  const dir = fs.mkdtempSync(path.join(OUT, "oracle-")), cf = path.join(dir, "cases.json"), of = path.join(dir, "oracle.json");
  fs.writeFileSync(cf, JSON.stringify([{ name: "page", envelope }]));
  const py = spawnSync("python3", [path.join(HERE, "oracle_resilience.py"), "--data", dataJs, "--cases", cf, "--out", of], { encoding: "utf8" });
  if (py.status !== 0) return null;
  const r = JSON.parse(fs.readFileSync(of, "utf8"))[0]; fs.rmSync(dir, { recursive: true, force: true }); return r;
}

async function desktop(browser) {
  const { p, ctx, errors } = await open(browser);
  await setup(p);
  const notice = await p.textContent("#rsNotice");
  const nRec = await p.evaluate(() => window.CITY_RESILIENCE_UI.sources().length);
  // keyboard: add a case, name it, Tab on
  await p.focus("#rsAdd"); await p.keyboard.press("Enter"); await tick(p);
  let s = await st(p);
  const afterAdd = s.focus;
  await p.keyboard.press("Control+A"); await p.keyboard.type("две записи"); await p.keyboard.press("Tab"); await tick(p);
  s = await st(p);
  const recs = await recordsOf(p, "c1");
  check("BR1", "path", "v2 shows the panel with «Условно исключаем из расчёта; это не подтверждение закрытия»; a case lists all real records of the category (one checkbox each)",
    /Условно исключаем из расчёта/.test(notice) && /не подтверждение закрытия/.test(notice) && recs.length === nRec && nRec > 0, { notice: notice.slice(0, 80), recs: recs.length, nRec });
  check("BR2", "keyboard", "«Добавить случай» with Enter: case c1, focus on its name field; typing a name + Tab applies it and moves the focus on (not <body>)",
    afterAdd === "rsLabel_c1" && s.cases[0] && s.cases[0].label === "две записи" && !s.body, { afterAdd, label: s.cases[0] && s.cases[0].label, focus: s.focus });
  // choose three records by keyboard, un-choose one
  for (const r of recs.slice(0, 3)) { await p.focus("#" + r.id); await p.keyboard.press("Space"); await tick(p, 60); }
  await p.focus("#" + recs[2].id); await p.keyboard.press("Space"); await tick(p);
  s = await st(p);
  const sum = await p.textContent("#rsCase_c1_sum");
  check("BR3", "keyboard", "Space chooses / un-chooses records of the case; the case summary shows «исключено 2 из N»", s.cases[0].ids.length === 2 && !s.cases[0].ids.includes(recs[2].rec) && new RegExp(`исключено 2 из ${nRec}`).test(sum), { ids: s.cases[0].ids.length, sum });
  // duplicate case and deletion by keyboard
  await p.focus("#rsAdd"); await p.keyboard.press("Enter"); await tick(p);
  const recs2 = await recordsOf(p, "c2");
  for (const r of recs2.slice(0, 2)) await p.check("#" + r.id);
  await tick(p);
  const dup = await p.evaluate(() => (document.getElementById("rsDup") || {}).textContent || null);
  check("BR4", "cases", "a second case with the same records is allowed and named as a duplicate (c1 = c2)", !!dup && /c1 = c2/.test(dup), dup);
  await p.focus("#rsDel_c2"); await p.keyboard.press("Enter"); await tick(p);
  s = await st(p);
  check("BR5", "keyboard", "«Удалить случай» with Enter removes it; the focus stays in the panel (previous «Удалить» or «Добавить случай»)", s.cases.length === 1 && ["rsDel_c1", "rsAdd"].includes(s.focus), { cases: s.cases.length, focus: s.focus });
  // a case with all records (null for plans without sites)
  await p.focus("#rsAdd"); await p.keyboard.press("Enter"); await tick(p);
  await p.keyboard.press("Control+A"); await p.keyboard.type("все записи категории"); await p.keyboard.press("Tab"); await tick(p);
  for (const r of await recordsOf(p, "c3")) await p.check("#" + r.id);
  await tick(p);
  // run with the keyboard; compare with the independent oracle
  await p.focus("#rsRun"); await p.keyboard.press("Enter");
  const fRun = await st(p);
  await p.waitForFunction(() => window.CITY_RESILIENCE_UI.state.status === "done", null, { timeout: 30000 }); await tick(p);
  s = await st(p);
  const envelope = await p.evaluate(() => window.CITY_RESILIENCE_UI.envelope());
  const o = oracle(envelope, path.join(WEB, "data.js"));
  const cards = await p.evaluate(() => Object.fromEntries([...document.querySelectorAll("#rsCompare [data-rs-plan]")].map((c) => [c.dataset.rsPlan, c.querySelector("dd").textContent])));
  const txt = (ids) => (ids.length ? ids.join(", ") : "без новых объектов");
  check("BR6", "compare", "«Сравнить» with Enter: focus stays in the panel while running and after; cards Ручной/Обычный/Устойчивый = the independent K07 oracle (plan IDs, price)",
    !fRun.body && !s.body && !!o && s.result && s.result.nominal.join() === o.nominal.selected_ids.join() && s.result.robust.join() === o.robust.selected_ids.join() &&
    cards.nominal === txt(o.nominal.selected_ids) && cards.robust === txt(o.robust.selected_ids) && Math.abs((s.result.price ?? NaN) - (o.price_of_robustness_m ?? NaN)) < 1e-9,
    { focusRun: fRun.focus, focusDone: s.focus, page: s.result, oracle: o && { nominal: o.nominal.selected_ids, robust: o.robust.selected_ids, price: o.price_of_robustness_m }, cards });
  const nullCell = await p.evaluate(() => { const r = document.querySelector('#rsTable tr[data-rs-case="c3"]'); return r && r.cells[1].textContent; });
  const manualWorst = await p.evaluate(() => { const c = document.querySelector('#rsCompare [data-rs-plan="manual"]'); return c && [...c.querySelectorAll("dd")].map((d) => d.textContent).join(" | "); });
  check("BR7", "null", "every record excluded and no site in the manual plan: the table shows «нет данных» / «без расстояния: N», the worst outcome says «среднее не определено» (no 0 m)",
    !!nullCell && /нет данных/.test(nullCell) && /без расстояния: \d+/.test(nullCell) && /среднее не определено/.test(manualWorst || "") && !/среднее 0 м/.test(manualWorst || ""), { nullCell, manualWorst });
  // apply / restore
  const before = s.selected;
  await p.focus("#rsApply_robust"); await p.keyboard.press("Enter"); await tick(p);
  const sA = await st(p);
  await p.focus("#rsRestore"); await p.keyboard.press("Enter"); await tick(p);
  const sR = await st(p);
  check("BR11", "apply", "«Применить» (устойчивый) replaces the manual plan only on Enter; «Вернуть ручной план» restores it; focus not lost", JSON.stringify(sA.selected) === JSON.stringify(o.robust.selected_ids.slice().sort()) && JSON.stringify(sR.selected) === JSON.stringify(before) && !sA.body && !sR.body,
    { applied: sA.selected, restored: sR.selected, focus: [sA.focus, sR.focus] });
  // number editing after the result → stale
  await openSections(p);
  await p.focus("#plW_P1"); await p.keyboard.press("Control+A"); await p.keyboard.type("9"); await p.keyboard.press("Tab"); await tick(p, 200);
  s = await st(p);
  check("BR9", "stale", "editing a weight (type + Tab) after the comparison: focus moves on, the comparison is marked out of date, «Применить» disappears", s.status === "stale" && !s.result && /устарел/.test(s.msg) && !s.body && (await p.locator("#rsApply_robust").count()) === 0, { status: s.status, msg: s.msg, focus: s.focus });
  // infeasible: a required site costing more than the budget
  await p.selectOption("#plS_K1", "required"); await p.locator("#plBudget").fill("50"); await p.locator("#plBudget").press("Enter"); await tick(p, 200);
  await p.click("#rsRun"); await p.waitForFunction(() => ["done", "stale"].includes(window.CITY_RESILIENCE_UI.state.status), null, { timeout: 30000 }); await tick(p);
  s = await st(p);
  const robustCard = await p.locator('#rsCompare [data-rs-plan="robust"]').count();
  check("BR8", "null", "required site cost > budget: «Нет допустимых планов» with the reason; no Обычный/Устойчивый cards, no price", /Нет допустимых планов/.test(s.msg) && /50/.test(s.msg) && robustCard === 0 && (await p.locator("#rsPrice").count()) === 0, { msg: s.msg, robustCard });
  await p.selectOption("#plS_K1", "free"); await p.locator("#plBudget").fill("600"); await p.locator("#plBudget").press("Enter"); await tick(p, 200);
  // import refusal: a file with derived results is refused, state unchanged
  const before2 = JSON.stringify(await st(p));
  const forged = JSON.stringify({ ...envelope, derived_results: { robust: { selected_ids: [] } } });
  await importText(p, "forged.json", forged);
  const sF = await st(p);
  check("BR17", "import", "a resilience file with derived results is refused («не принят»), the current plan and cases stay unchanged", /не принят/.test(sF.msg) && JSON.stringify({ ...sF, msg: "", focus: "" }) === JSON.stringify({ ...JSON.parse(before2), msg: "", focus: "" }), { msg: sF.msg });
  // cancel and stale during a run on a 12-site plan (K07 SYNTHETIC file), with setTimeout slowed to ≥ 40 ms
  const { realEnvelopes } = require(path.join(HERE, "resilience_cases.cjs"));
  const F = require(path.join(WEB, "facts.js")), PL = require(path.join(WEB, "plan.js"));
  const box = {}; vm.createContext(box); box.window = box; vm.runInContext(fs.readFileSync(path.join(WEB, "data.js"), "utf8"), box);
  const big = realEnvelopes(PL, box.CITY_EVIDENCE, F, R8).find((c) => c.name === "shymkent/school/max_12x25x8").envelope;
  await importText(p, "k07_12x25x8.json", JSON.stringify(big));
  s = await st(p);
  const loaded = s.cases.length === 7 && s.cands === 12;
  await slow(p);
  await p.click("#rsRun"); await tick(p, 150);
  const mid = await st(p);
  await p.focus("#rsCancel"); await p.keyboard.press("Enter"); await tick(p, 1500);
  s = await st(p);
  check("BR10", "cancel", "12 sites × 7 cases: «Отменить» stops the run, no result arrives later, message «отменено», focus not lost", loaded && mid.status === "running" && s.status === "cancelled" && !s.result && /отменено/.test(s.msg) && !s.body, { loaded, mid: mid.status, status: s.status, msg: s.msg, focus: s.focus }, loaded);
  await openSections(p);  // before the run: opening sections takes time and the run must still be going at the change
  await p.click("#rsRun"); await tick(p, 150);
  const mid2 = await st(p);
  await p.locator("#plBudget").fill("390"); await p.locator("#plBudget").press("Enter");
  const atChange = await st(p);
  await tick(p, 1500);
  s = await st(p);
  check("BR10b", "stale", "changing the budget while comparing stops the run («поиск остановлен»); its answer never appears", mid2.status === "running" && s.status === "stale" && !s.result && /остановлен/.test(s.msg), { mid: mid2.status, atChange: atChange.status, status: s.status, msg: s.msg }, mid2.status === "running" && atChange.status === "running");
  // bounded Tab stops in the panel (no map mode; records only inside opened cases)
  const stops = await p.evaluate(() => [...document.querySelectorAll("#resCard button, #resCard input, #resCard select, #resCard summary, #resCard [tabindex]")].filter((e) => !e.disabled && e.tabIndex >= 0 && e.getClientRects().length).length);
  const nr = await p.evaluate(() => window.CITY_RESILIENCE_UI.sources().length);
  check("BR14", "keyboard", "the panel's Tab stops stay bounded (≤ 7 cases × (records + 4) + 20); no map mode", stops <= 7 * (nr + 4) + 20, { stops, records: nr });
  await p.screenshot({ path: path.join(SHOTS, "BR_1400_panel.png") });
  // limit: a 13th site
  await p.click("#plModeCands");
  await p.evaluate(() => document.querySelector(".mapwrap").scrollIntoView({ block: "start" }));
  const spot = await p.evaluate(() => { const sq = document.querySelector('#map rect[stroke-dasharray="6 4"]').getBoundingClientRect();
    for (let y = Math.max(sq.top, 0) + 30; y < Math.min(sq.bottom, innerHeight) - 30; y += 37) for (let x = sq.left + 30; x < sq.right - 30; x += 41) { const e = document.elementFromPoint(x, y); if (e && e.closest("#map") && !e.closest("g[data-id],[data-plan-point],[data-plan-cand]") && e.tagName !== "text") return { x, y }; } return null; });
  if (spot) await p.mouse.click(spot.x, spot.y);
  await p.keyboard.press("Escape"); await tick(p);
  s = await st(p);
  const lim = await p.evaluate(() => (document.getElementById("rsLimit") || {}).textContent || null);
  check("BR12", "limits", "13 sites: the panel names the 12-site limit, nothing is removed automatically, «Сравнить» disabled", s.cands === 13 && !!lim && /12/.test(lim) && (await p.isDisabled("#rsRun")), { cands: s.cands, lim });
  // category and city switches
  await p.selectOption("#plCat", "outpatient_clinic"); await tick(p);
  s = await st(p);
  check("BR13a", "reset", "category change resets the cases (no IDs carried) with a reason", s.cases.length === 0 && s.category === "outpatient_clinic" && /сброшены/.test(s.msg), { cases: s.cases.length, msg: s.msg });
  await p.click("#rsAdd"); await tick(p);
  await p.click('#citySeg button[data-city="astana"]'); await tick(p);
  s = await st(p);
  check("BR13b", "reset", "city switch resets the cases with a reason (nothing carried to Astana)", s.city === "astana" && s.cases.length === 0 && /Город изменён/.test(s.msg), { city: s.city, cases: s.cases.length, msg: s.msg });
  check("BR16", "general", "no console or page errors on the desktop path", errors.length === 0, errors);
  await ctx.close();
}

// typed value + an immediate click (no Tab, no Enter): edits are applied on the next turn (r8 K3), so every action must see
// the typed value first. BUILD e82214e fixed this for «Найти» / «Сравнить» / apply / export; these checks are independent.
async function races(browser) {
  const { p, ctx, errors } = await open(browser);
  await setup(p);
  await p.click("#rsAdd"); await tick(p);
  await p.check("#" + (await recordsOf(p, "c1"))[0].id); await tick(p);
  await p.fill("#rsLabel_c1", "метка без Tab"); await p.click("#rsRun");
  await p.waitForFunction(() => window.CITY_RESILIENCE_UI.state.status !== "running", null, { timeout: 30000 }); await tick(p);
  let s = await st(p), e = await p.evaluate(() => window.CITY_RESILIENCE_UI.envelope());
  check("BR18", "race", "case name typed + immediate «Сравнить»: the run uses the typed name and finishes (not «устарело»)", s.status === "done" && s.cases[0].label === "метка без Tab" && e.cases[0].label === "метка без Tab", { status: s.status, label: s.cases[0].label, env: e.cases[0].label, msg: s.msg });
  await openSections(p);
  await p.fill("#plBudget", "777"); await p.click("#rsRun");
  await p.waitForFunction(() => window.CITY_RESILIENCE_UI.state.status !== "running", null, { timeout: 30000 }); await tick(p);
  s = await st(p); e = await p.evaluate(() => window.CITY_RESILIENCE_UI.envelope());
  check("BR19", "race", "budget typed + immediate «Сравнить»: the comparison uses the typed budget and is not stale", s.status === "done" && e.plan.budget === 777 && (await p.evaluate(() => window.CITY_PLAN_UI.state.budget)) === 777, { status: s.status, budget: e.plan.budget, msg: s.msg });
  await p.fill("#plBudget", "650"); await p.click("#plRun");
  await p.waitForFunction(() => window.CITY_PLAN_UI.opt.status !== "running", null, { timeout: 30000 }); await tick(p);
  const o = await p.evaluate(() => { const O = window.CITY_PLAN_UI.opt; return { status: O.status, budget: O.result && O.result.budget, state: window.CITY_PLAN_UI.state.budget }; });
  check("BR23", "race", "planner: budget typed + immediate «Найти точные оптимумы»: the search uses the typed budget and finishes", o.status === "done" && o.budget === 650 && o.state === 650, o);
  // human-speed click: Playwright's click sends mousedown and mouseup back to back; a person holds the button ~100 ms, and the
  // change (blur at mousedown) may re-render the card in between, replacing the button under the pointer
  const human = async (sel) => { await p.locator(sel).scrollIntoViewIfNeeded(); const b = await p.locator(sel).boundingBox(); await p.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await p.mouse.down(); await tick(p, 100); await p.mouse.up(); };
  await p.fill("#plBudget", "660"); await human("#plRun"); await tick(p, 80);
  await p.waitForFunction(() => window.CITY_PLAN_UI.opt.status !== "running", null, { timeout: 30000 }); await tick(p);
  const oh = await p.evaluate(() => { const O = window.CITY_PLAN_UI.opt; return { status: O.status, budget: O.result && O.result.budget, state: window.CITY_PLAN_UI.state.budget }; });
  check("BR24", "race", "planner: budget typed + a human-speed click (100 ms press) on «Найти точные оптимумы» starts the search with the typed budget (the click is not lost)", oh.status === "done" && oh.budget === 660 && oh.state === 660, oh);
  await p.fill("#rsLabel_c1", "человеческий клик"); await human("#rsRun"); await tick(p, 80);
  await p.waitForFunction(() => window.CITY_RESILIENCE_UI.state.status !== "running", null, { timeout: 30000 }); await tick(p);
  s = await st(p);
  check("BR25", "race", "case name typed + a human-speed click (100 ms press) on «Сравнить» starts the comparison (the click is not lost)", s.status === "done" && s.cases[0].label === "человеческий клик", { status: s.status, label: s.cases[0].label, msg: s.msg });
  await p.click("#rsAdd"); await tick(p);
  await p.fill("#rsLabel_c2", "сразу удалить"); await p.click("#rsDel_c2"); await tick(p, 200);
  s = await st(p);
  check("BR20", "race", "case name typed + immediate «Удалить случай»: the case is gone, no error message about the name, focus not lost", s.cases.length === 1 && s.cases[0].id === "c1" && !/Название случая/.test(s.msg) && !s.body, { cases: s.cases.map((c) => c.id), msg: s.msg, focus: s.focus });
  await p.fill("#plC_K1", "0"); await p.click('#citySeg button[data-city="astana"]'); await tick(p, 200);
  s = await st(p);
  const planMsg = await p.evaluate(() => window.CITY_PLAN_UI.state.msg);
  check("BR21", "race", "invalid cost typed + immediate city switch: Astana gets no Shymkent sites or cases, no page error (observed: plan message after the switch)", s.city === "astana" && s.cands === 0 && s.cases.length === 0 && errors.length === 0, { city: s.city, cands: s.cands, cases: s.cases.length, planMsg, errors });
  check("BR21b", "race", "after that switch the plan message gives the city-reset reason, not a refusal about the old city's site K1", /Город изменён/.test(planMsg) && !/K1/.test(planMsg), { planMsg });
  check("BR22", "general", "no console or page errors on the race path", errors.length === 0, errors);
  await ctx.close();
}

// touch (390 px, hasTouch): a tap synthesizes mousedown/mouseup/click at once after touchend
async function touch(browser) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }), p = await ctx.newPage(), errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  await p.goto(URL_); await p.waitForSelector("#map g[data-id]", { timeout: 15000 });
  await p.tap('#toolSeg button[data-tool="v2"]'); await p.tap("#plDemo"); await tick(p, 150);
  for (let i = 0; i < 20; i++) { const sm = p.locator("#planCard details:not([open]) > summary").first(); if (!(await sm.count())) break; await sm.tap(); await tick(p, 60); }
  await p.fill("#plBudget", "670"); await p.locator("#plRun").scrollIntoViewIfNeeded(); await p.tap("#plRun"); await tick(p, 80);
  await p.waitForFunction(() => window.CITY_PLAN_UI.opt.status !== "running", null, { timeout: 30000 }); await tick(p);
  const o = await p.evaluate(() => { const O = window.CITY_PLAN_UI.opt; return { status: O.status, budget: O.result && O.result.budget }; });
  check("BRT1", "touch", "390 px touch: budget typed + tap «Найти точные оптимумы» runs the search with the typed budget", o.status === "done" && o.budget === 670, o);
  await p.fill("#plC_K1", "0"); await p.locator('#citySeg button[data-city="astana"]').scrollIntoViewIfNeeded(); await p.tap('#citySeg button[data-city="astana"]'); await tick(p, 300);
  const t = await p.evaluate(() => ({ city: window.CITY_APP.state.city, cands: window.CITY_PLAN_UI.state.cands.length, msg: window.CITY_PLAN_UI.state.msg }));
  check("BRT2", "touch", "390 px touch: invalid cost typed + tap «Астана»: no sites carried, the message gives the city-reset reason (not a refusal about Shymkent's K1)", t.city === "astana" && t.cands === 0 && /Город изменён/.test(t.msg) && !/K1/.test(t.msg), t);
  check("BRT3", "general", "no page errors on the touch path", errors.length === 0, errors);
  await ctx.close();
}

async function narrow(browser) {
  const { p, ctx, errors } = await open(browser, { width: 390, height: 844 });
  await setup(p);
  await openSections(p);
  await p.focus("#plW_P1"); await p.keyboard.press("Control+A"); await p.keyboard.type("7"); await p.keyboard.press("Tab"); await tick(p, 200);
  const w = await p.evaluate(() => ({ w: window.CITY_PLAN_UI.state.points.find((x) => x.id === "P1").weight, focus: document.activeElement.id || document.activeElement.tagName }));
  check("BRN1", "390px", "390 px: typing a weight and Tab applies it and moves the focus on (not <body>)", w.w === 7 && w.focus !== "BODY" && w.focus !== "plW_P1", w);
  await p.click("#rsAdd"); await tick(p);
  const recs = await recordsOf(p, "c1");
  for (const r of recs) await p.check("#" + r.id);
  await p.uncheck("#" + recs[0].id); await tick(p);
  await p.click("#rsAdd"); await tick(p);
  await p.check("#" + (await recordsOf(p, "c2"))[0].id); await tick(p);
  await p.focus("#rsDel_c2"); await p.keyboard.press("Enter"); await tick(p);
  let s = await st(p);
  check("BRN2", "390px", "390 px: un-choosing a record and deleting a case work; the focus stays in the panel", s.cases.length === 1 && s.cases[0].ids.length === recs.length - 1 && ["rsDel_c1", "rsAdd"].includes(s.focus), { cases: s.cases.length, ids: s.cases[0] && s.cases[0].ids.length, focus: s.focus });
  await p.click("#rsRun");
  await p.waitForFunction(() => window.CITY_RESILIENCE_UI.state.status === "done", null, { timeout: 30000 }); await tick(p);
  const fit = await p.evaluate(() => {
    const card = document.getElementById("resCard"), cr = card.getBoundingClientRect(), iw = innerWidth;
    const out = [...card.querySelectorAll("button, input, select, p, .pl-cmp, .tablewrap, summary")].filter((e) => e.getBoundingClientRect().width > 0)
      .filter((e) => { const r = e.getBoundingClientRect(); return r.right > cr.right + 1 || r.left < cr.left - 1; }).map((e) => e.tagName + "#" + (e.id || "") + ":" + e.textContent.slice(0, 20));
    const w = document.getElementById("rsTable") && document.getElementById("rsTable").closest(".tablewrap");
    const clipped = [...document.querySelectorAll("#rsTable td")].filter((td) => getComputedStyle(td).textOverflow === "ellipsis").length;
    return { pageScroll: document.documentElement.scrollWidth > iw, outside: out.slice(0, 8), tableScrolls: !!w && w.scrollWidth > w.clientWidth + 1, clipped,
      region: w && { role: w.getAttribute("role"), name: w.getAttribute("aria-label"), tabindex: w.getAttribute("tabindex") } };
  });
  check("BRN3", "390px", "390 px: no horizontal page scroll; nothing sticks out of the panel; the per-case table loses no data (no ellipsis; any overflow scrolls inside its container)", !fit.pageScroll && fit.outside.length === 0 && fit.clipped === 0, fit);
  // N2-style: if the per-case table scrolls, it must be reachable from the keyboard
  let reach = null;
  if (fit.tableScrolls) {
    await p.focus("#rsRun"); let n = 0, ok = false;
    for (; n < 60; n++) { await p.keyboard.press("Tab"); ok = await p.evaluate(() => { const w = document.getElementById("rsTable").closest(".tablewrap"); return document.activeElement === w || w.contains(document.activeElement); }); if (ok) break; }
    reach = { reached: ok, tabs: n + 1 };
  }
  check("BRN4", "390px", "390 px: a scrolling per-case table is reachable with Tab (Chromium focuses scrollers); advisory: role/name/tabindex for other browsers", !fit.tableScrolls || (reach && reach.reached), { tableScrolls: fit.tableScrolls, reach, region: fit.region });
  await p.locator("#rsCompare").scrollIntoViewIfNeeded();
  await p.screenshot({ path: path.join(SHOTS, "BR_390_compare.png") });
  await p.click('#citySeg button[data-city="astana"]'); await tick(p);
  s = await st(p);
  check("BRN5", "390px", "390 px: city switch resets the cases with a reason", s.city === "astana" && s.cases.length === 0 && /Город изменён/.test(s.msg), { msg: s.msg });
  check("BRN6", "general", "no console or page errors at 390 px", errors.length === 0, errors);
  await ctx.close();
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const { p, ctx } = await open(browser);
  const has = await p.evaluate(() => ({ ui: !!(window.CITY_RESILIENCE_UI && window.CITY_RESILIENCE_UI.state && window.CITY_RESILIENCE_UI.sources), engine: !!window.CITY_RESILIENCE, card: !!document.getElementById("resCard") }));
  await ctx.close();
  if (!has.ui || !has.engine || !has.card) check("P0", "precondition", "the build contains the BUILD resilience panel (CITY_RESILIENCE_UI.state/sources, CITY_RESILIENCE, #resCard)", false, has, false);
  else { await desktop(browser); await races(browser); await touch(browser); await narrow(browser); }
  await browser.close();
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K07 round-9 independent browser tests of the BUILD resilience panel", label: OPT.label, sha: OPT.sha, app_root: path.basename(ROOT),
    total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"),
    note: "SYNTHETIC plans (BUILD demo, K07 files) on the real slices; record IDs are real; exclusions are conditional assumptions, not closures. setTimeout slowed to ≥ 40 ms only for the cancel/stale checks.", checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} [${c.area}] ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 500)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  process.exitCode = out.fail.length || out.test_incompatible.length ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
