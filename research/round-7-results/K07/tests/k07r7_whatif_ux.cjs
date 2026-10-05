// K07 round 7: UX checks of the "если добавить объект" scenario UI (whatif_ui.js + app.js hooks).
// Usage: node k07r7_whatif_ux.cjs --app-root <dir with web/> | --url <index.html URL> [--label …] [--sha …] [--out …]
// The UI is tested WITHOUT a distance engine (the table must say so) and with an explicitly SYNTHETIC fixture engine
// injected only by this test (W13b, W14) to check how engine output is rendered. No numbers of the fixture are real distances.
// Verdicts: PASS | FAIL | TEST_INCOMPATIBLE (precondition not met — never PASS). Needs Node + playwright (Chromium).
const path = require("path");
const fs = require("fs");
const { pathToFileURL } = require("url");
const { chromium } = require("playwright");

function args() {
  const a = process.argv.slice(2), o = { label: "run", sha: null, out: null, appRoot: null, url: null };
  for (let i = 0; i < a.length; i++) {
    const k = a[i], v = a[i + 1];
    if (k === "--app-root") { o.appRoot = v; i++; } else if (k === "--url") { o.url = v; i++; }
    else if (k === "--label") { o.label = v; i++; } else if (k === "--sha") { o.sha = v; i++; } else if (k === "--out") { o.out = v; i++; }
    else { console.error("unknown argument " + k); process.exit(2); }
  }
  if (!!o.appRoot === !!o.url) { console.error("give exactly one of --app-root or --url"); process.exit(2); }
  return o;
}
const OPT = args();
let URL_;
if (OPT.appRoot) {
  const r = path.resolve(OPT.appRoot), w = fs.existsSync(path.join(r, "web", "index.html")) ? path.join(r, "web") : r;
  URL_ = pathToFileURL(path.join(w, "index.html")).href;
} else URL_ = OPT.url;
const OUT = path.resolve(OPT.out || path.join(__dirname, "..", "results", OPT.label));
const SHOTS = path.join(OUT, "screenshots");
const checks = [];
function check(id, area, expect, ok, observed, precondition) {
  const verdict = precondition === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL";
  checks.push({ id, area, expect, verdict, observed: observed === undefined ? null : observed });
}

// FEATURE_SPEC city-whatif-v1 caption for a control point without source records
const NO_SOURCE_TEXT_EXPECTED = "В срезе нет исходных записей; улучшение не вычисляется";
// SYNTHETIC fixture engine for W13b/W14 only: values are made up per control point index, NOT distances
const FIXTURE_ENGINE = `window.CITY_WHATIF_ENGINE = { fixture: "SYNTHETIC k07r7 — not a distance engine", compute({ scenario }) {
  return { rows: scenario.control_points.map((p, i) => i === 1
      ? { control_point_id: p.id, before_m: null, after_m: scenario.proposed_object ? 640 : null, delta_m: null, nearest_before: null }
      : { control_point_id: p.id, before_m: 1500 + i, after_m: scenario.proposed_object ? 400 + i : 1500 + i, delta_m: scenario.proposed_object ? 1100 : 0,
          nearest_before: { record_id: "fixture-" + i, name: "Fixture school " + i, source: "SYNTHETIC fixture", qa: i === 2 ? ["COLOCATED"] : [] } }),
    notes: ["SYNTHETIC fixture engine (test only)"] }; } };`;

