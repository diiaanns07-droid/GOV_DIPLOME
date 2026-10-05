// K07 round 8: independent browser tests of the BUILD planner «Несколько объектов (v2)» (web/plan.js + web/plan-ui.js).
// Usage: node k07r8_build_planner.cjs --app-root <BUILD extraction> | --url <index.html URL> [--label …] [--sha …] [--out …]
// Adapter to BUILD's own DOM/API (ids #toolSeg, #plModePoints, #plCands …; window.CITY_PLAN_UI.state / .opt).
// User path + refusals + keyboard + 390 px; numbers compared with the K07 calculator (web/plan_calc.js, itself checked
// against the Python oracle). Files for import are built by the test: SYNTHETIC points/sites/costs, real snapshot.
// Verdicts: PASS | FAIL | TEST_INCOMPATIBLE (precondition not met — never PASS).
const path = require("path"), fs = require("fs"), vm = require("vm"), { pathToFileURL } = require("url");
const { chromium } = require("playwright");
const K = path.join(__dirname, "..");
const C = require(path.join(K, "web", "plan_calc.js")), DEMO = require(path.join(K, "web", "plan_demo.js"));
const { realScenarios } = require(path.join(__dirname, "plan_cases.cjs"));

const a = process.argv.slice(2), OPT = { label: "build", sha: null, out: null, appRoot: null, url: null };
for (let i = 0; i < a.length; i++) {
  const k = a[i], v = a[i + 1];
  if (k === "--app-root") { OPT.appRoot = v; i++; } else if (k === "--url") { OPT.url = v; i++; } else if (k === "--label") { OPT.label = v; i++; }
  else if (k === "--sha") { OPT.sha = v; i++; } else if (k === "--out") { OPT.out = v; i++; } else { console.error("unknown argument " + k); process.exit(2); }
}
if (!!OPT.appRoot === !!OPT.url) { console.error("give exactly one of --app-root or --url"); process.exit(2); }
const ROOT = OPT.appRoot ? path.resolve(OPT.appRoot) : null, WEB = ROOT && (fs.existsSync(path.join(ROOT, "web")) ? path.join(ROOT, "web") : ROOT);
const URL_ = ROOT ? pathToFileURL(path.join(WEB, "index.html")).href : OPT.url;
const OUT = path.resolve(OPT.out || path.join(K, "results", OPT.label)), SHOTS = path.join(OUT, "screenshots");
const checks = [];
function check(id, area, expect, ok, observed, pre) { checks.push({ id, area, expect, verdict: pre === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL", observed: observed === undefined ? null : observed }); }
// data/facts of the same build for the K07 calculator (Node side)
let D = null, F = null;
if (WEB) { F = require(path.join(WEB, "facts.js")); const box = {}; vm.createContext(box); box.window = box; vm.runInContext(fs.readFileSync(path.join(WEB, "data.js"), "utf8"), box); D = box.CITY_EVIDENCE; }

async function open(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1400, height: 1000 } });
  const p = await ctx.newPage(), errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  p.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  await p.goto(URL_);
  await p.waitForSelector("#map g[data-id]", { timeout: 15000 });
  return { p, ctx, errors };
}
const st = (p) => p.evaluate(() => {
  const U = window.CITY_PLAN_UI, S = U.state, O = U.opt;
  return { tool: window.CITY_APP.state.tool, city: window.CITY_APP.state.city, mode: S.mode, category: S.category, points: S.points.map((x) => ({ ...x })), cands: S.cands.map((x) => ({ ...x })),
    budget: S.budget, max: S.max_selected, radius: S.radius, required: S.required.slice(), excluded: S.excluded.slice(), selected: S.selected.slice().sort(),
    msg: (document.getElementById("plMsg") || {}).textContent || "", optMsg: (document.getElementById("plOptMsg") || {}).textContent || "",
    opt: { status: O.status, result: O.result && { status: O.result.status, digest: O.result.problem_digest }, backup: !!O.backup },
    cardHidden: document.getElementById("planCard").hidden, mapStatus: document.getElementById("mapStatus").textContent };
});
const digestOfState = (s) => JSON.stringify([s.city, s.category, s.points, s.cands, s.budget, s.max, s.radius, s.required, s.excluded, s.selected]);
async function mapToTop(p) { await p.evaluate(() => document.querySelector(".mapwrap").scrollIntoView({ block: "start" })); }
async function freeSpots(p, n, offset = 0) {
  await mapToTop(p);
  return p.evaluate(([n, offset]) => {
    const sq = document.querySelector('#map rect[stroke-dasharray="6 4"]').getBoundingClientRect(), out = [];
    const top = Math.max(sq.top, 0) + 14, bottom = Math.min(sq.bottom, innerHeight) - 14;
    for (let y = top + offset; y < bottom && out.length < n; y += 33) for (let x = sq.left + 16 + offset; x < sq.right - 16 && out.length < n; x += 43) {
      const e = document.elementFromPoint(x, y);
      if (!e || !e.closest("#map") || e.closest("g[data-id]") || e.closest("[data-plan-point],[data-plan-cand]") || e.tagName === "text") continue;
      out.push({ x, y });
    }
    return out;
  }, [n, offset]);
}
const clickAll = async (p, spots) => { await mapToTop(p); for (const q of spots) await p.mouse.click(q.x, q.y); };
// a value may be applied on the next event-loop turn (BUILD + K07 fix K3): give the page a moment before reading
async function setNum(p, id, v) { const l = p.locator("#" + id); await l.fill(String(v)); await l.press("Enter"); await p.waitForTimeout(60); }
async function toV2(p) { await p.click('#toolSeg button[data-tool="v2"]'); }
async function mode(p, m) { const want = m === "points" ? "#plModePoints" : "#plModeCands"; if ((await p.getAttribute(want, "aria-pressed")) !== "true") await p.click(want); }
const active = (p) => p.evaluate(() => { const e = document.activeElement; return { id: e.id || null, tag: e.tagName, label: e.getAttribute && e.getAttribute("aria-label"), body: e === document.body, inCard: !!(e.closest && e.closest("#planCard")) }; });
async function importText(p, name, text) {
  await p.setInputFiles("#plFile", { name, mimeType: "application/json", buffer: Buffer.from(text, "utf8") });
  await p.waitForTimeout(150);
}
const k07ctx = {};
const kctx = (city) => k07ctx[city] || (k07ctx[city] = C.makeContext(D, city, F));

