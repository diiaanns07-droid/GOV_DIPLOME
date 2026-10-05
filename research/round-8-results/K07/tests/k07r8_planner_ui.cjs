// K07 round 8: browser tests of the «План нескольких объектов» (city-plan-v2) UI — planner_ui.js + app.js hooks.
// Usage: node k07r8_planner_ui.cjs --app-root <dir with web/> | --url <index.html URL> [--label …] [--sha …] [--out …] [--only U|S]
// Real mouse/keyboard on the BUILD viewer with the K07 patch. Numbers are checked against the calculator in the page
// (window.CITY_PLAN_CALC), which itself is checked against the Python oracle by plan_calc.test.cjs.
// Data: the K10 slices of the BUILD; control points / sites / costs are placed by the test or come from the explicit
// SYNTHETIC demo set. Verdicts: PASS | FAIL | TEST_INCOMPATIBLE (precondition not met — never PASS).
const path = require("path"), fs = require("fs"), { pathToFileURL } = require("url");
const { chromium } = require("playwright");

function args() {
  const a = process.argv.slice(2), o = { label: "run", sha: null, out: null, appRoot: null, url: null, only: null };
  for (let i = 0; i < a.length; i++) {
    const k = a[i], v = a[i + 1];
    if (k === "--app-root") { o.appRoot = v; i++; } else if (k === "--url") { o.url = v; i++; } else if (k === "--label") { o.label = v; i++; }
    else if (k === "--sha") { o.sha = v; i++; } else if (k === "--out") { o.out = v; i++; } else if (k === "--only") { o.only = v; i++; }
    else { console.error("unknown argument " + k); process.exit(2); }
  }
  if (!!o.appRoot === !!o.url) { console.error("give exactly one of --app-root or --url"); process.exit(2); }
  return o;
}
const OPT = args();
let URL_;
if (OPT.appRoot) { const r = path.resolve(OPT.appRoot), w = fs.existsSync(path.join(r, "web", "index.html")) ? path.join(r, "web") : r; URL_ = pathToFileURL(path.join(w, "index.html")).href; }
else URL_ = OPT.url;
const OUT = path.resolve(OPT.out || path.join(__dirname, "..", "results", OPT.label)), SHOTS = path.join(OUT, "screenshots");
const checks = [];
function check(id, area, expect, ok, observed, pre) { checks.push({ id, area, expect, verdict: pre === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL", observed: observed === undefined ? null : observed }); }

async function open(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1400, height: 1000 } });
  const p = await ctx.newPage(), errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  p.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  if (opts.init) await p.addInitScript(opts.init);
  await p.goto(URL_);
  await p.waitForSelector("#map g[data-id]", { timeout: 15000 });
  return { p, ctx, errors };
}
const st = (p) => p.evaluate(() => {
  const S = window.CITY_PLAN_UI._state;
  return { open: S.open, tool: S.tool, city: S.city, category: S.category, points: S.points.map((x) => ({ ...x })), cands: S.cands.map((x) => ({ ...x })),
    selected: [...S.selected].sort(), budget: S.budget, max: S.max, radius: S.radius, pending: S.pending, msg: S.msg, synthetic: S.synthetic,
    cardHidden: document.getElementById("planCard").hidden, layerPts: document.querySelectorAll('#map [data-plan^="cp-"]').length,
    layerSites: document.querySelectorAll('#map [data-plan^="site-"]').length, mapStatus: document.getElementById("mapStatus").textContent,
    planMsg: (document.getElementById("plMsg") || {}).textContent || "", selectedRecord: window.CITY_APP.state.selected };
});
async function mapToTop(p) { await p.evaluate(() => document.querySelector(".mapwrap").scrollIntoView({ block: "start" })); }
// free spots inside the K10 square: not on a record marker, a plan marker or a label; ≥ 30 px apart
async function freeSpots(p, n, offset = 0, step = 31) {
  await mapToTop(p);
  return p.evaluate(([n, offset, step]) => {
    const sq = document.querySelector('#map rect[stroke-dasharray="6 4"]').getBoundingClientRect(), out = [];
    const top = Math.max(sq.top, 0) + 12, bottom = Math.min(sq.bottom, innerHeight) - 12;
    for (let y = top + offset; y < bottom && out.length < n; y += step) for (let x = sq.left + 14 + offset; x < sq.right - 14 && out.length < n; x += step) {
      const e = document.elementFromPoint(x, y);
      if (!e || !e.closest("#map") || e.closest("g[data-id]") || e.closest("[data-plan]") || e.tagName === "text") continue;
      if (out.some((q) => Math.hypot(q.x - x, q.y - y) < 30)) continue;
      out.push({ x, y });
    }
    return out;
  }, [n, offset, step]);
}
async function outsideSpot(p) {
  await mapToTop(p);
  return p.evaluate(() => {
    const sq = document.querySelector('#map rect[stroke-dasharray="6 4"]').getBoundingClientRect(), m = document.getElementById("map").getBoundingClientRect();
    return sq.left - m.left > 20 ? { x: (m.left + sq.left) / 2, y: Math.min(sq.top + sq.height / 2, innerHeight - 20) } : null;
  });
}
// spots are viewport coordinates taken after mapToTop(); scroll the map back first (checking a radio scrolls the card)
const clickAll = async (p, spots) => { await mapToTop(p); for (const q of spots) await p.mouse.click(q.x, q.y); };
const setTool = (p, v) => p.check(`#planBody input[name="plTool"][value="${v}"]`);
async function setNum(p, fk, value) { const l = p.locator(`#planBody [data-fk="${fk}"]`); await l.fill(String(value)); await l.press("Enter"); }
const active = (p) => p.evaluate(() => { const e = document.activeElement; return { id: e.id || null, fk: (e.dataset && e.dataset.fk) || null, tag: e.tagName, body: e === document.body, inCard: !!(e.closest && e.closest("#planCard")) }; });
const evalInPage = (p) => p.evaluate(() => { const U = window.CITY_PLAN_UI, C = U._calc(), v = U._validated(); return v.ok ? C.evaluatePlan(U._ctx(), v.scenario) : { error: v.error }; });

