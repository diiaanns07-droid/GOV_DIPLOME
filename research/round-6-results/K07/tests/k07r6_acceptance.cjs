// K07 round 6 REVIEW: acceptance of the BUILD viewer prototypes/city-evidence (target 064ed25 by default).
//
// ADAPTER of research/round-5-results/K07/tests/k07r5_regressions.cjs @ 56c8bff (sha256 7c614651…). Changes, each one
// justified by a TEST_INCOMPATIBLE result of the unmodified r5 test on 064ed25 (results/r5_test_unmodified/):
//   A1  no baseline expectation list: every invariant must PASS on the target; old 0bf27de XFAILs are not applied;
//   A2  R11: the status line of 064ed25 is <p id="mapStatus" role="status"> BELOW .mapwrap (r5 looked only inside
//       .mapwrap). The criterion is unchanged in substance: the result must be VISIBLE in the viewport after tapping the
//       map without scrolling (the r5 in-map hint was visible whenever the tapped map was); the live region is recorded;
//   A3  R13/R16: evidence.js format city-evidence/2 has no source.path/sha256, data_version has no commit suffix and the
//       school indicator is overture_place_records.school.*; the r5 mutations changed nothing (vacuous). New mutations
//       target the new fields; a mutation that changes nothing gives TEST_INCOMPATIBLE, never PASS;
//   A4  new: critical path of the 10-record co-located group (card / list / keyboard / 390 px) and stale explanation
//       after a city or filter change (round-6 assignment research/round-6/review/K07.txt).
// Usage: node k07r6_acceptance.cjs --app-root <dir> | --url <url>  [--label …] [--sha …] [--out …]
// Verdicts: PASS | FAIL | TEST_INCOMPATIBLE (precondition of the test not met). A skipped check is never PASS.
const path = require("path");
const fs = require("fs");
const { pathToFileURL, fileURLToPath } = require("url");
const { chromium } = require("playwright");