async function userPath(browser) {
  const { p, ctx, errors } = await open(browser);
  await toV2(p);
  let s = await st(p);
  check("B1", "path", "tool «Несколько объектов (v2)» shows the plan card and hides the v1 card", s.tool === "v2" && !s.cardHidden && (await p.isHidden("#whatifCard")), { tool: s.tool });
  await mode(p, "points");
  const sp = await freeSpots(p, 12, 4);
  await clickAll(p, sp.slice(0, 3));
  s = await st(p);
  check("B2", "path", "points mode: 3 clicks give P1..P3 with weight 1; the status line near the map names the mode", s.points.length === 3 && s.points.every((x) => x.weight === 1) && /контрольные точки/.test(s.mapStatus), { points: s.points.length, mapStatus: s.mapStatus });
  await mode(p, "cands");
  await clickAll(p, sp.slice(3, 6));
  s = await st(p);
  check("B3", "path", "candidates mode: 3 clicks give K1..K3 with the conditional default cost 100", s.cands.length === 3 && s.cands.every((c) => c.cost === 100) && /стоимость по умолчанию 100/.test(s.msg), { cands: s.cands, msg: s.msg });
  await p.evaluate(() => { for (const d of document.querySelectorAll("#planCard details")) d.open = true; });
  await setNum(p, "plW_P2", 5); await setNum(p, "plC_K1", 250); await setNum(p, "plC_K2", 120);
  await setNum(p, "plBudget", 400); await setNum(p, "plMax", 2); await setNum(p, "plRadius", 300);
  s = await st(p);
  check("B4", "path", "weights, costs, budget, max and radius are set by the inputs", s.points[1].weight === 5 && s.cands[0].cost === 250 && s.cands[1].cost === 120 && s.budget === 400 && s.max === 2 && s.radius === 300, { p2: s.points[1].weight, k1: s.cands[0].cost, budget: s.budget, max: s.max, radius: s.radius });
  await p.check("#plSel_K1"); await p.check("#plSel_K2");
  const f1 = await p.textContent("#plFeasible");
  await setNum(p, "plBudget", 300);
  const f2 = await p.textContent("#plFeasible");
  check("B5", "path", "manual plan K1+K2: feasible at budget 400 (370 of 400), infeasible at 300 with the reason", /допустим: 2 объект\(а\), 370 из 400/.test(f1) && /недопустим/.test(f2) && /300/.test(f2), { f1, f2 });
  await setNum(p, "plBudget", 400);
  await p.click("#plRun");
  await p.waitForFunction(() => window.CITY_PLAN_UI.opt.status === "done", null, { timeout: 20000 });
  s = await st(p);
  const raw = await p.evaluate(() => window.CITY_PLAN_UI.rawScenario());
  const v = C.validatePlanScenario(raw, kctx(raw.city_id)), ref = v.ok && C.optimizePlans(kctx(raw.city_id), v.scenario);
  const ui = await p.evaluate(() => window.CITY_PLAN_UI.opt.result.objectives);
  const same = !!ref && ["mean", "minimax", "coverage"].every((k) => ui[k].ids.join() === ref.objectives[k].selected_ids.join() && ui[k].weighted_sum_mm === ref.objectives[k].metrics.weighted_sum_mm && ui[k].max_mm === ref.objectives[k].metrics.max_mm && ui[k].covered_weight === ref.objectives[k].metrics.covered_weight && ui[k].cost === ref.objectives[k].metrics.cost);
  const cards = await p.evaluate(() => [...document.querySelectorAll("#plCompare [data-obj]")].map((c) => c.dataset.obj));
  check("B6", "path", "search result (three objectives: IDs, sum, worst, coverage, cost) = the K07 calculator for the same scenario; cards manual + 3",
    same && cards.join() === "manual,mean,minimax,coverage" && JSON.stringify(s.selected) === '["K1","K2"]', { ui, ref: ref && ref.objectives, cards, v: v.ok ? "ok" : v.error });
  await p.click("#plApply_mean");
  const sA = await st(p);
  await p.click("#plRestore");
  const sR = await st(p);
  check("B7", "path", "«Применить» (Среднее) sets the manual plan to its IDs; «Вернуть ручной план» restores K1+K2", JSON.stringify(sA.selected) === JSON.stringify(ui.mean.ids.slice().sort()) && JSON.stringify(sR.selected) === '["K1","K2"]', { applied: sA.selected, restored: sR.selected });
  await p.click("#plRun");
  await p.waitForFunction(() => window.CITY_PLAN_UI.opt.status === "done", null, { timeout: 20000 });
  await setNum(p, "plW_P1", 7);
  s = await st(p);
  check("B8", "stale", "a weight change after the search drops the result (status stale, no «Применить»)", s.opt.status === "stale" && !s.opt.result && (await p.locator("#plApply_mean").count()) === 0 && /устарели/.test(s.optMsg), { opt: s.opt, optMsg: s.optMsg });
  // interop: the BUILD export is accepted by the K07 validator; a K07 SYNTHETIC fixture is accepted by the BUILD import
  const exp = await p.evaluate(() => window.CITY_PLAN_UI.exportText());
  const ev = C.validatePlanScenario(JSON.parse(exp), kctx("shymkent"));
  check("B12", "interop", "a file exported by BUILD passes the K07 validator (same snapshot, derived_results dropped)", ev.ok, ev.ok ? null : ev.error);
  const fx = fs.readFileSync(path.join(K, "fixtures", "synthetic_demo_shymkent_school.json"), "utf8");
  await importText(p, "k07_fixture.json", fx);
  s = await st(p);
  check("B11", "interop", "the K07 SYNTHETIC fixture (shymkent/school) is accepted by the BUILD import: 12 points, 8 sites, budget 150", s.points.length === 12 && s.cands.length === 8 && s.budget === 150 && /загружен/.test(s.msg), { points: s.points.length, cands: s.cands.length, msg: s.msg.slice(0, 120) });
  // city switch
  await p.click('#citySeg button[data-city="astana"]');
  s = await st(p);
  await mode(p, "points");
  const sa = await freeSpots(p, 1, 9);
  await clickAll(p, sa);
  const s2 = await st(p), bb = D.cities.astana.bbox, q = s2.points[0];
  check("B10", "reset", "city switch resets the plan with a reason; in Astana points go into Astana's square", s.city === "astana" && s.points.length === 0 && /Город изменён/.test(s.msg) && !!q && q.lon >= bb[0] && q.lon <= bb[2] && q.lat >= bb[1] && q.lat <= bb[3], { msg: s.msg, point: q });
  check("G1", "general", "no console or page errors on the user path", errors.length === 0, errors);
  await ctx.close();
}

