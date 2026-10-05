// Browser test of «Несколько объектов (v2)» (round 8) via file:// — real mouse / keyboard, both cities.
// Usage:  NODE_PATH="$(npm root -g)" node tests/plan_smoke.cjs [outdir]   (outdir default: tests/out)
const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
const { pathToFileURL } = require("url");
const APP = path.resolve(__dirname, "..");
const out = path.resolve(process.argv[2] || path.join(APP, "tests", "out"));
fs.mkdirSync(out, { recursive: true });
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? " — " + String(detail).slice(0, 300) : "")); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", (r) => { if (!r.url().startsWith("file://") && !r.url().startsWith("blob:") && !r.url().startsWith("data:")) requests.push(r.url()); });
  await page.goto(pathToFileURL(path.join(APP, "web", "index.html")).href);
  await page.waitForSelector("#toolSeg");
  const at = async (fx, fy) => {
    const box = await page.$eval("#map", (e) => { e.scrollIntoView({ block: "nearest" }); const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
    await page.mouse.click(box.x + box.w * fx, box.y + box.h * fy);
  };
  const S = () => page.evaluate(() => {
    const U = CITY_PLAN_UI; let ev = null; try { ev = U.evaluate(); } catch (e) { ev = { error: String(e) }; }
    return { ps: JSON.parse(JSON.stringify(U.state)), ev, msg: (document.getElementById("plMsg") || {}).textContent || "", tool: CITY_APP.state.tool,
      tbl: document.querySelectorAll("#tbl tr").length, markers: document.querySelectorAll("#map g[data-id]").length,
      slice: document.getElementById("sliceBody").textContent, planHidden: document.getElementById("planCard").hidden, v1Hidden: document.getElementById("whatifCard").hidden,
      rows: document.querySelectorAll("#plRows tr[data-plan-row]").length, feas: (document.getElementById("plFeasible") || {}).textContent || "" };
  });

  // ---------- stage 1: editor, manual plan ----------
  check("v1 card shown by default, v2 hidden", (await S()).planHidden && !(await S()).v1Hidden);
  // a v1 scenario exists before switching tools and survives the switch
  await page.click("#wiModePoints"); await at(0.5, 0.5); await page.click("#wiModePoints");
  const v1before = await page.evaluate(() => JSON.stringify(CITY_APP.wiScenario()));
  await page.click('#toolSeg button[data-tool="v2"]');
  let s = await S();
  check("tool switch: v2 card shown, v1 card hidden, v1 layer not drawn", s.tool === "v2" && !s.planHidden && s.v1Hidden && !(await page.$("#map [data-wi-point]")));
  await page.click("#plModePoints");
  await at(0.3, 0.3); await at(0.6, 0.4); await at(0.45, 0.7);
  const mk = await page.$eval("#map g[data-id]", (g) => { const r = g.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.click(mk.x, mk.y);
  s = await S();
  check("4 control points by click (one on a marker; object not selected)", s.ps.points.length === 4 && s.rows === 4 && (await page.evaluate(() => CITY_APP.state.selected)) === null);
  await at(0.01, 0.01);
  s = await S();
  check("click outside the square rejected with a message", s.ps.points.length === 4 && s.msg.includes("вне квадрата"), s.msg);
  await page.click("#plModeCands");
  await at(0.32, 0.32); await at(0.62, 0.42); await at(0.8, 0.8);
  s = await S();
  check("3 candidates by click (default cost 100, hypothetical)", s.ps.cands.length === 3 && s.ps.cands.every((c) => c.cost === 100));
  await page.focus("#map"); await page.keyboard.press("Enter");
  s = await S();
  check("keyboard: Enter on map adds a candidate at the centre", s.ps.cands.length === 4 && s.ps.cands[3].id === "K4");
  await page.keyboard.press("Escape");
  check("Escape leaves the placement mode", (await S()).ps.mode === null);
  // weights and costs via keyboard inputs; invalid values are rejected and not applied
  await page.fill("#plW_P1", "5"); await page.press("#plW_P1", "Enter");
  await page.fill("#plC_K1", "250"); await page.press("#plC_K1", "Enter");
  s = await S();
  check("weight and cost edited by keyboard", s.ps.points[0].weight === 5 && s.ps.cands[0].cost === 250);
  await page.fill("#plW_P2", "101"); await page.press("#plW_P2", "Enter");
  s = await S();
  check("weight 101 rejected, previous value kept", s.ps.points[1].weight === 1 && s.msg.includes("1..100"), s.msg);
  await page.fill("#plC_K2", "0"); await page.press("#plC_K2", "Enter");
  check("cost 0 rejected", (await S()).ps.cands[1].cost === 100);
  await page.fill("#plBudget", "300"); await page.press("#plBudget", "Enter");
  await page.fill("#plMax", "2"); await page.press("#plMax", "Enter");
  // manual plan: K1 + K2 = 350 > 300 -> infeasible with the reason; then remove K1 -> feasible
  await page.check("#plSel_K1"); await page.check("#plSel_K2");
  s = await S();
  check("manual plan over budget: infeasible with reason, not altered", !s.ev.feasibility.feasible && s.feas.includes("бюджета") && s.ps.selected.length === 2, s.feas);
  await page.uncheck("#plSel_K1");
  s = await S();
  const k2 = s.ev.rows.filter((r) => r.nearest_after && r.nearest_after.kind === "hypothetical");
  check("manual plan K2 feasible; rows use the candidate where nearer", s.ev.feasibility.feasible && s.feas.startsWith("План допустим") && k2.length >= 1, JSON.stringify(s.ev.metrics));
  check("after ≤ before and delta = before − after in mm", s.ev.rows.every((r) => r.before_mm === null || (r.after_mm <= r.before_mm && r.delta_mm === r.before_mm - r.after_mm)));
  check("hypothetical candidates not in observed counters (55/55/55)", s.markers === 55 && s.tbl === 55 && s.slice.includes("55 в полном ответе"));
  const lay = await page.evaluate(() => ({ c: document.querySelectorAll('#map [data-layer="hypothetical"] [data-plan-cand]').length, p: document.querySelectorAll('#map [data-plan-point]').length }));
  check("candidates and points drawn in the separate hypothetical layer", lay.c === 4 && lay.p === 4, JSON.stringify(lay));
  // required / excluded constraints
  await page.selectOption("#plS_K3", "required"); await page.selectOption("#plS_K2", "excluded");
  s = await S();
  check("constraints: required K3, excluded K2 reported for the manual plan", s.ps.required.includes("K3") && s.ps.excluded.includes("K2") && !s.ev.feasibility.feasible
    && s.ev.feasibility.reasons.map((r) => r.code).sort().join() === "has_excluded,missing_required", JSON.stringify(s.ev.feasibility));
  await page.selectOption("#plS_K3", "free"); await page.selectOption("#plS_K2", "free");
  // move and delete a candidate
  const before = JSON.stringify((await S()).ev.metrics);
  await page.click("#plMove_K2"); await at(0.31, 0.31);
  s = await S();
  check("move candidate: position changed, recomputed, mode closed", s.ps.mode === null && JSON.stringify(s.ev.metrics) !== before && s.msg.includes("перенесён"));
  await page.click('[data-plan-cand-item="K2"] button[aria-label="Удалить кандидата K2"]');
  s = await S();
  check("delete candidate: removed from list, constraints and manual plan", !s.ps.cands.some((c) => c.id === "K2") && !s.ps.selected.includes("K2") && s.ev.metrics.count === 0);
  await page.screenshot({ path: path.join(out, "p1_shymkent_manual.png") });
  // v1 state survived the tool switch
  await page.click('#toolSeg button[data-tool="v1"]');
  check("v1 scenario intact after working in v2", (await page.evaluate(() => JSON.stringify(CITY_APP.wiScenario()))) === v1before);
  await page.click('#toolSeg button[data-tool="v2"]');
  // category change resets
  await page.selectOption("#plCat", "outpatient_clinic");
  s = await S();
  check("category change resets the v2 scenario with a reason", s.ps.points.length === 0 && s.ps.cands.length === 0 && s.msg.includes("Категория изменена"), s.msg);
  // demo set + city switch
  await page.click("#plDemo");
  s = await S();
  check("synthetic demo set labelled as invented", s.ps.points.length === 10 && s.ps.cands.length === 8 && (await page.textContent("#plDemoNote")).includes("synthetic"));
  await page.click('#citySeg button[data-city="astana"]');
  s = await S();
  check("city switch resets v2 with a reason", s.ps.points.length === 0 && s.msg.includes("Город изменён"), s.msg);
  await page.click("#plDemo");
  await page.evaluate(() => { CITY_PLAN_UI.toggleSelected("K1", true); CITY_PLAN_UI.toggleSelected("K6", true); });
  s = await S();
  check("Astana: demo plan evaluated (clinics), 65 records untouched", s.ev && s.ev.rows.length === 10 && s.tbl === 65 && s.ev.metrics.cost === 100 + 285, JSON.stringify(s.ev && s.ev.metrics));
  await page.screenshot({ path: path.join(out, "p2_astana_demo.png") });

  // ---------- stage 2: exact search, progress, cancel, stale, apply ----------
  // grow the Astana demo to the maximum 16 candidates × 25 points (synthetic positions inside the square)
  await page.evaluate(() => {
    const U = CITY_PLAN_UI, b = CITY_EVIDENCE.cities.astana.bbox, g = (fx, fy) => [b[0] + (b[2] - b[0]) * fx, b[1] + (b[3] - b[1]) * fy];
    U.setMode("cands"); for (let k = 0; k < 8; k++) U.place(g(0.1 + 0.11 * k, 0.5));
    U.setMode("points"); for (let k = 0; k < 15; k++) U.place(g(0.05 + 0.06 * k, 0.1 + 0.05 * (k % 4)));
    U.setMode("points");
  });
  s = await S();
  check("editor at the maximum: 16 candidates × 25 points", s.ps.cands.length === 16 && s.ps.points.length === 25);
  const tStart = Date.now();
  await page.click("#plRun");
  const sawProgress = await page.evaluate(() => !!document.getElementById("plProgress"));
  await page.waitForFunction(() => CITY_PLAN_UI.opt.status !== "running", null, { timeout: 30000 });
  const tRun = Date.now() - tStart;
  const opt = await page.evaluate(() => {
    const U = CITY_PLAN_UI, sc = U.scenario(), ref = CITY_PLAN.optimizePlans(U.ctxOf(CITY_APP.state.city), sc, { F: CITY_FACTS });
    return { st: U.opt.status, r: U.opt.result, ref, table: !!document.getElementById("plCompare"), msg: document.getElementById("plOptMsg").textContent };
  });
  check(`search 16×25 in the browser finished (${tRun} ms incl. sensitivity), progress shown`, opt.st === "done" && opt.r.status === "optimal" && opt.r.evaluated === 65536 && sawProgress, opt.msg);
  check("UI result = direct optimizePlans (same winners, Pareto, digest)", JSON.stringify(opt.r.objectives) === JSON.stringify(opt.ref.objectives) && JSON.stringify(opt.r.pareto) === JSON.stringify(opt.ref.pareto) && opt.r.problem_digest === opt.ref.problem_digest);
  check("comparison table: manual + three objectives with 'Применить'", opt.table && (await page.$$("#plCompare button")).length === 3);
  const manualBefore = (await S()).ps.selected;
  check("search does not auto-apply (manual plan unchanged)", JSON.stringify(manualBefore) === JSON.stringify(["K1", "K6"]));
  await page.click("#plApply_minimax");
  s = await S();
  check("apply: manual plan := minimax winner; result stays valid", JSON.stringify(s.ps.selected) === JSON.stringify(opt.r.objectives.minimax.ids) && (await page.evaluate(() => CITY_PLAN_UI.opt.status)) === "done");
  await page.click("#plRestore");
  check("restore: manual plan back", JSON.stringify((await S()).ps.selected) === JSON.stringify(["K1", "K6"]));
  await page.screenshot({ path: path.join(out, "p3_astana_compare.png"), fullPage: true });
  // changing a parameter invalidates the old answer
  await page.fill("#plBudget", "450"); await page.press("#plBudget", "Enter");
  s = await S();
  check("budget change: old optimum marked stale, apply buttons gone", (await page.evaluate(() => CITY_PLAN_UI.opt.status)) === "stale" && !(await page.$("#plCompare")) && (await page.textContent("#plOptMsg")).includes("устарели"));
  // cancel while running
  const c1 = await page.evaluate(() => { const U = CITY_PLAN_UI; U.startSearch(); const running = U.opt.status === "running"; U.cancelSearch(); return { running, st: U.opt.status, res: U.opt.result }; });
  await page.waitForTimeout(300);
  const c2 = await page.evaluate(() => ({ st: CITY_PLAN_UI.opt.status, table: !!document.getElementById("plCompare") }));
  check("cancel: status cancelled, no partial result shown later", c1.running && c1.st === "cancelled" && c1.res === null && c2.st === "cancelled" && !c2.table, JSON.stringify([c1, c2]));
  // parameter change during a run: the late answer is discarded
  await page.evaluate(() => { CITY_PLAN_UI.startSearch(); CITY_PLAN_UI.setNumber("Радиус", "600", 100, 5000, (v) => { CITY_PLAN_UI.state.radius = v; }); });
  await page.waitForTimeout(500);
  const st2 = await page.evaluate(() => ({ st: CITY_PLAN_UI.opt.status, res: CITY_PLAN_UI.opt.result }));
  check("parameter change during the search: answer discarded (stale)", st2.st === "stale" && st2.res === null, JSON.stringify(st2));
  // infeasible: required candidate costs more than the budget
  check("long lists collapse (16 candidates): section closed by default, opens by click", !(await page.evaluate(() => document.getElementById("plSecCands").open)));
  await page.click("#plSecCands > summary");
  await page.selectOption("#plS_K7", "required");
  await page.fill("#plBudget", "100"); await page.press("#plBudget", "Enter");
  await page.click("#plRun");
  await page.waitForFunction(() => CITY_PLAN_UI.opt.status !== "running");
  const inf = await page.evaluate(() => ({ r: CITY_PLAN_UI.opt.result, msg: document.getElementById("plOptMsg").textContent }));
  check("infeasible: required cost > budget reported with reason, constraint kept", inf.r.status === "infeasible" && inf.msg.includes("Нет допустимых") && inf.msg.includes("бюджета")
    && (await S()).ps.required.includes("K7"), inf.msg);
  await page.selectOption("#plS_K7", "free");
  await page.fill("#plBudget", "600"); await page.press("#plBudget", "Enter");
  /*__STAGE3__*/

  await page.setViewportSize({ width: 390, height: 844 });
  const sw = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  check("390 px: no horizontal scroll with the v2 card", sw.sw <= sw.cw + 1, JSON.stringify(sw));
  await page.screenshot({ path: path.join(out, "p9_narrow.png"), fullPage: false });
  check("no console/page errors", errors.length === 0, errors.join(" | "));
  check("no network requests", requests.length === 0, requests.join(" "));
  await browser.close();
  fs.writeFileSync(path.join(out, "plan_smoke_result.json"), JSON.stringify({ url: "web/index.html (file://)", results }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
