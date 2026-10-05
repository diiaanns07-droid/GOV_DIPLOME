// K07 round 5 REVIEW: browser regressions of the current BUILD viewer prototypes/city-evidence (web/index.html).
//
// Usage:
//   node k07r5_regressions.cjs --app-root <dir> [--label baseline] [--sha <commit>] [--out <dir>]
//   node k07r5_regressions.cjs --url <http(s)://…/index.html | file:///…/index.html> [--label …] [--sha …]
// <dir> is prototypes/city-evidence (containing web/) or the web/ folder itself.
// Needs Node + playwright (preinstalled Chromium). No network: corrupted inputs are served by request interception,
// the files on disk are never modified.
//
// Every check has an expectation for the BUILD baseline K04 @ 0bf27de, declared from reading its code BEFORE running
// (BASELINE_EXPECT). The summary separates "failed as expected on baseline" from unexpected results. A FAIL on another
// version is a finding for that version only after it has been run against it (pass --sha).
const path = require("path");
const fs = require("fs");
const { pathToFileURL, fileURLToPath } = require("url");
const { chromium } = require("playwright");

const BASELINE_SHA = "0bf27deb8549b325b34a9610402613d745544edb";
const BASELINE_EXPECT = {  // pass | fail | unknown, from code reading of web/app.js, web/facts.js, web/index.html @ 0bf27de
  R1: "fail", R2: "fail", R3: "pass", R4: "fail", R5a: "pass", R5b: "pass", R6: "fail", R7a: "pass", R7b: "pass",
  R8: "fail", R9: "fail", R10: "fail", R11: "fail", R12: "unknown", R13: "fail", R14: "pass", R15: "pass", R16: "pass", R17: "pass",
};

// ---------------- arguments ----------------
function args() {
  const a = process.argv.slice(2), o = { label: "run", sha: null, out: null, appRoot: null, url: null };
  for (let i = 0; i < a.length; i++) {
    const k = a[i], v = a[i + 1];
    if (k === "--app-root") { o.appRoot = v; i++; } else if (k === "--url") { o.url = v; i++; }
    else if (k === "--label") { o.label = v; i++; } else if (k === "--sha") { o.sha = v; i++; } else if (k === "--out") { o.out = v; i++; }
    else if (k === "-h" || k === "--help") { console.log(fs.readFileSync(__filename, "utf8").split("\n").slice(0, 12).join("\n")); process.exit(0); }
    else { console.error("unknown argument " + k); process.exit(2); }
  }
  if (!!o.appRoot === !!o.url) { console.error("give exactly one of --app-root or --url"); process.exit(2); }
  return o;
}
const OPT = args();
let URL_, WEB_DIR = null;
if (OPT.appRoot) {
  const r = path.resolve(OPT.appRoot);
  WEB_DIR = fs.existsSync(path.join(r, "web", "index.html")) ? path.join(r, "web") : r;
  if (!fs.existsSync(path.join(WEB_DIR, "index.html"))) { console.error("no index.html under " + r); process.exit(2); }
  URL_ = pathToFileURL(path.join(WEB_DIR, "index.html")).href;
} else {
  URL_ = OPT.url;
  if (URL_.startsWith("file:")) WEB_DIR = path.dirname(fileURLToPath(URL_));
}
const OUT = path.resolve(OPT.out || path.join(__dirname, "..", "results", OPT.label));
const SHOTS = path.join(OUT, "screenshots");

const checks = [];
function check(id, scenario, expect, ok, observed) {
  checks.push({ id, scenario, expect, ok: !!ok, observed: observed === undefined ? null : observed, baseline_expectation: BASELINE_EXPECT[id] || "unknown" });
}

// original bytes of a web file (for corrupted variants)
async function original(route, name) {
  if (WEB_DIR) return fs.readFileSync(path.join(WEB_DIR, name), "utf8");
  const r = await route.fetch(); return await r.text();
}
function jsonOf(js) { const i = js.indexOf("{"), j = js.lastIndexOf("}"); return { head: js.slice(0, i), obj: JSON.parse(js.slice(i, j + 1)), tail: js.slice(j + 1) }; }