async function refusals(browser) {
  const { p, ctx, errors } = await open(browser);
  await toV2(p);
  await mode(p, "points");
  await clickAll(p, (await freeSpots(p, 2, 6)));
  // outside the square
  const out = await p.evaluate(() => { const sq = document.querySelector('#map rect[stroke-dasharray="6 4"]').getBoundingClientRect(), m = document.getElementById("map").getBoundingClientRect(); return sq.left - m.left > 20 ? { x: (m.left + sq.left) / 2, y: Math.min(sq.top + sq.height / 2, innerHeight - 20) } : null; });
  let s = await st(p); const n0 = s.points.length;
  if (out) { await mapToTop(p); await p.mouse.click(out.x, out.y); }
  s = await st(p);
  check("R1", "refusal", "a click outside the K10 square places nothing and says why", !!out && s.points.length === n0 && /вне квадрата/.test(s.msg), { msg: s.msg }, !!out);
  // invalid numbers: refused with a message, the shown value returns to the stored one
  await p.evaluate(() => { for (const d of document.querySelectorAll("#planCard details")) d.open = true; });
  const bad = [["plW_P1", "0"], ["plW_P1", "2.5"], ["plW_P1", "101"], ["plBudget", "1000001"], ["plBudget", "-1"], ["plMax", "6"], ["plRadius", "50"], ["plRadius", ""]];
  const res = [];
  for (const [id, val] of bad) {
    const before = await st(p);
    await setNum(p, id, val);
    const after = await st(p), shown = await p.inputValue("#" + id);
    res.push({ id, val, refused: digestOfState(before) === digestOfState(after) && /нужно целое/.test(after.msg), shown });
  }
  check("R3", "refusal", "weight 0 / 2.5 / 101, budget 1 000 001 / −1, max 6, radius 50 / empty: refused with a message, state unchanged", res.every((x) => x.refused), res);
  check("R3b", "refusal", "after a refused value the input shows the stored value again (not the rejected text)", res.every((x) => !["0", "2.5", "101", "1000001", "-1", "6", "50"].includes(x.shown)), res.map((x) => [x.id, x.val, x.shown]));
  // limits: import a 16×25 plan, then try one more point and one more candidate
  const big = realScenarios(C, D, F, DEMO).find((c) => c.name === "shymkent/school/max_16x25").scenario;
  await importText(p, "k07_max_16x25.json", JSON.stringify(big));
  s = await st(p);
  const loaded = s.points.length === 25 && s.cands.length === 16;
  await mode(p, "points"); await clickAll(p, (await freeSpots(p, 1, 2)));
  const s1 = await st(p);
  await mode(p, "cands"); await clickAll(p, (await freeSpots(p, 1, 2)));
  const s2 = await st(p);
  check("R2", "refusal", "limits: with 25 points and 16 sites the next point / site is refused with a message", loaded && s1.points.length === 25 && /Не больше 25/.test(s1.msg) && s2.cands.length === 16 && /Не больше 16/.test(s2.msg), { loaded, p: s1.points.length, c: s2.cands.length, m1: s1.msg, m2: s2.msg }, loaded);
  // cancel a long search (16×25 + three budgets)
  await p.click("#plRun");
  await p.waitForTimeout(60);
  const mid = await st(p);
  await p.click("#plCancel");
  await p.waitForTimeout(800);
  s = await st(p);
  check("R6", "cancel", "«Отменить поиск» on a 16×25 search: status cancelled, no result appears later, manual plan unchanged", mid.opt.status === "running" && s.opt.status === "cancelled" && !s.opt.result && /отменён/.test(s.optMsg) && JSON.stringify(s.selected) === JSON.stringify(mid.selected), { mid: mid.opt, end: s.opt, msg: s.optMsg }, mid.opt.status === "running");
  // infeasible: a required site costing more than the budget
  await p.evaluate(() => { for (const d of document.querySelectorAll("#planCard details")) d.open = true; });
  await p.selectOption("#plS_site-03", "required"); await setNum(p, "plBudget", 50);
  await p.click("#plRun");
  await p.waitForFunction(() => ["done", "stale"].includes(window.CITY_PLAN_UI.opt.status), null, { timeout: 20000 });
  s = await st(p);
  check("R4", "refusal", "required site cost > budget: «Нет допустимых планов» with the reason; constraints are not dropped", /Нет допустимых планов/.test(s.optMsg) && /бюджета 50/.test(s.optMsg) && s.required.includes("site-03"), { optMsg: s.optMsg });
  // import refusals: the current plan stays exactly as it was
  const good = JSON.parse(fs.readFileSync(path.join(K, "fixtures", "synthetic_demo_shymkent_school.json"), "utf8"));
  const astanaSnap = kctx("astana").source_snapshot;
  const T = (o) => JSON.stringify(o), mut = (f) => { const o = JSON.parse(T(good)); f(o); return T(o); };
  const files = [
    ["duplicate key", T(good).replace('"budget":150', '"budget":150,"budget":1')], ["NaN token", T(good).replace('"budget":150', '"budget":NaN')],
    ["1e999", T(good).replace('"budget":150', '"budget":1e999')], ["foreign snapshot", mut((o) => { o.source_snapshot = astanaSnap; })],
    ["unknown field url", mut((o) => { o.url = "https://example.com/x.js"; })], ["required∩excluded", mut((o) => { o.required_ids = ["site-1"]; o.excluded_ids = ["site-1"]; })],
    ["forged derived_results", mut((o) => { o.derived_results = { manual: { selected_ids: [], metrics: { weighted_sum_mm: 1, unknown_count: 0, max_mm: 1, covered_weight: 99, cost: 0 } } }; })],
    ["v1 file", T({ schema_version: "city-whatif-v1", city_id: "shymkent", source_snapshot: "sha256:00", category: "school", control_points: [], proposed_object: null })],
    ["not JSON", "{ this is not json"], ["deep nesting", "[".repeat(200) + "]".repeat(200)], ["over 256 KiB", T({ ...good, pad: "x".repeat(270000) })],
  ];
  const rr = [], noop = files.filter(([, t]) => t === T(good)).map(([n]) => n);
  for (const [name, text] of files) {
    const before = await st(p);
    await importText(p, name.replace(/\W+/g, "_") + ".json", text);
    const after = await st(p);
    rr.push({ name, unchanged: digestOfState(before) === digestOfState(after), msg: after.msg.slice(0, 90) });
  }
  check("R5", "refusal", "11 bad files (duplicate key, NaN, 1e999, foreign snapshot, unknown field, required∩excluded, forged derived_results, v1, not JSON, deep nesting, > 256 KiB): «не принят», plan unchanged",
    rr.every((x) => x.unchanged && /не принят/.test(x.msg)), rr, noop.length === 0);
  check("G2", "general", "no console or page errors on the refusal path", errors.length === 0, errors);
  await ctx.close();
}