async function editorChecks(browser) {
  const { p, ctx, errors } = await open(browser);
  let s = await st(p);
  const sp0 = await freeSpots(p, 1);
  await clickAll(p, sp0);
  s = await st(p);
  check("U1", "mode", "plan closed by default: card hidden, a map click creates no plan item", s.cardHidden && !s.open && s.points.length === 0 && s.cands.length === 0, { cardHidden: s.cardHidden, points: s.points.length });
  await p.click("#planBtn");
  const spots = await freeSpots(p, 60, 3);
  await clickAll(p, spots.slice(0, 3));
  s = await st(p);
  check("U2", "placement", "plan open: 3 clicks give 3 control points (weight 1) in the list and on the map; the map status says so",
    !s.cardHidden && s.points.length === 3 && s.points.every((x) => x.weight === 1) && s.layerPts === 3 && /Точка 3 поставлена/.test(s.mapStatus) && (await p.locator("#plPts li[data-pl-point]").count()) === 3,
    { points: s.points.length, layer: s.layerPts, mapStatus: s.mapStatus });
  await setTool(p, "candidate");
  await clickAll(p, spots.slice(3, 5));
  s = await st(p);
  check("U3", "placement", "candidate tool: 2 clicks give 2 hypothetical sites with the conditional default cost 100, labelled as such",
    s.cands.length === 2 && s.cands.every((c) => c.cost === 100 && c.status === "free") && s.layerSites === 2 && /условное значение/.test(s.planMsg), { cands: s.cands, msg: s.planMsg });
  // limits
  await clickAll(p, spots.slice(5, 20));
  s = await st(p);
  check("U5", "limits", "at most 16 sites: the 17th click is refused with a message about the exact search limit", spots.length >= 20 && s.cands.length === 16 && /Не больше 16/.test(s.planMsg) && /65 536/.test(s.planMsg), { cands: s.cands.length, msg: s.planMsg }, spots.length >= 20);
  await setTool(p, "control");
  await clickAll(p, spots.slice(20, 43));
  s = await st(p);
  check("U4", "limits", "at most 25 control points: the 26th click is refused with a message", spots.length >= 43 && s.points.length === 25 && /Не больше 25/.test(s.planMsg), { points: s.points.length, msg: s.planMsg }, spots.length >= 43);
  const out = await outsideSpot(p);
  const n0 = s.points.length;
  if (out) { await mapToTop(p); await p.mouse.click(out.x, out.y); }
  s = await st(p);
  check("U6", "bbox", "a click outside the K10 square is refused with a message", !!out && s.points.length === n0 && /вне квадрата/.test(s.planMsg), { msg: s.planMsg }, !!out);
  // numeric inputs: invalid values are refused and the previous value is restored
  await setNum(p, "w-cp-1", "0");
  const w0 = await p.inputValue('#planBody [data-fk="w-cp-1"]'); s = await st(p);
  const wRef = s.points[0].weight === 1 && w0 === "1" && /Вес Точка 1: нужно целое число 1…100/.test(s.planMsg);
  await setNum(p, "w-cp-1", "2.5"); s = await st(p); const wFrac = s.points[0].weight === 1;
  await setNum(p, "w-cp-1", "7"); s = await st(p);
  check("U7", "inputs", "weight: 0 and 2.5 refused (value restored, message), 7 accepted", wRef && wFrac && s.points[0].weight === 7, { msg: s.planMsg, weight: s.points[0].weight, shown: w0 });
  await setNum(p, "c-site-1", "1000001"); s = await st(p);
  const cRef = s.cands[0].cost === 100 && /нужно целое число 1…1\s000\s000/.test(s.planMsg);
  await setNum(p, "c-site-1", "250"); s = await st(p);
  check("U8", "inputs", "cost: 1 000 001 refused, 250 accepted (conditional units)", cRef && s.cands[0].cost === 250, { msg: s.planMsg, cost: s.cands[0].cost });
  await setNum(p, "plRadius", "50"); s = await st(p); const rRef = s.radius === 500 && /Радиус охвата, м: нужно целое число 100…5\s000/.test(s.planMsg);
  await setNum(p, "plMax", "6"); s = await st(p); const mRef = s.max === 3;
  await setNum(p, "plBudget", "-1"); s = await st(p); const bRef = s.budget === 300;
  await setNum(p, "plRadius", "300"); await setNum(p, "plMax", "2"); await setNum(p, "plBudget", "400"); s = await st(p);
  check("U9", "inputs", "radius 50, max 6, budget −1 refused; radius 300, max 2, budget 400 accepted", rRef && mRef && bRef && s.radius === 300 && s.max === 2 && s.budget === 400, { radius: s.radius, max: s.max, budget: s.budget });
  // manual plan feasibility
  await p.check('#planBody [data-fk="sel-site-1"]'); await p.check('#planBody [data-fk="sel-site-2"]');
  let feas = await p.textContent("#plFeas"), sel = await p.textContent("#plManSel");
  const ok1 = /^✓/.test(feas) && /Место 1, Место 2/.test(sel) && /350 усл. ед. из бюджета 400/.test(sel);
  await setNum(p, "plBudget", "300"); feas = await p.textContent("#plFeas");
  const over = /стоимость больше бюджета \(350 > 300\)/.test(feas);
  await setNum(p, "plMax", "1"); feas = await p.textContent("#plFeas");
  const many = /мест больше, чем «Максимум объектов» \(2 > 1\)/.test(feas) && /стоимость больше бюджета/.test(feas);
  check("U10", "manual plan", "manual plan: feasible within budget/count; over budget and over count are reported with numbers, not hidden", ok1 && over && many, { feas, sel });
  await setNum(p, "plMax", "3"); await setNum(p, "plBudget", "400");
  // required / excluded
  await p.selectOption('#planBody [data-fk="st-site-3"]', "required");
  s = await st(p); const reqOk = s.selected.includes("site-3") && await p.isDisabled('#planBody [data-fk="sel-site-3"]') && await p.isChecked('#planBody [data-fk="sel-site-3"]');
  await p.selectOption('#planBody [data-fk="st-site-1"]', "excluded");
  s = await st(p); const excOk = !s.selected.includes("site-1") && await p.isDisabled('#planBody [data-fk="sel-site-1"]') && !(await p.isChecked('#planBody [data-fk="sel-site-1"]'));
  check("U11", "constraints", "«обязательно» puts the site into the manual plan (locked), «исключено» removes it (locked); the message says so", reqOk && excOk && /исключено/.test(s.planMsg), { selected: s.selected, msg: s.planMsg });
  // table vs calculator
  const ev = await evalInPage(p);
  const rows = await p.evaluate(() => [...document.querySelectorAll("#plTable tbody tr[data-pl-row]")].map((r) => [r.dataset.plRow, ...[...r.cells].map((c) => c.textContent)]));
  const near = await p.evaluate(() => [...document.querySelectorAll("#plTable tbody tr.pl-sub")].map((r) => r.textContent));
  const fmt = (mm) => (mm === null ? "—" : mm >= 1e6 ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(mm / 1e6) + " км" : new Intl.NumberFormat("ru-RU").format(Math.round(mm / 1000)) + " м");
  const same = !ev.error && rows.length === ev.rows.length && ev.rows.every((r, i) => rows[i][0] === r.control_point_id && rows[i][2] === fmt(r.before_mm) && rows[i][3] === fmt(r.after_mm));
  check("U12", "table", "per-point table = calculator: one row per point, before/after as computed; nearest object says «запись среза (source)» or «(гипотеза)»",
    same && near.length === ev.rows.length && near.every((t) => /запись среза \(|\(гипотеза\)/.test(t)), { rows: rows.slice(0, 3), ev: ev.error || ev.rows.slice(0, 3) });
  const mt = await p.evaluate(() => [...document.querySelectorAll("#plMetrics tr")].map((r) => [...r.cells].map((c) => c.textContent)));
  check("U13", "table", "metrics table compares «Исходный срез» and «Ручной план»: mean, worst point, coverage of point weight, cost", mt.length === 5 && mt[0].join("|") === "Показатель|Исходный срез|Ручной план" && /не жителей|вес точек/.test(mt[3][0]) && /усл. ед./.test(mt[4][2]), mt);
  // move and delete (focus)
  const before = (await st(p)).points[1];
  await p.click('#planBody [data-fk="mvp-cp-2"]');
  const fMove = await active(p);
  const free = await freeSpots(p, 1, 17);
  if (free.length) await clickAll(p, free);
  s = await st(p);
  const moved = s.points.find((x) => x.id === "cp-2");
  check("U14", "move", "«Перенести» moves the focus to the map; the next click moves that point (same id, new coordinates)", fMove.id === "map" && !!moved && (moved.lon !== before.lon || moved.lat !== before.lat) && !s.pending, { focus: fMove, before, moved });
  await p.click('#planBody [data-fk="dlc-site-4"]');
  s = await st(p); const fDel = await active(p);
  check("U15", "delete", "deleting a site removes it from the list, the map and the manual plan; focus goes to the next «Удалить»", !s.cands.some((c) => c.id === "site-4") && s.layerSites === 15 && fDel.fk === "dlc-site-5", { cands: s.cands.length, focus: fDel });
  // own marker click: nothing new
  await mapToTop(p);
  const own = await p.evaluate(() => { const m = document.querySelector('#map [data-plan="cp-1"] circle'); if (!m) return null; const r = m.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  const n1 = (await st(p)).points.length;
  if (own) await p.mouse.click(own.x, own.y);  // measured right before the click, no scroll in between
  s = await st(p);
  check("U19", "placement", "a click on the plan's own marker adds nothing", !!own && s.points.length === n1, { own: !!own, points: s.points.length }, !!own);
  // exclusivity with what-if v1 and the base point mode
  await p.click("#wiModePoints");
  s = await st(p); const wiOn = await p.evaluate(() => window.CITY_APP.state.wi.mode);
  const offByWi = s.tool === "none" && wiOn === "points";
  await setTool(p, "control");
  const wiAfter = await p.evaluate(() => window.CITY_APP.state.wi.mode);
  await p.click("#pointBtn");
  s = await st(p); const pm = await p.evaluate(() => window.CITY_APP.state.pointMode);
  const offByPoint = s.tool === "none" && pm;
  await setTool(p, "candidate");
  const pmAfter = await p.evaluate(() => window.CITY_APP.state.pointMode);
  check("U18", "modes", "one placement mode at a time: v1 «контрольные точки» or «Расстояние от точки» switch plan placement off, the plan tool switches them off", offByWi && wiAfter === null && offByPoint && pmAfter === false, { offByWi, wiAfter, offByPoint, pmAfter });
  // tool «Ничего»: a click on a record marker selects the record
  await setTool(p, "none");
  await mapToTop(p);
  const mk = await p.evaluate(() => { for (const g of [...document.querySelectorAll("#map g[data-id]")].reverse()) { const r = g.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2; if (g.contains(document.elementFromPoint(x, y))) return { x, y, id: g.dataset.id }; } return null; });
  const n2 = (await st(p)).points.length;
  if (mk) await p.mouse.click(mk.x, mk.y);
  s = await st(p);
  check("U23", "modes", "tool «Ничего»: a click on a record marker selects the record and adds no point", !!mk && s.points.length === n2 && s.selectedRecord && s.selectedRecord.id === mk.id, { selected: s.selectedRecord, points: s.points.length }, !!mk);
  await p.screenshot({ path: path.join(SHOTS, "U_1400_editor.png") });
  // category and city resets
  await p.selectOption("#plCat", "outpatient_clinic");
  s = await st(p);
  check("U16", "reset", "category change resets the plan with a reason", s.points.length === 0 && s.cands.length === 0 && s.category === "outpatient_clinic" && /Категория изменена/.test(s.planMsg), { msg: s.planMsg });
  await setTool(p, "control");
  await clickAll(p, (await freeSpots(p, 2, 9)));
  const had = (await st(p)).points.length;
  const other = await p.evaluate(() => [...document.querySelectorAll("#citySeg button")].map((b) => b.dataset.city).find((c) => c !== window.CITY_APP.state.city));
  await p.click(`#citySeg button[data-city="${other}"]`);
  s = await st(p);
  const resetMsg = s.planMsg;
  await setTool(p, "control");
  const sa = await freeSpots(p, 1, 5);
  await clickAll(p, sa);
  const sA = await st(p);
  const bb = await p.evaluate((c) => window.CITY_EVIDENCE.cities[c].bbox, other), q = sA.points[0];
  const back = await p.evaluate(() => [...document.querySelectorAll("#citySeg button")].map((b) => b.dataset.city).find((c) => c !== window.CITY_APP.state.city));
  await p.click(`#citySeg button[data-city="${back}"]`);
  const sB = await st(p);
  check("U17", "reset", "city switch resets the plan with a reason; in the other city points go into its own square; nothing is restored on return",
    had === 2 && s.points.length === 0 && s.city === other && /Город изменён/.test(resetMsg) && !!q && q.lon >= bb[0] && q.lon <= bb[2] && q.lat >= bb[1] && q.lat <= bb[3] && sB.points.length === 0,
    { had, afterSwitch: s.points.length, msg: resetMsg, point: q, bbox: bb, afterReturn: sB.points.length });
  // SYNTHETIC demo set
  await p.click('#planBody [data-fk="plDemo"]');
  s = await st(p);
  const label = await p.evaluate(() => (document.getElementById("plSynth") || {}).textContent || "");
  const ev2 = await evalInPage(p);
  check("U20", "demo", "SYNTHETIC demo: 12 points, 8 sites, budget 300, labelled «SYNTHETIC … не данные города» in the card and the message", s.synthetic && s.points.length === 12 && s.cands.length === 8 && s.budget === 300 && /SYNTHETIC/.test(label) && /не данные города/.test(label) && /SYNTHETIC/.test(s.planMsg) && !ev2.error,
    { label, points: s.points.length, cands: s.cands.length });
  check("U22", "general", "no console or page errors on the editor path", errors.length === 0, errors);
  await ctx.close();
}

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  {
    const { p, ctx } = await open(browser);
    const has = await p.evaluate(() => ({ ui: !!window.CITY_PLAN_UI, calc: !!window.CITY_PLAN_CALC, btn: !!document.getElementById("planBtn"), card: !!document.getElementById("planCard"),
      hooks: !!(window.CITY_APP && window.CITY_APP.toLonLat && window.CITY_APP.setPointMode), v1: !!document.getElementById("whatifCard") }));
    await ctx.close();
    if (!has.ui || !has.calc || !has.btn || !has.card || !has.hooks) {
      check("P0", "precondition", "the build contains the K07 r8 planner (CITY_PLAN_UI, CITY_PLAN_CALC, #planBtn, #planCard, CITY_APP hooks)", false, has, false);
      await browser.close(); return finish("Planner UI not found in this build: no U/S check was run. Another API needs an adapter, not a PASS.", 3);
    }
  }
  if (!OPT.only || OPT.only === "U") await editorChecks(browser);
  if (typeof module.exports.extra === "function") await module.exports.extra(browser, { open, st, freeSpots, clickAll, setTool, setNum, active, evalInPage, check, SHOTS, OPT });
  await browser.close();
  return finish();
}
function finish(note, code) {
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K07 round-8 browser checks of the city-plan-v2 planner UI", label: OPT.label, sha: OPT.sha,
    target: OPT.appRoot ? { app_root: path.basename(path.resolve(OPT.appRoot)) } : { url: OPT.url },
    total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"),
    note: note || "Sites, costs and weights are placed by the test or come from the explicit SYNTHETIC demo set; they are not city data.", checks };
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} [${c.area}] ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 300)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  process.exitCode = code || (out.fail.length || out.test_incompatible.length ? 1 : 0);
}
module.exports = { open, st, freeSpots, clickAll, setTool, setNum, active, evalInPage, check };
if (require.main === module) main().catch((e) => { console.error(e); process.exit(2); });