async function open(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1400, height: 900 } });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  p.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  if (opts.engine) await p.addInitScript(FIXTURE_ENGINE);
  await p.goto(URL_);
  await p.waitForSelector("#map g[data-id]", { timeout: 15000 });
  return { p, ctx, errors };
}
const ws = (p) => p.evaluate(() => {
  const U = window.CITY_WHATIF_UI, S = U && U._state;
  return S ? { active: S.active, tool: S.tool, category: S.category, city: S.city, points: S.points.map((x) => ({ ...x })), proposed: S.proposed && { ...S.proposed },
    pending: S.pending, msg: (document.getElementById("wiMsg") || {}).textContent || "", mapMsg: (document.getElementById("wiMapMsg") || {}).textContent || "",
    listItems: document.querySelectorAll("#wiList li[data-wi-point]").length,
    layerPoints: document.querySelectorAll('#map [data-whatif^="cp-"]').length, layerProposed: document.querySelectorAll('#map [data-whatif="proj-1"]').length,
    cardHidden: document.getElementById("whatifCard").hidden, selected: window.CITY_APP.state.selected } : null;
});
async function mapToTop(p) { await p.evaluate(() => document.querySelector(".mapwrap").scrollIntoView({ block: "start" })); }
// free spots inside the K10 square: topmost element is not a data marker, a scenario marker or a label
async function freeSpots(p, n, offset = 0) {
  await mapToTop(p);
  return p.evaluate(([n, offset]) => {
    const sq = document.querySelector('#map rect[stroke-dasharray="6 4"]').getBoundingClientRect(), out = [];
    const top = Math.max(sq.top, 0) + 12, bottom = Math.min(sq.bottom, innerHeight) - 12;
    for (let y = top + offset; y < bottom && out.length < n; y += 37) for (let x = sq.left + 14 + offset; x < sq.right - 14 && out.length < n; x += 41) {
      const e = document.elementFromPoint(x, y);
      if (!e || !e.closest("#map") || e.closest("g[data-id]") || e.closest("[data-whatif]") || e.tagName === "text") continue;
      if (out.some((q) => Math.hypot(q.x - x, q.y - y) < 30)) continue;
      out.push({ x, y });
    }
    return out;
  }, [n, offset]);
}
// before/after table: every cell inside the scenario card (no clipped column), page without horizontal scroll
async function tableFit(p) {
  await p.locator("#wiResult").scrollIntoViewIfNeeded();
  return p.evaluate((NO) => {
    const card = document.getElementById("whatifCard"), iw = innerWidth, cr = card.getBoundingClientRect();
    const cells = [...document.querySelectorAll("#wiResult td")];
    const outside = cells.filter((c) => { const r = c.getBoundingClientRect(); return r.right > cr.right + 1 || r.left < cr.left - 1; }).length;
    const labels = cells.slice(0, 5).map((c) => getComputedStyle(c, "::before").content);
    const thead = document.querySelector("#wiResult thead"), headShown = !!thead && thead.getBoundingClientRect().width > 2;
    return { rows: document.querySelectorAll("#wiResult tbody tr").length, cells: cells.length, outside, cardOverflow: card.scrollWidth > card.clientWidth + 1,
      pageScroll: document.documentElement.scrollWidth > iw, noSourceShown: cells.some((c) => c.textContent === NO),
      labelled: headShown || labels.every((l) => l && l !== "none" && l !== "normal"), headShown, labels };
  }, NO_SOURCE_TEXT_EXPECTED);
}
async function outsideSpot(p) {
  await mapToTop(p);
  return p.evaluate(() => {
    const sq = document.querySelector('#map rect[stroke-dasharray="6 4"]').getBoundingClientRect(), m = document.getElementById("map").getBoundingClientRect();
    const x = (m.left + sq.left) / 2, y = Math.min(sq.top + sq.height / 2, innerHeight - 20);
    return sq.left - m.left > 20 ? { x, y } : null;
  });
}