async function keyboard(browser) {
  const { p, ctx, errors } = await open(browser);
  await toV2(p);
  await p.focus("#plModePoints"); await p.keyboard.press("Enter");
  await p.focus("#map"); await p.keyboard.press("Enter");
  for (let i = 0; i < 3; i++) await p.keyboard.press("ArrowRight");
  await p.keyboard.press("Enter");
  let s = await st(p);
  check("K1", "keyboard", "focused map + Enter places a point at the centre in v2 points mode (2 points after Enter, arrows, Enter)", s.points.length === 2, { points: s.points.length });
  // natural Tab path between the map and the plan card while placing
  await p.focus("#map");
  let n = 0; for (; n < 60; n++) { await p.keyboard.press("Tab"); const f = await active(p); if (f.inCard) break; }
  check("K2", "keyboard", "while placing, the plan card is reachable from the map in ≤ 10 Tab presses (roads and records should not stand in between)", n < 10, { tabsMapToCard: n < 60 ? n + 1 : ">60" });
  // Tab after typing a number moves on to the next control
  await p.evaluate(() => { for (const d of document.querySelectorAll("#planCard details")) d.open = true; });
  await p.focus("#plBudget"); await p.keyboard.press("Control+A"); await p.keyboard.type("350"); await p.keyboard.press("Tab");
  await p.waitForTimeout(100);  // the value may be applied on the next event-loop turn; focus is read after the re-render
  const fTab = await active(p); s = await st(p);
  check("K3", "keyboard", "typing a budget and pressing Tab applies it and moves focus to the next field («Максимум объектов»)", s.budget === 350 && fTab.id === "plMax", { budget: s.budget, focus: fTab });
  // delete with the keyboard: focus must stay in the card
  const del = p.locator('#planCard button[aria-label="Удалить контрольную точку P1"]');
  await del.focus(); await p.keyboard.press("Enter");
  const fDel = await active(p); s = await st(p);
  check("K4", "keyboard", "«Удалить» with Enter removes the point and keeps the focus in the plan card (not on <body>)", s.points.length === 1 && !fDel.body && fDel.inCard, { points: s.points.length, focus: fDel });
  // search with the keyboard: focus is not lost while running and after the result
  await p.focus("#plRun"); await p.keyboard.press("Enter");
  const fRun = await active(p);
  await p.waitForFunction(() => window.CITY_PLAN_UI.opt.status === "done", null, { timeout: 20000 });
  const fDone = await active(p);
  check("K5", "keyboard", "«Найти точные оптимумы» with Enter: focus stays in the card while running (e.g. on «Отменить поиск») and after the result", !fRun.body && fRun.inCard && !fDone.body && fDone.inCard, { running: fRun, done: fDone });
  await p.focus("#map"); await p.keyboard.press("Escape");
  s = await st(p);
  check("K6", "keyboard", "Escape leaves the placement mode", s.mode === null, { mode: s.mode });
  check("G3", "general", "no console or page errors on the keyboard path", errors.length === 0, errors);
  await ctx.close();
}

