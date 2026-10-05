// K12 round 8, stage 2 (group U): the stale-result / cancel guard of a city-plan-v2 UI, checked in a real browser.
// For implementations whose guard is not an exported object (BUILD keeps it inside the plan-ui.js closure), the Node
// adapter cannot reach it, so stage2_runtime.cjs reports D2–D6 as SKIP; this file covers the same cases via the page API.
//   NODE_PATH="$(npm root -g)" node ui_gate_browser.cjs --app-root <copy of prototypes/city-evidence> [--out r.json]
// Opens <app-root>/web/index.html over file://, aborts every non-file request (and counts it), never writes into app-root.
// Page API used (BUILD plan-ui.js @ d865dd4): CITY_PLAN_UI.{importText,startSearch,cancelSearch,applyPlan,setNumber,opt,state},
// CITY_APP.switchCity. Fixture texts: fixtures_v2/V01, V03, V04, N03 with "__SNAPSHOT__" replaced by the page's own snapshot.
"use strict";
const fs = require("fs"), path = require("path");
const { pathToFileURL } = require("url");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const APP = path.resolve(opt("--app-root", ""));
const OUT = opt("--out");
const HERE = __dirname;
const INDEX = path.join(APP, "web", "index.html");
if (!fs.existsSync(INDEX)) { console.error("usage: node ui_gate_browser.cjs --app-root <dir>"); process.exit(2); }
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { console.log(JSON.stringify({ verdict: "SKIP", reason: "playwright not installed (set NODE_PATH)" })); process.exit(0); }
const IDX = JSON.parse(fs.readFileSync(path.join(HERE, "FIXTURES_V2_INDEX.json"), "utf8"));
const fx = (id) => fs.readFileSync(path.join(HERE, IDX.fixtures.find((f) => f.id === id).file), "utf8");