// ---------------- page helpers ----------------
async function open(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1400, height: 900 } });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  p.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  if (opts.routes) for (const [pattern, fn] of opts.routes) await p.route(pattern, fn);
  await p.goto(URL_);
  if (!opts.noWait) await p.waitForSelector("#map g[data-id]", { timeout: 15000 });
  return { p, ctx, errors };
}
const st = (p) => p.evaluate(() => {
  const A = window.CITY_APP, S = A.state;
  const tip = document.getElementById("tip");
  return { city: S.city, point: S.point, selected: S.selected, pointMode: S.pointMode,
    selEmpty: !document.getElementById("selEmpty").hidden, selBody: document.getElementById("selBody").textContent,
    tipVisible: getComputedStyle(tip).display !== "none", tipText: tip.textContent,
    crosshair: [...document.querySelectorAll("#map path")].filter((e) => /^M[-\d.]+ [-\d.]+H/.test(e.getAttribute("d") || "")).length,
    markers: document.querySelectorAll("#map g[data-id]").length };
});
async function mapToTop(p) { await p.evaluate(() => document.querySelector(".mapwrap").scrollIntoView({ block: "start" })); }
// a marker whose centre is really on top (not covered by another marker or label)
async function topMarker(p) {
  await mapToTop(p);
  return p.evaluate(() => {
    for (const g of [...document.querySelectorAll("#map g[data-id]")].reverse()) {
      const r = g.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
      if (x > 0 && y > 0 && x < innerWidth && y < innerHeight && g.contains(document.elementFromPoint(x, y)))
        return { x, y, id: g.dataset.id, name: g.getAttribute("aria-label") };
    }
    return null;
  });
}
async function hover(p, m) { await p.mouse.move(m.x - 30, m.y - 30); await p.mouse.move(m.x, m.y, { steps: 6 }); }
// an empty spot of the K10 square (topmost element is the square's background rect), searched from the centre outwards
async function emptySpot(p, noScroll) {
  if (!noScroll) await mapToTop(p);
  return p.evaluate(() => {
    // centre of the VISIBLE part of the map (the page is not scrolled when noScroll is set)
    const svg = document.getElementById("map"), r = svg.getBoundingClientRect();
    const top = Math.max(r.top, 0), bottom = Math.min(r.bottom, innerHeight), cx = r.left + r.width / 2, cy = (top + bottom) / 2;
    for (let d = 0; d < Math.min(r.width, bottom - top) / 2; d += 7) for (const [dx, dy] of [[d, 0], [-d, 0], [0, d], [0, -d], [d, d], [-d, -d], [d, -d], [-d, d]]) {
      const x = cx + dx, y = cy + dy; if (y < top || y > bottom) continue;
      const e = document.elementFromPoint(x, y);
      if (e && e.tagName === "rect" && e.closest("#map") && !e.closest("g[data-id]")) return { x, y };
    }
    return null;
  });
}
async function roadSpot(p) {
  await mapToTop(p);
  return p.evaluate(() => {
    const svg = document.getElementById("map"), r = svg.getBoundingClientRect();
    for (let y = r.top + 20; y < Math.min(r.bottom, innerHeight) - 20; y += 9) for (let x = r.left + 20; x < r.right - 60; x += 9) {
      const e = document.elementFromPoint(x, y);
      if (e && e.tagName === "path" && (e.getAttribute("aria-label") || "").startsWith("Дорога")) return { x, y };
    }
    return null;
  });
}
async function setPoint(p, noScroll) {
  if ((await p.getAttribute("#pointBtn", "aria-pressed")) !== "true") await p.click("#pointBtn");
  const s = await emptySpot(p, noScroll); if (!s) return false;
  await p.mouse.click(s.x, s.y);
  return (await st(p)).point !== null;
}
async function otherCity(p) { return p.evaluate(() => [...document.querySelectorAll("#citySeg button")].map((b) => b.dataset.city).find((c) => c !== window.CITY_APP.state.city)); }

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();

  // ===== S1 stale tooltip =====
  // The action (filter change / zoom / city switch) and the tooltip read happen in ONE JS task, so Chromium's own
  // hover update after a re-render cannot hide or overwrite the tooltip in between: the check tests the viewer's logic.
  // What a user sees 300 ms later (after that hover update) is stored as observed.after_300ms for information.
  {
    const { p, ctx, errors } = await open(browser);
    const actInPage = (sel, how) => p.evaluate(([sel, how]) => {
      const tip = document.getElementById("tip"), el = document.querySelector(sel);
      if (how === "uncheck") { el.checked = false; el.dispatchEvent(new Event("change", { bubbles: true })); } else el.click();
      return { visible: getComputedStyle(tip).display !== "none", text: tip.textContent };
    }, [sel, how]);
    const later = async () => { await p.waitForTimeout(300); const s = await st(p); return s.tipVisible ? s.tipText : null; };
    let m = await topMarker(p); await hover(p, m);
    const before = (await st(p)).tipText;
    const grp = await p.evaluate((id) => window.CITY_EVIDENCE.cities[window.CITY_APP.state.city].places.find((x) => x.id === id).group, m.id);
    let r = await actInPage(`input[data-group="${grp}"]`, "uncheck");
    check("R1", "S1 stale tooltip", "a filter change hides the hovered object's group -> its tooltip is hidden in the same re-render (precondition: tooltip was visible)",
      before !== "" && !(r.visible && r.text === before), { before, after_same_task: r.visible ? r.text : null, after_300ms: await later(), group: grp });
    await p.check(`input[data-group="${grp}"]`);
    m = await topMarker(p); await hover(p, m);
    const before2 = (await st(p)).tipText;
    r = await actInPage("#zIn", "click");
    check("R2", "S1 stale tooltip", "zoom re-renders the map (the hovered marker moves) -> its tooltip is hidden in the same re-render",
      before2 !== "" && !(r.visible && r.text === before2), { before: before2, after_same_task: r.visible ? r.text : null, after_300ms: await later() });
    m = await topMarker(p); await hover(p, m);
    const before3 = (await st(p)).tipText, oc = await otherCity(p);
    r = await actInPage(`#citySeg button[data-city="${oc}"]`, "click");
    check("R3", "S1 stale tooltip", "city switch -> tooltip of the previous city is hidden in the same re-render",
      before3 !== "" && !r.visible, { before: before3, after_same_task: r.visible ? r.text : null, after_300ms: await later() });
    check("R17", "S8 general", "no console or page errors on the normal path (S1)", errors.length === 0, errors);
    await ctx.close();
  }

  // ===== S2 clearing the point / S3 city switch with point and road =====
  {
    const { p, ctx } = await open(browser);
    const ok = await setPoint(p);
    const clear = p.locator("button", { hasText: /Сбросить|Очистить/ });
    const hasClear = (await clear.count()) > 0;
    if (hasClear) await clear.first().click(); else await p.keyboard.press("Escape");
    let s = await st(p);
    check("R4", "S2 clear point", "a set point can be cleared (button or Escape): no crosshair, empty card", ok && s.point === null && s.crosshair === 0 && s.selEmpty,
      { pointWasSet: ok, hasClearButton: hasClear, point: s.point, crosshair: s.crosshair });
    await p.screenshot({ path: path.join(SHOTS, "S2_after_clear_attempt.png") });
    // city switch with a point
    if ((await st(p)).point === null) await setPoint(p);
    const had = (await st(p)).point !== null, oc = await otherCity(p);
    await p.click(`#citySeg button[data-city="${oc}"]`);
    s = await st(p);
    check("R5a", "S3 city switch", "switching city with a point set -> point, crosshair and card of the old city are gone", had && s.point === null && s.crosshair === 0 && s.selEmpty && s.selBody === "",
      { hadPoint: had, point: s.point, crosshair: s.crosshair, card: s.selBody.slice(0, 40) });
    // city switch with a road selected
    if ((await p.getAttribute("#pointBtn", "aria-pressed")) === "true") await p.click("#pointBtn");
    const rs = await roadSpot(p);
    if (rs) await p.mouse.click(rs.x, rs.y);
    const hadSeg = (await st(p)).selected && (await st(p)).selected.type === "segment";
    const back = await otherCity(p);
    await p.click(`#citySeg button[data-city="${back}"]`);
    s = await st(p);
    check("R5b", "S3 city switch", "switching city with a road card open -> card cleared", hadSeg && s.selected === null && s.selEmpty, { hadSegment: hadSeg, selected: s.selected });
    await ctx.close();
  }

  // ===== S4 filters and layers keep no orphan selection =====
  {
    const { p, ctx } = await open(browser);
    const rs = await roadSpot(p); if (rs) await p.mouse.click(rs.x, rs.y);
    const hadSeg = (await st(p)).selected && (await st(p)).selected.type === "segment";
    await p.uncheck("#tRoads");
    let s = await st(p);
    check("R6", "S4 filters/layers", "roads layer switched off while a road card is open -> no orphan road card", hadSeg && (s.selected === null || s.selected.type !== "segment"),
      { hadSegment: hadSeg, selected: s.selected, card: s.selBody.slice(0, 40) });
    await p.check("#tRoads");
    await p.locator("#tbl tr").first().click();
    const id = (await st(p)).selected.id;
    const grp = await p.evaluate((i) => window.CITY_EVIDENCE.cities[window.CITY_APP.state.city].places.find((x) => x.id === i).group, id);
    await p.uncheck(`input[data-group="${grp}"]`);
    s = await st(p);
    check("R7a", "S4 filters/layers", "category of the selected object switched off -> selection cleared", s.selected === null, { group: grp, selected: s.selected });
    await p.check(`input[data-group="${grp}"]`);
    await p.locator("#tbl tr").first().click();
    await p.uncheck("#tPlaces");
    s = await st(p);
    check("R7b", "S4 filters/layers", "objects layer switched off -> selected object cleared", s.selected === null && s.markers === 0, { selected: s.selected, markers: s.markers });
    await ctx.close();
  }

  // ===== S5 keyboard =====
  {
    const { p, ctx } = await open(browser);
    const t = await p.evaluate(() => {
      const all = [...document.querySelectorAll("a[href], button, input, select, summary, [tabindex]")].filter((e) => e.tabIndex >= 0 && !e.disabled);
      return { toZoom: all.findIndex((e) => e.id === "zIn"), toTable: all.findIndex((e) => e.closest && e.closest("#tbl")),
        mapStops: all.filter((e) => e.closest && e.closest("#map")).length,
        skipLink: [...document.querySelectorAll("a[href^='#']")].some((a) => /табли/i.test(a.textContent)) };
    });
    check("R8", "S5 keyboard", "the table and zoom are reachable without tabbing through every map feature (skip link or < 40 stops)", t.skipLink || t.toTable < 40, t);
    await p.click("#pointBtn");
    const focusable = await p.evaluate(() => { const m = document.getElementById("map"); m.focus(); return document.activeElement === m; });
    if (focusable) await p.keyboard.press("Enter");
    const s = await st(p);
    check("R9", "S5 keyboard", "a point can be set without a mouse (focusable map + Enter)", focusable && s.point !== null, { mapFocusable: focusable, point: s.point });
    const role = await p.getAttribute("#map", "role");
    check("R10", "S5 keyboard", "interactive markers are not hidden from assistive tech (map svg role is not 'img')", role !== "img", { role });
    await ctx.close();
  }

  // ===== S6 390 px =====
  {
    const { p, ctx } = await open(browser, { viewport: { width: 390, height: 844 } });
    // natural path: press the toolbar button, then tap the visible part of the map without scrolling
    const ok = await setPoint(p, true);
    const v = await p.evaluate(() => {
      const h = document.querySelector("#selBody h3"), r = h ? h.getBoundingClientRect() : null;
      const hint = [...document.querySelectorAll(".mapwrap *")].some((e) => !e.closest("svg") && e.offsetParent !== null && /Точка|точк/.test(e.textContent));
      return { scrollY, resultHeadingTop: r && Math.round(r.top), viewportHeight: innerHeight, resultVisible: !!r && r.top >= 0 && r.bottom <= innerHeight, hintNextToMap: hint };
    });
    check("R11", "S6 390px", "on 390 px, after tapping the map without scrolling, the point result is visible or announced next to the map", ok && (v.resultVisible || v.hintNextToMap), { pointSet: ok, ...v });
    await p.locator("#tbl tr").first().click();
    const clipped = await p.evaluate(() => [...document.querySelectorAll(".card, .tablewrap")].filter((c) => !c.hidden && c.offsetParent !== null && c.scrollWidth > c.clientWidth + 1)
      .map((c) => ({ box: c.className, card: (c.closest(".card").querySelector("h2, summary") || {}).textContent, scrollWidth: c.scrollWidth, clientWidth: c.clientWidth })));
    check("R12", "S6 390px", "cards and tables fit 390 px without hidden columns (no inner horizontal scroll)", clipped.length === 0, clipped);
    await p.screenshot({ path: path.join(SHOTS, "S6_390_full.png"), fullPage: true });
    await ctx.close();
  }

  // ===== S7 missing / corrupted data and evidence (served by interception, files untouched) =====
  {
    // R13 evidence.js of another data version: SHA256 of places and data_version changed
    const { p, ctx, errors } = await open(browser, { routes: [["**/evidence.js", async (route) => {
      const { head, obj, tail } = jsonOf(await original(route, "evidence.js"));
      for (const c of Object.values(obj.cities)) for (const o of c.observations) {
        if (o.data_version) o.data_version = o.data_version.replace(/-[0-9a-f]{7}$/, "-0000000");
        if (o.source && /places_social/.test(o.source.path || "")) o.source.sha256 = "0".repeat(64);
      }
      await route.fulfill({ contentType: "application/javascript", body: head + JSON.stringify(obj) + tail });
    }]] });
    const txt = await p.textContent("main");
    check("R13", "S7 data/evidence", "evidence.js built from another data version (SHA256/data_version differ from data.js) -> the viewer warns instead of using it silently",
      /не совпада|несоответств|другой верси|устарел|mismatch/i.test(txt), { warningShown: /не совпада|несоответств|другой верси|устарел|mismatch/i.test(txt), errors });
    await p.screenshot({ path: path.join(SHOTS, "S7_evidence_other_version.png") });
    await ctx.close();
  }
  {
    const { p, ctx, errors } = await open(browser, { routes: [["**/evidence.js", async (route) => {
      const s = await original(route, "evidence.js"); await route.fulfill({ contentType: "application/javascript", body: s.slice(0, Math.floor(s.length / 2)) });
    }]] });
    const txt = await p.textContent("main"), rows = await p.locator("#tbl tr").count();
    check("R14", "S7 data/evidence", "truncated evidence.js -> explicit 'catalog unavailable', districts not invented, table still works",
      /Каталог фактов недоступен/.test(txt) && rows > 0 && !/Әл-Фараби|Еңбекші|Аль-Фараби|Енбекши/.test(await p.textContent("#tbl")), { rows, errors: errors.slice(0, 2) });
    await ctx.close();
  }
  {
    const { p, ctx, errors } = await open(browser, { noWait: true, routes: [["**/data.js", async (route) => {
      const s = await original(route, "data.js"); await route.fulfill({ contentType: "application/javascript", body: s.slice(0, Math.floor(s.length / 2)) });
    }]] });
    await p.waitForTimeout(300);
    const txt = await p.textContent("main");
    check("R15", "S7 data/evidence", "truncated data.js -> clear 'data not found' state, no map from partial data",
      /Данные не найдены/.test(txt) && (await p.locator("#map g[data-id]").count()) === 0, { text: txt.slice(0, 80), errors: errors.slice(0, 2) });
    await p.screenshot({ path: path.join(SHOTS, "S7_truncated_data.png") });
    await ctx.close();
  }
  {
    const { p, ctx, errors } = await open(browser, { routes: [["**/evidence.js", async (route) => {
      const { head, obj, tail } = jsonOf(await original(route, "evidence.js"));
      // ADAPTER (BUILD r6): in the v1.2 build the school observation is "overture_place_records.school.conf_ge_*"
      // (round-4 name "places.school" no longer exists, so the original removed nothing). Same invariant: no school number.
      for (const c of Object.values(obj.cities)) c.observations = c.observations.filter((o) => o.indicator_id !== "places.school" && !/^overture_place_records\.school\./.test(o.indicator_id));
      await route.fulfill({ contentType: "application/javascript", body: head + JSON.stringify(obj) + tail });
    }]] });
    const ex = await p.textContent("#explainBody");
    const schoolRow = await p.evaluate(() => [...document.querySelectorAll("#explainBody tr")].map((r) => r.textContent).find((t) => /^Школа/.test(t)) || null);
    check("R16", "S7 data/evidence", "evidence.js without the school observation -> explicit error or 'нет данных', never a number for schools",
      /Ошибка|нет данных/.test(ex) && (!schoolRow || /нет данных/.test(schoolRow)), { explain: ex.slice(0, 120), schoolRow, errors: errors.slice(0, 2) });
    await ctx.close();
  }

  // normal screenshot
  {
    const { p, ctx } = await open(browser);
    await p.screenshot({ path: path.join(SHOTS, "S0_overview_1400.png") });
    await ctx.close();
  }
  await browser.close();

  const failed = checks.filter((c) => !c.ok);
  const out = {
    kind: "K07 round-5 browser regressions of prototypes/city-evidence", label: OPT.label, sha: OPT.sha,
    target: OPT.appRoot ? { app_root: path.basename(path.resolve(OPT.appRoot)) } : { url: OPT.url },
    baseline_sha: BASELINE_SHA, total: checks.length, passed: checks.length - failed.length,
    failed: failed.map((c) => c.id),
    vs_baseline_expectation: {
      failed_as_expected: failed.filter((c) => c.baseline_expectation === "fail").map((c) => c.id),
      failed_unexpected: failed.filter((c) => c.baseline_expectation === "pass").map((c) => c.id),
      failed_unknown_expectation: failed.filter((c) => c.baseline_expectation === "unknown").map((c) => c.id),
      passed_although_expected_fail: checks.filter((c) => c.ok && c.baseline_expectation === "fail").map((c) => c.id),
    },
    note: "baseline_expectation describes K04 @ 0bf27de only. For another version a FAIL is a finding of that version only if this run used it (see sha).",
    checks,
  };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.ok ? "PASS" : "FAIL"} ${c.id} [${c.scenario}] (baseline expect: ${c.baseline_expectation}) ${c.expect}${c.ok ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 200)}`);
  console.log(`${out.passed}/${out.total} passed · ${OUT}`);
})().catch((e) => { console.error(e); process.exit(2); });