async function narrow(browser) {
  const { p, ctx, errors } = await open(browser, { viewport: { width: 390, height: 844 } });
  await toV2(p);
  await p.click("#plDemo");
  await p.click("#plRun");
  await p.waitForFunction(() => window.CITY_PLAN_UI.opt.status === "done", null, { timeout: 20000 });
  await p.evaluate(() => { for (const d of document.querySelectorAll("#planCard details")) d.open = true; });
  const fit = await p.evaluate(() => {
    const card = document.getElementById("planCard"), cr = card.getBoundingClientRect(), iw = innerWidth;
    const els = [...card.querySelectorAll("button, input, select, td, th, .pl-cmp, figure, svg, li, p")].filter((e) => e.getBoundingClientRect().width > 0);
    const outside = els.filter((e) => { const r = e.getBoundingClientRect(); const wrap = e.closest(".tablewrap"); if (wrap && wrap !== e) { const w = wrap.getBoundingClientRect(); return w.right > cr.right + 1; } return r.right > cr.right + 1 || r.left < cr.left - 1; })
      .map((e) => e.tagName + "#" + (e.id || "") + ":" + (e.textContent || "").trim().slice(0, 24));
    const hidden = [...card.querySelectorAll(".tablewrap")].filter((w) => w.scrollWidth > w.clientWidth + 1).map((w) => (w.querySelector("table") || {}).id);
    return { pageScroll: document.documentElement.scrollWidth > iw, outside: outside.slice(0, 10), tablesWithInnerScroll: hidden };
  });
  check("N1", "390px", "390 px: no horizontal page scroll, nothing in the plan card sticks out of it", !fit.pageScroll && fit.outside.length === 0, fit);
  check("N2", "390px", "390 px: the Pareto / budget tables fit without an inner horizontal scroll", fit.tablesWithInnerScroll.length === 0, fit.tablesWithInnerScroll);
  await p.locator("#plCompare").scrollIntoViewIfNeeded();
  await p.screenshot({ path: path.join(SHOTS, "N_390_compare.png") });  // before the tap below makes the result stale
  await mode(p, "points");
  await mapToTop(p);
  const sp = await freeSpots(p, 1, 9);
  if (sp.length) await p.mouse.click(sp[0].x, sp[0].y);
  const msg = await p.evaluate(() => { const m = document.getElementById("mapStatus"), r = m.getBoundingClientRect(); return { text: m.textContent.slice(0, 60), top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight }; });
  check("N3", "390px", "390 px: after a tap on the map in points mode the status line is visible without scrolling", msg.top >= 0 && msg.bottom <= msg.vh && msg.text.length > 0, msg);
  check("G4", "general", "no console or page errors at 390 px", errors.length === 0, errors);
  await ctx.close();
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const { p, ctx } = await open(browser);
  const has = await p.evaluate(() => ({ plan: !!window.CITY_PLAN, ui: !!(window.CITY_PLAN_UI && window.CITY_PLAN_UI.state && window.CITY_PLAN_UI.opt), tool: !!document.querySelector('#toolSeg button[data-tool="v2"]'), card: !!document.getElementById("planCard") }));
  await ctx.close();
  if (!has.plan || !has.ui || !has.tool || !has.card || !D) {
    check("P0", "precondition", "the build contains the BUILD v2 planner (CITY_PLAN, CITY_PLAN_UI.state/opt, #toolSeg v2, #planCard) and --app-root data", false, has, false);
  } else { await userPath(browser); await refusals(browser); await keyboard(browser); await narrow(browser); }
  await browser.close();
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K07 round-8 independent browser tests of the BUILD planner (city-plan-v2)", label: OPT.label, sha: OPT.sha,
    target: ROOT ? { app_root: path.basename(ROOT) } : { url: OPT.url }, total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"),
    note: "Points, sites, costs and weights are placed by the test or come from SYNTHETIC files; they are not city data.", checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} [${c.area}] ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 400)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  process.exitCode = out.fail.length || out.test_incompatible.length ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