const results = [];
const check = (id, title, ok, detail) => { results.push({ id, title, status: ok ? "PASS" : "FAIL", detail: detail === undefined ? null : detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${id} ${title}${ok ? "" : " — " + JSON.stringify(detail).slice(0, 300)}`); };

(async () => {
  const browser = await chromium.launch(process.env.K12_CHROMIUM ? { executablePath: process.env.K12_CHROMIUM } : {});
  const page = await browser.newPage();
  const external = [], errors = [];
  await page.route("**/*", (route) => { const u = route.request().url();
    if (u.startsWith("file://") || u.startsWith("data:") || u.startsWith("blob:")) return route.continue();
    external.push(u); return route.abort(); });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(pathToFileURL(INDEX).href);
  await page.waitForFunction(() => window.CITY_PLAN_UI && window.CITY_PLAN && window.CITY_APP);
  const v2btn = await page.$('#toolSeg button[data-tool="v2"]');
  if (v2btn) await v2btn.click();
  const snap = await page.evaluate(() => ({ shymkent: CITY_PLAN.sourceSnapshot(CITY_EVIDENCE, "shymkent", CITY_APP.ui.F),
                                            astana: CITY_PLAN.sourceSnapshot(CITY_EVIDENCE, "astana", CITY_APP.ui.F) }));
  const sub = (t, city = "shymkent") => t.split('"__SNAPSHOT__"').join(JSON.stringify(snap[city])).split('"__SNAPSHOT_OTHER_CITY__"').join(JSON.stringify(snap[city === "shymkent" ? "astana" : "shymkent"]));
  const T = { V01: sub(fx("V01")), V03: sub(fx("V03")), V04: sub(fx("V04")), N03: sub(fx("N03")) };
  const S = () => page.evaluate(() => { const U = CITY_PLAN_UI; return { status: U.opt.status, hasResult: U.opt.result !== null && U.opt.result !== undefined,
    rid: U.opt.request_id, examined: U.opt.examined, total: U.opt.total, msg: U.state.msg, city: CITY_APP.state.city,
    // plan fields only (the message line is expected to change on a refusal)
    ps: JSON.stringify(["category", "points", "cands", "budget", "max_selected", "radius", "required", "excluded", "selected"].map((k) => U.state[k])) }; });
  const waitNotRunning = (ms = 20000) => page.waitForFunction(() => CITY_PLAN_UI.opt.status !== "running", null, { timeout: ms }).catch(() => null);
  const settle = (ms) => page.waitForTimeout(ms);

  // U1: atomic import refusals in the UI (17 candidates; forged derived_results) leave the editor state as it was
  const imp1 = await page.evaluate((t) => CITY_PLAN_UI.importText(t), T.V01);
  const s0 = await S();
  const r17 = await page.evaluate((t) => CITY_PLAN_UI.importText(t), T.N03);
  const s17 = await S();
  const r03 = await page.evaluate((t) => CITY_PLAN_UI.importText(t), T.V03);
  const s03 = await S();
  check("U1", "UI-импорт: 17 кандидатов и поддельные derived_results отклонены, состояние редактора прежнее",
    imp1 === true && r17 === false && r03 === false && s17.ps === s0.ps && s03.ps === s0.ps && s17.status === s0.status &&
    /не принят/.test(s17.msg) && /не принят/.test(s03.msg), { imp1, r17, r03, msg17: s17.msg.slice(0, 120), msg03: s03.msg.slice(0, 120) });

  // U2: a completed search, then a budget change: old optimum becomes stale, apply refused
  await page.evaluate((t) => CITY_PLAN_UI.importText(t), T.V04);           // 16 candidates, 65536 subsets per job
  await page.evaluate(() => CITY_PLAN_UI.startSearch());
  await waitNotRunning();
  const done = await page.evaluate(() => ({ st: CITY_PLAN_UI.opt.status, r: CITY_PLAN_UI.opt.result && { status: CITY_PLAN_UI.opt.result.status,
    evaluated: CITY_PLAN_UI.opt.result.evaluated, mean: CITY_PLAN_UI.opt.result.objectives && CITY_PLAN_UI.opt.result.objectives.mean.ids } }));
  const node = await page.evaluate(() => { const U = CITY_PLAN_UI, sc = CITY_PLAN.validatePlanScenario(U.rawScenario(), U.ctxOf(CITY_APP.state.city));
    const r = CITY_PLAN.optimizePlans(U.ctxOf(CITY_APP.state.city), sc, { F: CITY_APP.ui.F }); return { evaluated: r.evaluated, mean: r.objectives.mean.ids }; });
  check("U2a", "полный поиск в UI: done, все 65 536 наборов, «Среднее» = синхронному optimizePlans",
    done.st === "done" && done.r && done.r.status === "optimal" && done.r.evaluated === 65536 && JSON.stringify(done.r.mean) === JSON.stringify(node.mean), { done, node });
  await page.evaluate(() => CITY_PLAN_UI.setNumber("budget", String(CITY_PLAN_UI.state.budget - 1), 0, 1000000, (v) => { CITY_PLAN_UI.state.budget = v; }));
  const afterBudget = await S();
  const applied = await page.evaluate(() => CITY_PLAN_UI.applyPlan("mean"));
  check("U2b", "после смены бюджета прежний оптимум устарел (stale), применить нельзя", afterBudget.status === "stale" && !afterBudget.hasResult && applied === false,
    { status: afterBudget.status, applied });

  // U3: cancel mid-run: no partial result later
  const c = await page.evaluate(() => { const U = CITY_PLAN_UI; U.startSearch(); const running = U.opt.status === "running"; U.cancelSearch(); return { running, st: U.opt.status }; });
  await settle(1500);
  const c2 = await S();
  check("U3", "отмена посреди поиска: cancelled, результат не появился и позже", c.running && c.st === "cancelled" && c2.status === "cancelled" && !c2.hasResult, { c, c2: { status: c2.status, hasResult: c2.hasResult } });

  // U4: parameter change during the run: the answer of the old request is discarded
  await page.evaluate(() => CITY_PLAN_UI.startSearch());
  await settle(30);
  const mid = await S();
  await page.evaluate(() => CITY_PLAN_UI.setNumber("budget", String(CITY_PLAN_UI.state.budget - 1), 0, 1000000, (v) => { CITY_PLAN_UI.state.budget = v; }));
  await settle(2500);
  const u4 = await S();
  check("U4", "изменение бюджета во время поиска: ответ старого запроса отброшен (stale, без результата)",
    mid.status === "running" && u4.status === "stale" && !u4.hasResult, { mid: mid.status, examined: mid.examined, after: u4.status, hasResult: u4.hasResult });

  // U5: import of another scenario during the run: the old search is superseded, its answer never appears
  await page.evaluate((t) => CITY_PLAN_UI.importText(t), T.V04);
  await page.evaluate(() => CITY_PLAN_UI.startSearch());
  await settle(30);
  const ridBefore = (await S()).rid;
  const imp5 = await page.evaluate((t) => CITY_PLAN_UI.importText(t), T.V01);
  await settle(2500);
  const u5 = await S();
  check("U5", "импорт другого сценария во время поиска: старый поиск снят, его ответ не применён", imp5 === true && u5.rid > ridBefore && u5.status !== "done" && !u5.hasResult,
    { imp5, status: u5.status, hasResult: u5.hasResult });

  // U6: city switch during the run: reset, nothing from the old city is applied
  await page.evaluate((t) => CITY_PLAN_UI.importText(t), T.V04);
  await page.evaluate(() => CITY_PLAN_UI.startSearch());
  await settle(30);
  await page.evaluate(() => CITY_APP.switchCity("astana"));
  await settle(2500);
  const u6 = await page.evaluate(() => ({ status: CITY_PLAN_UI.opt.status, hasResult: !!CITY_PLAN_UI.opt.result, pts: CITY_PLAN_UI.state.points.length,
    cands: CITY_PLAN_UI.state.cands.length, city: CITY_APP.state.city }));
  check("U6", "смена города во время поиска: сценарий сброшен, старый ответ не применён", u6.city === "astana" && !u6.hasResult && u6.status !== "done" && u6.cands === 0, u6);
  await page.evaluate(() => CITY_APP.switchCity("shymkent"));

  // U7: the page stays responsive during a full search (timer gaps)
  await page.evaluate((t) => CITY_PLAN_UI.importText(t), T.V04);
  const gaps = await page.evaluate(() => new Promise((resolve) => {
    let last = performance.now(), maxGap = 0, ticks = 0;
    const iv = setInterval(() => { const now = performance.now(); maxGap = Math.max(maxGap, now - last); last = now; ticks++; }, 10);
    const t0 = performance.now();
    CITY_PLAN_UI.startSearch();
    const poll = () => { if (CITY_PLAN_UI.opt.status === "running") return setTimeout(poll, 20);
      clearInterval(iv); resolve({ maxGap: Math.round(maxGap), ticks, total_ms: Math.round(performance.now() - t0), status: CITY_PLAN_UI.opt.status }); };
    setTimeout(poll, 20);
  }));
  check("U7", "страница отвечает во время полного поиска (самый длинный разрыв таймера < 200 мс)", gaps.status === "done" && gaps.ticks > 0 && gaps.maxGap < 200, gaps);

  check("U8", "нет внешних запросов и ошибок страницы", external.length === 0 && errors.length === 0, { external: external.slice(0, 5), errors: errors.slice(0, 5) });
  await browser.close();
  const summary = { app_root: path.basename(APP), total: results.length, pass: results.filter((r) => r.status === "PASS").length,
    fail: results.filter((r) => r.status === "FAIL").map((r) => r.id), external_requests: external.length, verdict: results.every((r) => r.status === "PASS") ? "PASS" : "FAIL" };
  console.log(JSON.stringify(summary));
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 1) + "\n");
  process.exit(summary.verdict === "PASS" ? 0 : 1);
})().catch((e) => { console.error("ui_gate_browser error:", e && e.message); process.exit(3); });