function finish(extraNote) {
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K07 round-7 UX checks of the what-if scenario UI", label: OPT.label, sha: OPT.sha,
    target: OPT.appRoot ? { app_root: path.basename(path.resolve(OPT.appRoot)) } : { url: OPT.url },
    total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"),
    note: extraNote || "W13b and W14 use a SYNTHETIC fixture engine injected by the test; its numbers are not distances.", checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} [${c.area}] ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 240)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  return out;
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();

  // ===== precondition: the build has this UI (window.CITY_WHATIF_UI + #whatifBtn + app hooks) =====
  {
    const { p, ctx } = await open(browser);
    const has = await p.evaluate(() => ({ ui: !!window.CITY_WHATIF_UI, btn: !!document.getElementById("whatifBtn"), card: !!document.getElementById("whatifCard"),
      hooks: !!(window.CITY_APP && window.CITY_APP.toLonLat && window.CITY_APP.renderMap) }));
    await ctx.close();
    if (!has.ui || !has.btn || !has.card || !has.hooks) {
      check("W0", "precondition", "the build contains the K07 r7 scenario UI (window.CITY_WHATIF_UI, #whatifBtn, #whatifCard, CITY_APP hooks)", false, has, false);
      await browser.close();
      finish("Scenario UI not found in this build: no W check was run. A build with another API needs an adapter, not a PASS.");
      process.exit(3);
    }
  }

  // ===== mode, placement, limits, move, delete, bbox, data markers =====
  {
    const { p, ctx, errors } = await open(browser);
    const pre = !!(await ws(p));
    let s = pre ? await ws(p) : null;
    const spots0 = await freeSpots(p, 1);
    if (spots0.length) await p.mouse.click(spots0[0].x, spots0[0].y);
    s = pre ? await ws(p) : null;
    check("W1", "mode", "scenario mode is off by default: card hidden, a map click creates no scenario item", pre && s.cardHidden && !s.active && s.points.length === 0 && !s.proposed, s && { cardHidden: s.cardHidden, points: s.points.length }, pre);
    await p.click("#whatifBtn");
    const spots = await freeSpots(p, 12, 3);
    for (const q of spots.slice(0, 3)) await p.mouse.click(q.x, q.y);
    s = await ws(p);
    check("W2", "placement", "with the mode on, 3 clicks give 3 control points in the list and on the map", s.active && s.points.length === 3 && s.listItems === 3 && s.layerPoints === 3, { points: s.points.length, list: s.listItems, layer: s.layerPoints, msg: s.msg });
    for (const q of spots.slice(3, 11)) await p.mouse.click(q.x, q.y);
    s = await ws(p);
    const atLimit = s.points.length;
    check("W3", "placement", "at most 10 control points: the 11th click is refused with a message, the count stays 10",
      spots.length >= 11 && atLimit === 10 && /Не больше 10/.test(s.msg), { clicks: Math.min(spots.length, 11), points: atLimit, msg: s.msg }, spots.length >= 11);
    // delete
    const delId = s.points[4].id;
    await p.click(`button[data-wi-del="${delId}"]`);
    s = await ws(p);
    check("W4", "delete", "«Удалить» removes exactly that point from the list and the map", s.points.length === 9 && !s.points.some((x) => x.id === delId) && s.layerPoints === 9 && s.listItems === 9, { deleted: delId, points: s.points.length, layer: s.layerPoints });
    // move
    const mvId = s.points[0].id, before = { ...s.points[0] };
    await p.click(`button[data-wi-move="${mvId}"]`);
    const pendingOk = (await ws(p)).pending && (await ws(p)).pending.id === mvId;
    const free = await freeSpots(p, 1, 19);
    if (free.length) await p.mouse.click(free[0].x, free[0].y);
    s = await ws(p);
    const after = s.points.find((x) => x.id === mvId);
    check("W5", "move", "«Переместить» + click moves that point (same id, new coordinates), count unchanged", pendingOk && after && (after.lon !== before.lon || after.lat !== before.lat) && s.points.length === 9 && !s.pending,
      { id: mvId, before, after, points: s.points.length });
    // proposed object: place, place again (moves, still one), delete
    await p.check('input[name="wiTool"][value="proposed"]');
    const pr = await freeSpots(p, 2, 11);
    await p.mouse.click(pr[0].x, pr[0].y);
    const p1 = (await ws(p)).proposed;
    await p.mouse.click(pr[1].x, pr[1].y);
    s = await ws(p);
    const moved = s.proposed && p1 && (s.proposed.lon !== p1.lon || s.proposed.lat !== p1.lat);
    check("W6a", "proposed", "one proposed object: a second placement moves it (layer shows exactly 1)", !!p1 && moved && s.layerProposed === 1 && s.points.length === 9, { first: p1, now: s.proposed, layer: s.layerProposed });
    await p.click("#wiProjDel");
    s = await ws(p);
    check("W6b", "proposed", "deleting the proposed object returns to baseline (no project on map or in the card)", !s.proposed && s.layerProposed === 0 && /исходный вариант/.test(s.msg), { proposed: s.proposed, msg: s.msg });
    await p.screenshot({ path: path.join(SHOTS, "W_1400_scenario.png") });
    // outside the square
    const out = await outsideSpot(p);
    const n0 = (await ws(p)).points.length;
    await p.check('input[name="wiTool"][value="control"]');
    if (out) await p.mouse.click(out.x, out.y);
    s = await ws(p);
    check("W7", "bbox", "a click outside the K10 square is refused with a message and changes nothing", !!out && s.points.length === n0 && !s.proposed && /Вне квадрата/.test(s.msg), { points: s.points.length, msg: s.msg }, !!out);
    // data marker click selects the object and places nothing. The map has focus first: on the first r7 run a re-render on
    // svg blur replaced the marker between pointerdown and click, so the click was lost (kept as a regression case).
    const n1 = (await ws(p)).points.length;
    await p.focus("#map");
    const mapFocusedBefore = await p.evaluate(() => document.activeElement === document.getElementById("map"));
    const mk = await p.evaluate(() => { for (const g of [...document.querySelectorAll("#map g[data-id]")].reverse()) { const r = g.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2; if (g.contains(document.elementFromPoint(x, y))) return { x, y, id: g.dataset.id }; } return null; });
    if (mk) await p.mouse.click(mk.x, mk.y);
    s = await ws(p);
    check("W8", "explicit placement", "in scenario mode a click on an object marker selects the object and creates no scenario point", !!mk && s.points.length === n1 && s.selected && s.selected.type === "place" && s.selected.id === mk.id, { mapFocusedBefore, points: s.points.length, selected: s.selected }, !!mk && mapFocusedBefore);
    // base point mode is exclusive
    await p.click("#pointBtn");
    s = await ws(p);
    const baseOn = await p.evaluate(() => window.CITY_APP.state.pointMode);
    await p.click("#whatifBtn");
    const s2 = await ws(p), baseAfter = await p.evaluate(() => window.CITY_APP.state.pointMode);
    check("W11", "explicit placement", "«Расстояние от точки» and the scenario mode exclude each other", baseOn && !s.active && s2.active && !baseAfter, { baseOn, scenarioAfterBase: s.active, scenarioOn: s2.active, baseAfter });
    // category change resets
    await p.selectOption("#wiCat", "outpatient_clinic");
    s = await ws(p);
    check("W10", "reset", "category change resets the scenario and says why", s.points.length === 0 && !s.proposed && /смена категории/.test(s.msg) && s.category === "outpatient_clinic", { points: s.points.length, msg: s.msg });
    // city switch resets, points are not carried, switching back does not restore
    const sp = await freeSpots(p, 2, 7);
    for (const q of sp) await p.mouse.click(q.x, q.y);
    const had = (await ws(p)).points.length;
    const other = await p.evaluate(() => [...document.querySelectorAll("#citySeg button")].map((b) => b.dataset.city).find((c) => c !== window.CITY_APP.state.city));
    await p.click(`#citySeg button[data-city="${other}"]`);
    s = await ws(p);
    const back = await p.evaluate(() => [...document.querySelectorAll("#citySeg button")].map((b) => b.dataset.city).find((c) => c !== window.CITY_APP.state.city));
    await p.click(`#citySeg button[data-city="${back}"]`);
    const s3 = await ws(p);
    check("W9", "reset", "city switch resets the scenario with a reason; points are not carried to the other city nor restored on return",
      had === 2 && s.points.length === 0 && s.layerPoints === 0 && /смена города/.test(s.msg) && s.city === other && s3.points.length === 0, { had, afterSwitch: s.points.length, msg: s.msg, afterReturn: s3.points.length });
    check("W15", "general", "no console or page errors during the mouse path", errors.length === 0, errors);
    await ctx.close();
  }

  // ===== keyboard only =====
  {
    const { p, ctx, errors } = await open(browser);
    await p.focus("#whatifBtn"); await p.keyboard.press("Enter");
    let s = await ws(p);
    const on = s.active && !s.cardHidden;
    await p.focus('input[name="wiTool"][value="control"]'); await p.keyboard.press("Space");
    await p.focus("#map");
    const tgtShown = () => p.evaluate(() => { const t = document.querySelector('#map [data-whatif="target"]'); if (!t) return null; const r = t.getBoundingClientRect(); return getComputedStyle(t).display !== "none" && r.width > 0; });
    const target = await tgtShown();
    await p.keyboard.press("Enter");
    for (let i = 0; i < 3; i++) await p.keyboard.press("ArrowRight");
    await p.keyboard.press("Enter");
    s = await ws(p);
    const two = s.points.length === 2 && (s.points[0].lon !== s.points[1].lon);
    await p.focus(`button[data-wi-move="${s.points[0].id}"]`); await p.keyboard.press("Enter");
    const pend = (await ws(p)).pending;
    await p.focus("#map"); await p.keyboard.press("ArrowDown"); await p.keyboard.press("ArrowDown"); await p.keyboard.press("Enter");
    const s2 = await ws(p);
    const movedK = s2.points[0].lat !== s.points[0].lat && !s2.pending;
    await p.focus(`button[data-wi-move="${s2.points[1].id}"]`); await p.keyboard.press("Enter");
    await p.keyboard.press("Escape");
    const cancelled = !(await ws(p)).pending;
    await p.focus(`button[data-wi-del="${s2.points[1].id}"]`); await p.keyboard.press("Enter");
    const s3 = await ws(p);
    await p.focus('input[name="wiTool"][value="proposed"]'); await p.keyboard.press("Space");
    const targetUnfocused = await tgtShown();
    await p.focus("#map"); await p.keyboard.press("Enter");
    const s4 = await ws(p);
    check("W12", "keyboard", "keyboard only: mode on, centre target shown, Enter places, arrows+Enter place a second point, move via button+Enter, Escape cancels, delete via button, proposed via radio+Enter",
      on && target === true && targetUnfocused === false && two && pend && movedK && cancelled && s3.points.length === 1 && !!s4.proposed,
      { on, targetShownOnFocus: target, targetShownUnfocused: targetUnfocused, two, pending: !!pend, movedK, cancelled, afterDelete: s3.points.length, proposed: !!s4.proposed });
    check("W15b", "general", "no console or page errors during the keyboard path", errors.length === 0, errors);
    await ctx.close();
  }

  // ===== 390 px =====
  {
    const { p, ctx } = await open(browser, { viewport: { width: 390, height: 844 } });
    await p.click("#whatifBtn");
    const sp = await freeSpots(p, 3, 5);
    for (const q of sp) await p.mouse.click(q.x, q.y);
    const msgVis = await p.evaluate(() => { const m = document.getElementById("wiMapMsg"), r = m.getBoundingClientRect(); return { hidden: m.hidden, top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight, text: m.textContent.slice(0, 60) }; });
    await p.locator("#whatifCard").scrollIntoViewIfNeeded();
    const fit = await p.evaluate(() => {
      const card = document.getElementById("whatifCard"), iw = innerWidth;
      const ctrls = [...card.querySelectorAll("button, select, input")].filter((e) => e.offsetParent !== null).map((e) => e.getBoundingClientRect());
      return { pageScroll: document.documentElement.scrollWidth > iw, cardOverflow: card.scrollWidth > card.clientWidth + 1,
        controlsOutside: ctrls.filter((r) => r.right > iw + 1 || r.left < -1).length, controls: ctrls.length };
    });
    const s = await ws(p);
    check("W13", "390px", "390 px: points placed, placement message visible on the map, no horizontal scroll, all scenario controls inside the screen",
      s.points.length === 3 && !msgVis.hidden && msgVis.top >= 0 && msgVis.bottom <= msgVis.vh && !fit.pageScroll && !fit.cardOverflow && fit.controlsOutside === 0, { points: s.points.length, msgVis, fit });
    await p.screenshot({ path: path.join(SHOTS, "W13_390_card.png") });
    await ctx.close();
  }
  // 390 px with engine rows (SYNTHETIC fixture): long texts must wrap inside the card, labels stay readable
  {
    const { p, ctx } = await open(browser, { viewport: { width: 390, height: 844 }, engine: true });
    await p.click("#whatifBtn");
    const sp = await freeSpots(p, 3, 5);
    for (const q of sp) await p.mouse.click(q.x, q.y);
    await p.check('input[name="wiTool"][value="proposed"]');
    const pr = await freeSpots(p, 1, 23);
    if (pr.length) await p.mouse.click(pr[0].x, pr[0].y);
    const t = await tableFit(p);
    const s = await ws(p);
    check("W13b", "390px", "390 px with engine rows (SYNTHETIC fixture): every cell inside the card, no horizontal scroll, each value labelled, the no-source caption readable",
      s.points.length === 3 && !!s.proposed && t.rows === 3 && t.outside === 0 && !t.cardOverflow && !t.pageScroll && t.noSourceShown && t.labelled,
      { points: s.points.length, proposed: !!s.proposed, ...t }, s.points.length === 3 && !!s.proposed);
    await p.screenshot({ path: path.join(SHOTS, "W13b_390_engine_table.png") });
    await ctx.close();
  }

  // ===== engine output rendering =====
  {
    const { p, ctx } = await open(browser);
    await p.click("#whatifBtn");
    const sp = await freeSpots(p, 3, 9);
    for (const q of sp) await p.mouse.click(q.x, q.y);
    const noEngine = await p.textContent("#wiResult");
    await ctx.close();
    const e = await open(browser, { engine: true });
    await e.p.click("#whatifBtn");
    const sp2 = await freeSpots(e.p, 3, 9);
    for (const q of sp2) await e.p.mouse.click(q.x, q.y);
    await e.p.check('input[name="wiTool"][value="proposed"]');
    const pr = await freeSpots(e.p, 1, 23);
    await e.p.mouse.click(pr[0].x, pr[0].y);
    const rows = await e.p.evaluate(() => [...document.querySelectorAll("#wiResult tbody tr")].map((r) => [...r.cells].map((c) => c.textContent)));
    const res = await e.p.textContent("#wiResult");
    const fit = await tableFit(e.p);
    await e.p.screenshot({ path: path.join(SHOTS, "W14_fixture_engine_table.png") });
    check("W14", "result table", "without an engine the table says the calculation is not connected; with the SYNTHETIC fixture engine rows show before/after/delta, the exact no-source caption and the nearest record's source; at 1400 px (400 px side column) every cell is inside the card",
      /не подключён/.test(noEngine) && rows.length === 3 && rows[0][1] === "1,50 км" && rows[0][2] === "400 м" && rows[0][3].startsWith("−") &&
      rows[1][4] === NO_SOURCE_TEXT_EXPECTED && rows[1][3] === "—" && /SYNTHETIC fixture/.test(rows[0][4]) && /⚠ COLOCATED/.test(rows[2][4]) && /не время пешком/.test(res) &&
      fit.outside === 0 && !fit.cardOverflow && !fit.pageScroll && fit.labelled,
      { noEngine: noEngine.slice(0, 80), rows, fit });
    await e.ctx.close();
  }
  await browser.close();
  const out = finish();
  process.exitCode = out.fail.length ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
