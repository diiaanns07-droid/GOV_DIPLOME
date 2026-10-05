// K07 round 4 REVIEW: user-level checks of the fixed round-3 K07 prototype (or of a patched copy).
// Usage: node review_user_path.cjs <prototype_dir> <label>
//   <prototype_dir>  directory with index.html, app.js, data.js (see scripts/extract_snapshot.py)
//   <label>          "snapshot" | "patched" -> results/review_<label>.json, results/screenshots/<label>/*.png
// FAIL = the prototype does not behave as a user expects (a defect), not a test crash. Exit 0 always if the run completed.
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

const DIR = path.resolve(process.argv[2]);
const LABEL = process.argv[3] || "run";
const URL = "file://" + path.join(DIR, "index.html");
const K07R4 = path.resolve(__dirname, "..");
const SHOTS = path.join(K07R4, "results/screenshots", LABEL);
const checks = [];
const check = (id, area, expect, ok, observed) => checks.push({ id, area, expect, ok: !!ok, observed: observed === undefined ? null : observed });

async function state(p) {
  return p.evaluate(() => {
    const S = window.K07_APP.state, c = window.K07_DATA.cities[S.city];
    const ids = new Set(c.places.map((x) => x.id));
    const rendered = [...document.querySelectorAll("#map g[data-id]")].map((g) => g.dataset.id);
    return {
      city: S.city, point: S.point, selected: S.selected,
      selEmptyVisible: !document.getElementById("selEmpty").hidden, selBody: document.getElementById("selBody").textContent,
      markers: rendered.length, foreignMarkers: rendered.filter((id) => !ids.has(id)).length,
      expectedMarkers: c.places.filter((x) => S.groups.has(x.group)).length,
      tblCount: document.getElementById("tblCount").textContent, tblSelRows: document.querySelectorAll("#tbl tr.sel").length,
      selRing: document.querySelectorAll("#map g[data-id] circle[r='10']").length,
      crosshairOrRadius: [...document.querySelectorAll("#map path, #map circle")].filter((e) => (e.getAttribute("d") || "").includes("H") || (e.getAttribute("stroke-dasharray") === "5 4")).length,
      tLabel: [...document.querySelectorAll("#map text")].some((t) => t.textContent.startsWith("T = ")),
      tipVisible: getComputedStyle(document.getElementById("tip")).display !== "none", tipText: document.getElementById("tip").textContent,
      prov: document.getElementById("provBody").textContent, graph: document.getElementById("graphBody").textContent,
      cityLabel: c.label, iso: c.iso, segs: c.graph.segments, nPlaces: c.places.length,
      clipW: String(c.k10_request_clip.export[0]),
      otherNames: Object.values(window.K07_DATA.cities).filter((x) => x.key !== S.city).flatMap((x) => x.places.map((q) => q.name)),
    };
  });
}

async function pointAt(p, dx, dy) {
  return p.evaluate(([dx, dy]) => {
    const S = window.K07_APP.state, c = window.K07_DATA.cities[S.city].k10_request_clip.centre;
    const [x, y] = window.K07_APP.toScreen(c[0], c[1]); const r = document.getElementById("map").getBoundingClientRect();
    return { x: r.left + x + dx, y: r.top + y + dy };
  }, [dx, dy]);
}