const TARGET_SHA = "064ed25368341edaa50289bc29e21dda7bdd9440";

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
// precondition === false -> TEST_INCOMPATIBLE (the test could not exercise the invariant), never PASS
function check(id, scenario, expect, ok, observed, precondition) {
  const verdict = precondition === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL";
  checks.push({ id, scenario, expect, verdict, ok: verdict === "PASS", observed: observed === undefined ? null : observed });
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
      const inView = (r) => !!r && r.top >= 0 && r.bottom <= innerHeight && r.height > 0;
      const h = document.querySelector("#selBody h3"), r = h ? h.getBoundingClientRect() : null;
      // A2: hint = an element inside the map (r5) or the status line next to it (064ed25: #mapStatus / role=status)
      const cands = [...document.querySelectorAll(".mapwrap *, #mapStatus, .mapcol [role=status]")]
        .filter((e) => !e.closest("svg") && e.offsetParent !== null && /Точка|точк/.test(e.textContent));
      const st = document.getElementById("mapStatus"), sr = st && st.getBoundingClientRect();
      return { scrollY, resultHeadingTop: r && Math.round(r.top), viewportHeight: innerHeight, resultVisible: inView(r),
        hintNextToMap: cands.some((e) => inView(e.getBoundingClientRect())),
        statusLine: st ? { text: st.textContent.slice(0, 80), top: Math.round(sr.top), bottom: Math.round(sr.bottom), role: st.getAttribute("role"), ariaLive: st.getAttribute("aria-live") } : null };
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
    // A3: city-evidence/2 links evidence to data through release, data_version and source.evidence (branch@sha)
    let mutated = 0;
    const { p, ctx, errors } = await open(browser, { routes: [["**/evidence.js", async (route) => {
      const { head, obj, tail } = jsonOf(await original(route, "evidence.js"));
      for (const c of Object.values(obj.cities)) {
        if (c.release) { c.release = "2026-09-30.1"; mutated++; }
        for (const o of c.observations) {
          if (o.release) { o.release = "2026-09-30.1"; mutated++; }
          if (o.data_version) { const d = o.data_version.replace(/2026-09-23\.1/, "2026-09-30.1"); if (d !== o.data_version) { o.data_version = d; mutated++; } }
          if (o.source && typeof o.source.evidence === "string") { const e = o.source.evidence.replace(/@[0-9a-f]{40}/, "@" + "0".repeat(40)); if (e !== o.source.evidence) { o.source.evidence = e; mutated++; } }
          if (o.source && o.source.sha256) { o.source.sha256 = "0".repeat(64); mutated++; }
        }
      }
      await route.fulfill({ contentType: "application/javascript", body: head + JSON.stringify(obj) + tail });
    }]] });
    const txt = await p.textContent("main");
    const warn = /не совпада|несоответств|другой верси|другого выпуска|устарел|mismatch/i.test(txt);
    check("R13", "S7 data/evidence", "evidence.js of another release / data version (release, data_version, source SHA differ from data.js) -> the viewer warns instead of using it silently",
      warn, { mutatedFields: mutated, warningShown: warn, errors }, mutated > 0);
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
    let removed = 0;
    const { p, ctx, errors } = await open(browser, { routes: [["**/evidence.js", async (route) => {
      const { head, obj, tail } = jsonOf(await original(route, "evidence.js"));
      // A3: r5 removed "places.school"; city-evidence/2 names it overture_place_records.school.*
      const isSchool = (o) => o.indicator_id === "places.school" || /^overture_place_records\.school\./.test(o.indicator_id);
      for (const c of Object.values(obj.cities)) { const n = c.observations.length; c.observations = c.observations.filter((o) => !isSchool(o)); removed += n - c.observations.length; }
      await route.fulfill({ contentType: "application/javascript", body: head + JSON.stringify(obj) + tail });
    }]] });
    const ex = await p.textContent("#explainBody");
    const schoolRow = await p.evaluate(() => [...document.querySelectorAll("#explainBody tr")].map((r) => r.textContent).find((t) => /^Школа/.test(t)) || null);
    check("R16", "S7 data/evidence", "evidence.js without the school observation -> explicit error or 'нет данных', never a number for schools",
      /Ошибка|нет данных/.test(ex) && (!schoolRow || /нет данных/.test(schoolRow)), { removedObservations: removed, explain: ex.slice(0, 120), schoolRow, errors: errors.slice(0, 2) }, removed > 0);
    await ctx.close();
  }

  // ===== G critical path: the co-located group of 10 records (Shymkent, K05-3) =====
  // every record of the group must be reachable through the object card and through the table, with the keyboard,
  // and on a 390 px screen. Records are identified by Overture id via CITY_APP.state.selected (no name matching).
  const groupOf = (p) => p.evaluate(() => {
    const ev = window.CITY_OBS, c = ev && ev.cities && ev.cities.shymkent;
    const g = c && c.qa && (c.qa.colocated || []).find((x) => x.ids.length === 10);
    return g ? { ids: g.ids, lon: g.lon, lat: g.lat } : null;
  });
  // breadth-first walk over the "other records" buttons of the object card
  async function walkCard(p, startId, ids) {
    const seen = new Set(), queue = [startId], clipped = [];
    while (queue.length) {
      const id = queue.shift(); if (seen.has(id)) continue;
      await p.evaluate((i) => window.CITY_APP.selectPlace(i), id);
      if ((await st(p)).selected?.id !== id) continue;
      seen.add(id);
      const btns = p.locator("#selBody button");
      const n = await btns.count();
      for (let k = 0; k < n; k++) {
        const b = btns.nth(k);
        await b.scrollIntoViewIfNeeded();
        const geo = await b.evaluate((e) => { const r = e.getBoundingClientRect(); const x = r.left + r.width / 2, y = r.top + r.height / 2;
          return { right: r.right, left: r.left, iw: innerWidth, top: document.elementFromPoint(x, y) === e || e.contains(document.elementFromPoint(x, y)) }; });
        if (geo.right > geo.iw + 1 || geo.left < -1 || !geo.top) clipped.push({ from: id, k, ...geo });
        await b.click();
        const sel = (await st(p)).selected;
        if (sel && sel.type === "place" && ids.includes(sel.id) && !seen.has(sel.id)) queue.push(sel.id);
        await p.evaluate((i) => window.CITY_APP.selectPlace(i), id);   // back to the card being walked
      }
    }
    return { reached: [...seen].filter((i) => ids.includes(i)).length, clipped };
  }
  async function walkTable(p, ids, viaKeyboard) {
    const got = new Set(); const rows = p.locator("#tbl tr"); const n = await rows.count();
    for (let k = 0; k < n; k++) {
      const r = rows.nth(k);
      if (viaKeyboard) { await r.focus(); await p.keyboard.press("Enter"); } else { await r.scrollIntoViewIfNeeded(); await r.click(); }
      const sel = (await st(p)).selected;
      if (sel && sel.type === "place" && ids.includes(sel.id)) got.add(sel.id);
    }
    return got.size;
  }
  for (const [vp, tag] of [[{ width: 1400, height: 900 }, "1400"], [{ width: 390, height: 844 }, "390"]]) {
    const { p, ctx, errors } = await open(browser, { viewport: vp });
    const grp = await groupOf(p);
    const pre = !!grp;
    if (tag === "1400") {
      // G1 the map marker at the group point opens a group member's card that lists the other 9 records
      await mapToTop(p);
      let g1 = null;
      if (grp) {
        const [x, y] = await p.evaluate(([lon, lat]) => { const r = document.getElementById("map").getBoundingClientRect(); const [a, b] = window.CITY_APP.toScreen ? window.CITY_APP.toScreen(lon, lat) : [null, null]; return [a === null ? null : r.left + a, r.top + b]; }, [grp.lon, grp.lat]);
        if (x !== null) await p.mouse.click(x, y);
        else {  // CITY_APP has no toScreen in 064ed25: click the topmost marker whose record belongs to the group
          const m = await p.evaluate((ids) => { for (const g of [...document.querySelectorAll("#map g[data-id]")].reverse()) if (ids.includes(g.dataset.id)) { const r = g.getBoundingClientRect(); const x = r.left + r.width / 2, y = r.top + r.height / 2; if (g.contains(document.elementFromPoint(x, y))) return { x, y }; } return null; }, grp.ids);
          if (m) await p.mouse.click(m.x, m.y);
        }
        const s1 = await st(p);
        const others = await p.locator("#selBody button").count();
        g1 = { selected: s1.selected, inGroup: !!s1.selected && grp.ids.includes(s1.selected.id), buttons: others };
      }
      check("G1", "G group of 10", "clicking the group point on the map opens a member's card listing the other 9 records", pre && g1.inGroup && g1.buttons >= 9, g1, pre);
      const c = pre ? await walkCard(p, grp.ids[0], grp.ids) : null;
      check("G2", "G group of 10", "all 10 records are reachable from the object card (buttons of the other records)", pre && c.reached === 10, c, pre);
      const t = pre ? await walkTable(p, grp.ids, false) : 0;
      check("G3", "G group of 10", "all 10 records are reachable from the table (mouse)", pre && t === 10, { reached: t }, pre);
      // G4 keyboard: skip link -> table; every row selects with Enter; card buttons work with Enter
      await p.goto(URL_); await p.waitForSelector("#map g[data-id]");
      const skip = await p.evaluate(() => { const a = [...document.querySelectorAll("a[href^='#']")].find((x) => /табли/i.test(x.textContent)); return a ? a.getAttribute("href") : null; });
      let afterSkip = null, tabsToRow = null;
      if (skip) {
        await p.focus(`a[href="${skip}"]`); await p.keyboard.press("Enter");
        afterSkip = await p.evaluate(() => document.activeElement && (document.activeElement.id || document.activeElement.tagName));
        for (let k = 1; k <= 5; k++) { await p.keyboard.press("Tab"); if (await p.evaluate(() => !!document.activeElement.closest("#tbl"))) { tabsToRow = k; break; } }
      }
      const kRows = pre ? await walkTable(p, grp.ids, true) : 0;
      let kBtn = null;
      if (pre) {
        await p.evaluate((i) => window.CITY_APP.selectPlace(i), grp.ids[0]);
        await p.locator("#selBody button").first().focus(); await p.keyboard.press("Enter");
        const sel = (await st(p)).selected; kBtn = !!sel && grp.ids.includes(sel.id) && sel.id !== grp.ids[0];
      }
      check("G4", "G group of 10", "keyboard: skip link reaches the table (≤5 Tab to a row), all 10 rows select with Enter, a card button selects with Enter",
        pre && !!skip && tabsToRow !== null && kRows === 10 && kBtn, { skip, afterSkip, tabsToRow, rowsByKeyboard: kRows, cardButtonByKeyboard: kBtn }, pre);
      check("R17b", "S8 general", "no console or page errors on the group path", errors.length === 0, errors);
    } else {
      const c = pre ? await walkCard(p, grp.ids[0], grp.ids) : null;
      const t = pre ? await walkTable(p, grp.ids, false) : 0;
      const sw = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
      check("G5", "G group of 10", "390 px: all 10 reachable via card buttons and via table, buttons fully on screen and not covered, no horizontal page scroll",
        pre && c.reached === 10 && c.clipped.length === 0 && t === 10 && sw.sw <= sw.iw, { card: c, table: t, scroll: sw }, pre);
      if (pre) { await p.evaluate((i) => window.CITY_APP.selectPlace(i), grp.ids[0]); await p.locator("#selCard").scrollIntoViewIfNeeded(); await p.screenshot({ path: path.join(SHOTS, "G5_390_group_card.png") }); }
    }
    await ctx.close();
  }

  // ===== E stale explanation after city / filter change =====
  {
    const { p, ctx } = await open(browser);
    const btn = p.locator("#explainBody button", { hasText: /Объяснить/ });
    const hasBtn = (await btn.count()) > 0;
    let e1 = null;
    if (hasBtn) {
      const before = await p.evaluate(() => window.CITY_APP.state.city);
      // click and switch city in the same task: the async reply arrives for the old city
      await p.evaluate(() => { const b = [...document.querySelectorAll("#explainBody button")].find((x) => /Объяснить/.test(x.textContent)); b.click();
        const other = [...document.querySelectorAll("#citySeg button")].find((x) => x.dataset.city !== window.CITY_APP.state.city); other.click(); });
      await p.waitForTimeout(300);
      const box = await p.evaluate(() => { const b = document.querySelector("#explainBody .explain"); return { visible: !!b && !b.hidden && b.offsetParent !== null, text: b ? b.textContent.slice(0, 120) : "" }; });
      e1 = { from: before, to: await p.evaluate(() => window.CITY_APP.state.city), box };
    }
    check("E1", "E explanation", "an explanation requested before a city switch is not shown for the new city", hasBtn && !e1.box.visible, e1, hasBtn);
    let e2 = null;
    if (hasBtn) {
      await p.locator("#explainBody button", { hasText: /Объяснить/ }).click();
      await p.waitForSelector("#explainBody .explain:not([hidden])", { timeout: 3000 }).catch(() => {});
      const shown = await p.evaluate(() => { const b = document.querySelector("#explainBody .explain"); return !!b && !b.hidden; });
      const g = await p.evaluate(() => [...document.querySelectorAll("input[data-group]")].find((x) => x.checked).dataset.group);
      await p.uncheck(`input[data-group="${g}"]`);
      await p.waitForTimeout(200);
      const after = await p.evaluate(() => { const b = document.querySelector("#explainBody .explain"); return { visible: !!b && !b.hidden && b.offsetParent !== null, text: b ? b.textContent.slice(0, 80) : "" }; });
      e2 = { explanationShownBeforeFilter: shown, filterOff: g, after };
    }
    check("E2", "E explanation", "after a category filter change the previous explanation is not left on screen", hasBtn && e2.explanationShownBeforeFilter && !e2.after.visible, e2, hasBtn && !!(e2 && e2.explanationShownBeforeFilter));
    await ctx.close();
  }

  // normal screenshot
  {
    const { p, ctx } = await open(browser);
    await p.screenshot({ path: path.join(SHOTS, "S0_overview_1400.png") });
    await ctx.close();
  }
  await browser.close();

  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = {
    kind: "K07 round-6 acceptance of prototypes/city-evidence (adapter of the r5 test, see header)", label: OPT.label, sha: OPT.sha,
    target: OPT.appRoot ? { app_root: path.basename(path.resolve(OPT.appRoot)) } : { url: OPT.url }, default_target_sha: TARGET_SHA,
    total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"),
    note: "No baseline XFAIL list is applied. TEST_INCOMPATIBLE = the test could not exercise the invariant; it is not a PASS.",
    checks,
  };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} [${c.scenario}] ${c.expect}${c.ok ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 220)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
})().catch((e) => { console.error(e); process.exit(2); });