async function citySwitchSuite(p, from, to) {
  const tag = `${from}->${to}`;
  await p.click(`#citySeg button[data-city="${from}"]`);
  // (a) selected object
  await p.locator("#tbl tr").nth(2).click();
  let s = await state(p);
  const selName = s.selBody.slice(0, 30);
  // hover a marker whose centre is really on top, so a tooltip is visible; then switch by KEYBOARD (pointer stays)
  await p.evaluate(() => document.querySelector(".mapwrap").scrollIntoView({ block: "start" }));
  const hp = await p.evaluate(() => {
    for (const g of [...document.querySelectorAll("#map g[data-id]")].reverse()) {
      const r = g.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
      if (g.contains(document.elementFromPoint(x, y))) return { x, y };
    }
    return null;
  });
  await p.mouse.move(hp.x - 30, hp.y - 30); await p.mouse.move(hp.x, hp.y, { steps: 6 });
  const tipBefore = (await state(p)).tipText;
  await p.focus(`#citySeg button[data-city="${to}"]`); await p.keyboard.press("Enter");
  s = await state(p);
  check(`CS1 ${tag}`, "city switch", "selected object card of the old city is cleared", s.selected === null && s.selEmptyVisible && s.selBody === "" && s.selRing === 0 && s.tblSelRows === 0,
    { selected: s.selected, selBodyStart: s.selBody.slice(0, 40), was: selName });
  check(`CS2 ${tag}`, "city switch", "tooltip of an old-city object does not stay on the new city's map (precondition: tooltip was visible)",
    tipBefore !== "" && (!s.tipVisible || !s.otherNames.some((n) => n && s.tipText.includes(n))), { tipBefore, tipVisible: s.tipVisible, tipText: s.tipText });
  check(`CS3 ${tag}`, "city switch", "markers and table count belong to the new city only",
    s.foreignMarkers === 0 && s.markers === s.expectedMarkers && s.tblCount.includes(`из ${s.nPlaces}`), { markers: s.markers, foreign: s.foreignMarkers, tbl: s.tblCount });
  check(`CS4 ${tag}`, "city switch", "provenance and graph cards show the new city",
    s.prov.includes(s.cityLabel) && s.prov.includes(s.iso) && s.graph.includes(`${s.segs} сегментов`) && s.graph.includes(s.clipW), { city: s.cityLabel });
  await p.mouse.move(5, 5);
  // (b) selected point
  await p.click(`#citySeg button[data-city="${from}"]`);
  if ((await p.getAttribute("#pointBtn", "aria-pressed")) !== "true") await p.click("#pointBtn");
  const pt = await pointAt(p, 40, 40); await p.mouse.click(pt.x, pt.y);
  const hadPoint = (await state(p)).point !== null;
  await p.click(`#citySeg button[data-city="${to}"]`);
  s = await state(p);
  check(`CS5 ${tag}`, "city switch", "point, radius, crosshair and T label of the old city are cleared",
    hadPoint && s.point === null && s.crosshairOrRadius === 0 && !s.tLabel && s.selEmptyVisible, { hadPoint, point: s.point, drawn: s.crosshairOrRadius, tLabel: s.tLabel });
  // (c) switching back does not restore old state as data
  await p.click(`#citySeg button[data-city="${from}"]`);
  s = await state(p);
  check(`CS6 ${tag}`, "city switch", "switching back starts clean (no restored point/selection)", s.point === null && s.selected === null, { point: s.point, selected: s.selected });
  await p.click("#pointBtn");  // leave point mode off
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await p.goto(URL);
  await p.waitForSelector("#map g[data-id]");

  // ---- city switch (minimum required) ----
  await citySwitchSuite(p, "shymkent", "astana");
  await citySwitchSuite(p, "astana", "shymkent");

  // ---- filters ----
  await p.click('#citySeg button[data-city="astana"]');
  const nSchool = await p.evaluate(() => window.K07_DATA.cities.astana.places.filter((x) => x.group === "school").length);
  let s = await state(p);
  await p.uncheck('input[data-group="school"]');
  let s2 = await state(p);
  check("F1", "filters", "unchecking a group removes exactly its objects from map and table", s2.markers === s.markers - nSchool && s2.tblCount.includes(`${s.markers - nSchool} из`), { before: s.markers, after: s2.markers, nSchool });
  await p.check('input[data-group="school"]');
  // object selected, then its group filtered out
  await p.locator("#tbl tr").first().click();
  const g = await p.evaluate(() => window.K07_DATA.cities.astana.places.find((x) => x.id === window.K07_APP.state.selected.id).group);
  await p.uncheck(`input[data-group="${g}"]`);
  s = await state(p);
  check("F2", "filters", "a selected object hidden by a filter does not keep an orphan card", s.selected === null || s.selBody.includes("скрыт"), { group: g, selected: s.selected, card: s.selBody.slice(0, 50) });
  await p.check(`input[data-group="${g}"]`);

  // ---- object ----
  const top = p.locator("#map g[data-id]").last(); const name = (await top.getAttribute("aria-label")).split(",")[0];
  await top.click();
  s = await state(p);
  check("O1", "object", "click opens the card of that object with 'capacity unknown' and kind badges", s.selBody.includes(name) && s.selBody.includes("неизвестно") && s.selBody.includes("производное K07"), name);
  // marker under a map label must stay clickable
  await p.evaluate(() => document.querySelector(".mapwrap").scrollIntoView({ block: "start" }));
  const hit = await p.evaluate(() => {
    const out = []; let tested = 0;
    for (const g of document.querySelectorAll("#map g[data-id]")) {
      const r = g.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
      if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
      tested++;
      const e = document.elementFromPoint(x, y);
      if (e && e.tagName === "text") out.push({ id: g.dataset.id, label: e.textContent.slice(0, 40) });
    }
    return { tested, covered: out };
  });
  check("O2", "object", "no marker centre is covered by a label that swallows the click", hit.tested > 0 && hit.covered.length === 0, hit);

  // ---- clearing the point ----
  await p.click("#pointBtn");
  let pt = await pointAt(p, 40, 40); await p.mouse.click(pt.x, pt.y);
  const clearBtn = p.locator("button", { hasText: /Сбросить|Очистить/ });
  const hasClear = (await clearBtn.count()) > 0;
  if (hasClear) await clearBtn.first().click(); else await p.keyboard.press("Escape");
  s = await state(p);
  check("P1", "point", "the user can clear the selected point (button or Escape)", s.point === null && s.crosshairOrRadius === 0 && !s.tLabel, { hasClearButton: hasClear, point: s.point });
  await p.mouse.click(pt.x, pt.y);
  await p.click("#pointBtn");
  s = await state(p);
  check("P2", "point", "after turning point mode off the point is either cleared or still clearable", s.point === null || hasClear, { point: s.point, hasClear });
  if (hasClear) await clearBtn.first().click();

  // ---- empty selection ----
  for (const cb of await p.locator("input[data-group]").all()) await cb.uncheck();
  s = await state(p);
  check("E1", "empty", "no groups -> clear empty messages on map and in table, no markers", s.markers === 0 && (await p.isVisible("#mapMsg")) && (await p.textContent("#tbl")).includes("Не выбрана"), null);
  await p.click('#citySeg button[data-city="shymkent"]');
  s = await state(p);
  check("E2", "empty", "empty state survives a city switch without stale numbers", s.markers === 0 && s.tblCount.includes(`(0 из ${s.nPlaces}`), s.tblCount);
  for (const cb of await p.locator("input[data-group]").all()) await cb.check();

  // ---- keyboard ----
  await p.goto(URL); await p.waitForSelector("#map g[data-id]");
  await p.focus('#citySeg button[data-city="astana"]'); await p.keyboard.press("Space");
  s = await state(p);
  check("K1", "keyboard", "city buttons work with the keyboard", s.city === "astana", s.city);
  await p.focus('input[data-group="pharmacy"]'); await p.keyboard.press("Space");
  s2 = await state(p);
  check("K2", "keyboard", "group checkboxes work with the keyboard", s2.markers < s.markers, { before: s.markers, after: s2.markers });
  await p.keyboard.press("Space");
  await p.locator("#map g[data-id]").first().focus(); await p.keyboard.press("Enter");
  s = await state(p);
  check("K3", "keyboard", "a focused marker opens its card with Enter", s.selected && s.selected.type === "place", s.selected);
  const tabs = await p.evaluate(() => {
    const all = [...document.querySelectorAll('a[href], button, input, summary, [tabindex]')].filter((e) => e.tabIndex >= 0 && !e.disabled && e.offsetParent !== null || e.closest("svg"));
    return { toZoom: all.findIndex((e) => e.id === "zIn"), toTable: all.findIndex((e) => e.closest && e.closest("#tbl")),
             skipLink: !!document.querySelector('a[href="#tblSection"], a[href="#tbl"]') };
  });
  check("K4", "keyboard", "table and zoom are reachable without tabbing through every map feature (skip link or < 40 stops)", tabs.skipLink || tabs.toTable < 40, tabs);
  await p.click("#pointBtn");
  await p.focus("#map").catch(() => {});
  const mapFocusable = await p.evaluate(() => document.activeElement && document.activeElement.id === "map");
  if (mapFocusable) await p.keyboard.press("Enter");
  s = await state(p);
  check("K5", "keyboard", "a point can be set without a mouse (focusable map + Enter)", mapFocusable && s.point !== null, { mapFocusable, point: s.point });

  // ---- 390 px ----
  const narrow = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const n = await narrow.newPage();
  await n.goto(URL); await n.waitForSelector("#map g[data-id]");
  const w = await n.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth, mapH: document.getElementById("map").clientHeight,
    btn: document.getElementById("pointBtn").getBoundingClientRect().right }));
  check("W1", "390px", "no horizontal page scroll; controls inside the viewport; map at least 300 px high", w.sw <= w.iw && w.btn <= w.iw && w.mapH >= 300, w);
  await n.screenshot({ path: path.join(SHOTS, "390_top.png") });
  await n.click('#citySeg button[data-city="astana"]');
  await n.click("#pointBtn");
  // an empty spot of the city polygon (topmost element is the city fill path), near the K10 clip centre
  const np = await n.evaluate(() => {
    const c = window.K07_DATA.cities.astana.k10_request_clip.centre, [x0, y0] = window.K07_APP.toScreen(c[0], c[1]);
    const r = document.getElementById("map").getBoundingClientRect();
    for (let d = 20; d < 200; d += 6) for (const [dx, dy] of [[d, d], [-d, d], [d, -d], [-d, -d]]) {
      const x = r.left + x0 + dx, y = r.top + y0 + dy, e = document.elementFromPoint(x, y);
      if (e && e.tagName === "path" && e.getAttribute("fill") === "var(--surface-2)") return { x, y };
    }
    return null;
  });
  if (np) await n.mouse.click(np.x, np.y);
  const ns = await n.evaluate(() => {
    const sel = document.getElementById("selCard").getBoundingClientRect(), map = document.querySelector(".mapwrap").getBoundingClientRect();
    const hint = [...document.querySelectorAll(".mapwrap *")].some((e) => e.offsetParent !== null && /Точка|точк/.test(e.textContent) && e.id !== "map" && !e.closest("svg"));
    return { point: window.K07_APP.state.point, cardTopVisible: sel.top < innerHeight && sel.bottom > 0, hintInMapArea: hint };
  });
  check("W2", "390px", "a point can be set on a 390 px screen and its result is visible or announced next to the map",
    np && ns.point !== null && (ns.cardTopVisible || ns.hintInMapArea), { foundEmptySpot: !!np, ...ns });
  const clipped = await n.evaluate(() => [...document.querySelectorAll(".card, .tablewrap")].filter((c) => c.scrollWidth > c.clientWidth + 1)
    .map((c) => ({ box: c.className, card: (c.closest(".card").querySelector("h2") || {}).textContent, scrollWidth: c.scrollWidth, clientWidth: c.clientWidth })));
  check("W3", "390px", "side cards and tables fit 390 px without hidden columns (no inner horizontal scroll)", clipped.length === 0, clipped);
  await n.screenshot({ path: path.join(SHOTS, "390_point_full.png"), fullPage: true });

  check("X1", "general", "no console or page errors during the run", errors.length === 0, errors);
  await p.screenshot({ path: path.join(SHOTS, "1400_end.png") });
  await browser.close();

  const out = { kind: "REVIEW user-level checks of the K07 round-3 prototype", label: LABEL, prototype_dir_name: path.basename(DIR),
    total: checks.length, passed: checks.filter((c) => c.ok).length, failed: checks.filter((c) => !c.ok).map((c) => c.id), checks };
  fs.writeFileSync(path.join(K07R4, `results/review_${LABEL}.json`), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.ok ? "PASS" : "FAIL"} ${c.id} [${c.area}] ${c.expect}${c.ok ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 220)}`);
  console.log(`${out.passed}/${out.total} passed`);
})().catch((e) => { console.error(e); process.exit(2); });
