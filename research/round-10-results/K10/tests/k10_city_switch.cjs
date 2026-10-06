// K10 round 10: city switch on the REAL main site (root app.py / web/ on 8501): Shymkent -> Astana -> Shymkent.
// Usage: node k10_city_switch.cjs [--url http://127.0.0.1:8501/] [--label …] [--sha …] [--out DIR] [--mutate nocityreset|noexplreset]
// --mutate breaks the page on purpose (test of the test): the checks must then FAIL.
// Start the site from a clean copy of the pinned commit first (python -B app.py --port 8501; no API keys needed).
// Checks that a switch replaces city, sources, record IDs and names, coordinates/bbox, the plan problem digest and
// labels, and leaves no plan/resilience result, explanation or selection of the previous city; the training model
// score (52,56 in the original mode) is not touched. Map layers are checked only when the MapLibre map is ready
// (the basemap host may be blocked in the test environment: then those checks are NOT_RUN, not PASS).
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const a = process.argv.slice(2), OPT = { url: "http://127.0.0.1:8501/", label: "site", sha: null, out: null, mutate: null };
for (let i = 0; i < a.length; i += 2) { const k = a[i].replace(/^--/, ""); if (!(k in OPT)) { console.error("unknown argument " + a[i]); process.exit(2); } OPT[k] = a[i + 1]; }
const OUT = path.resolve(OPT.out || path.join(__dirname, "..", "results", "city_switch_" + OPT.label)), SHOTS = path.join(OUT, "screenshots");
const checks = [];
const check = (id, expect, ok, observed, verdict) => checks.push({ id, expect, verdict: verdict || (ok ? "PASS" : "FAIL"), observed: observed === undefined ? null : observed });
const tick = (p, ms = 150) => p.waitForTimeout(ms);

// everything the page shows or holds for the planner, as plain data
const snap = (p) => p.evaluate(() => {
  const PS = CITY_PLAN_UI.state, OS = CITY_PLAN_UI.opt, RS = CITY_RESILIENCE_UI.state, D = CITY_APP.ui.D, city = CITY_APP.state.city;
  let digest = null, raw = null;
  try { raw = CITY_PLAN_UI.rawScenario(); digest = window.CITY_PLAN.problemDigest(window.CITY_PLAN.validatePlanScenario(raw, CITY_PLAN_UI.ctxOf(city), { requirePoints: false }), CITY_APP.ui.F); } catch (e) { digest = "error: " + (e.detail || e.message); }
  const panel = document.getElementById("gov-panel");
  return { city, title: document.title, h1: document.getElementById("gov-city-title").textContent, brandSub: document.querySelector(".brand-sub").textContent,
    pressed: [...document.querySelectorAll("#gov-panel [data-city]")].filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.city),
    points: PS.points.length, cands: PS.cands.length, selected: PS.selected.slice(), expl: !!PS.expl, optStatus: OS.status, optResult: !!OS.result,
    rsCases: RS.cases.length, rsStatus: RS.status, rsResult: !!RS.result, rsExpl: !!RS.expl,
    selection: document.getElementById("gov-selection").textContent.trim(), dataText: document.getElementById("gov-data-body").textContent,
    rawCity: raw && raw.city_id, rawSnapshot: raw && raw.source_snapshot, digest, bbox: D.cities[city].bbox,
    panelText: panel.innerText, panelHtml: panel.innerHTML, score: document.getElementById("city-score").textContent,
    active: GOVTECH.active, mapReady: typeof mapReady !== "undefined" && mapReady,
    mapRecords: (typeof map !== "undefined" && map && map.getSource && map.getSource("gov-records")) ? map.getSource("gov-records")._data.features.map((f) => f.properties.id) : null };
});
const cityRecords = (p, city) => p.evaluate((c) => CITY_APP.ui.D.cities[c].places.map((x) => ({ id: x.id, name: x.name, lon: x.lon, lat: x.lat })), city);
function leaks(s, recs, other) {
  const names = new Set(other.map((r) => r.name)), ids = recs.filter((r) => !other.some((o) => o.id === r.id));
  const leakedIds = ids.filter((r) => s.panelHtml.includes(r.id) || s.panelText.includes(r.id)).map((r) => r.id);
  const leakedNames = recs.filter((r) => r.name && r.name.length > 4 && !names.has(r.name) && s.panelText.includes(r.name)).map((r) => r.name);
  const coords = recs.filter((r) => s.panelText.includes(String(r.lon)) && s.panelText.includes(String(r.lat))).map((r) => r.id);
  return { leakedIds: leakedIds.slice(0, 5), leakedNames: leakedNames.slice(0, 5), coords: coords.slice(0, 5) };
}

async function work(p) {  // produce every kind of per-city state: plan result, apply, explanation, resilience result, selection
  await p.click("#plDemo"); await tick(p);
  await p.click("#plRun"); await p.waitForFunction(() => CITY_PLAN_UI.opt.status !== "running", null, { timeout: 30000 }); await tick(p);
  const ap = p.locator('[id^="plApply_"]').first(); if (await ap.count()) { await ap.click(); await tick(p); }
  await p.click("#plExplain").catch(() => {}); await tick(p);
  await p.evaluate(() => GOVTECH.setPage("resilience")).catch(() => {}); await tick(p);
  await p.click("#rsAdd"); await tick(p);
  const rec = p.locator('input[data-rs-rec]').first(); if (await rec.count()) { await rec.check(); await tick(p); }
  await p.click("#rsRun"); await p.waitForFunction(() => CITY_RESILIENCE_UI.state.status !== "running", null, { timeout: 30000 }); await tick(p);
  await p.click("#rsExplain").catch(() => {}); await tick(p);
  await p.evaluate(() => GOVTECH.setPage("data")).catch(() => {}); await tick(p);
  const first = p.locator("#gov-data-body .gov-sources button").first(); if (await first.count()) { await first.click(); await tick(p); }
}

async function run(browser, vp, tag) {
  const ctx = await browser.newContext({ viewport: vp }), p = await ctx.newPage(), errors = [], net = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  p.on("console", (m) => { if (m.type() === "error") (/Failed to load resource|ERR_TUNNEL|ERR_PROXY/.test(m.text()) ? net : errors).push(m.text().slice(0, 200)); });
  await p.goto(OPT.url); await p.waitForFunction(() => window.GOVTECH && window.CITY_PLAN_UI && window.CITY_RESILIENCE_UI, null, { timeout: 20000 }); await tick(p, 1500);
  if (OPT.mutate === "nocityreset") await p.evaluate(() => { CITY_APP.ui.EXT.onCity.length = 0; });
  if (OPT.mutate === "noexplreset") await p.evaluate(() => { const h = CITY_APP.ui.EXT.onCity; const keep = CITY_PLAN_UI.state; h.push(() => { const e = keep.expl; setTimeout(() => { keep.expl = e; }, 0); }); });
  const score0 = await p.evaluate(() => document.getElementById("city-score").textContent);
  await p.click("#govtech-toggle"); await tick(p, 600);
  const shy = await cityRecords(p, "shymkent"), ast = await cityRecords(p, "astana");
  let s0 = await snap(p);
  check(`${tag}-CS1`, "planning mode opens on Shymkent; the training score stays as before", s0.active && s0.city === "shymkent" && s0.h1 === "Шымкент" && s0.score === score0, { city: s0.city, score0, score: s0.score });
  await work(p);
  const s1 = await snap(p);
  check(`${tag}-CS2`, "Shymkent state was really produced (plan result, explanation, resilience result, selection) — precondition of the switch test",
    s1.optResult && s1.selected.length > 0 && s1.rsResult && !!s1.selection, { optStatus: s1.optStatus, selected: s1.selected.length, rsStatus: s1.rsStatus, expl: s1.expl, rsExpl: s1.rsExpl, selection: s1.selection.slice(0, 60) });
  if (tag === "1440") await p.screenshot({ path: path.join(SHOTS, `${tag}_shymkent_before_switch.png`) });
  await p.click('#gov-panel [data-city="astana"]'); await tick(p, 600);
  const s2 = await snap(p);
  check(`${tag}-CS3`, "labels follow the city: heading, page title, subtitle, pressed button", s2.city === "astana" && s2.h1 === "Астана" && /Астана/.test(s2.title) && /Астана/.test(s2.brandSub) && s2.pressed.join() === "astana",
    { h1: s2.h1, title: s2.title, sub: s2.brandSub, pressed: s2.pressed });
  check(`${tag}-CS4`, "no plan of the previous city: points, sites, selection, search result and explanation are empty", s2.points === 0 && s2.cands === 0 && s2.selected.length === 0 && !s2.optResult && !s2.expl && ["idle", "stale"].includes(s2.optStatus),
    { points: s2.points, cands: s2.cands, selected: s2.selected, optStatus: s2.optStatus, optResult: s2.optResult, expl: s2.expl });
  check(`${tag}-CS5`, "no resilience cases, result or explanation of the previous city", s2.rsCases === 0 && !s2.rsResult && !s2.rsExpl, { rsCases: s2.rsCases, rsStatus: s2.rsStatus, rsResult: s2.rsResult, rsExpl: s2.rsExpl });
  check(`${tag}-CS6`, "the selected record card of the previous city is cleared", s2.selection === "", s2.selection.slice(0, 80));
  check(`${tag}-CS7`, "sources and records switch: data panel names the Astana slice; scenario city_id/snapshot and bbox are Astana's; the problem digest differs",
    /Срез Астана: \d+ записей/.test(s2.dataText) && !/Срез Шымкент/.test(s2.dataText) && s2.rawCity === "astana" && s2.rawSnapshot !== s1.rawSnapshot && JSON.stringify(s2.bbox) !== JSON.stringify(s1.bbox) && s2.digest !== s1.digest,
    { data: s2.dataText.slice(0, 60), rawCity: s2.rawCity, snap: [s1.rawSnapshot, s2.rawSnapshot], digest: [String(s1.digest).slice(0, 12), String(s2.digest).slice(0, 12)] });
  const lk = leaks(s2, shy, ast);
  check(`${tag}-CS8`, "no Shymkent record ID, name or coordinate pair anywhere in the planning panel after the switch", !lk.leakedIds.length && !lk.leakedNames.length && !lk.coords.length, lk);
  if (s2.mapReady) check(`${tag}-CS9`, "map layer of source points holds only Astana records", s2.mapRecords && s2.mapRecords.length > 0 && s2.mapRecords.every((id) => ast.some((r) => r.id === id)), { n: s2.mapRecords && s2.mapRecords.length });
  else check(`${tag}-CS9`, "map layer of source points holds only Astana records", false, "MapLibre map not ready (basemap host blocked in this environment): map layers not inspected", "NOT_RUN");
  if (tag === "1440") await p.screenshot({ path: path.join(SHOTS, `${tag}_astana_after_switch.png`) });
  // the same work in Astana, then back to Shymkent
  await p.evaluate(() => GOVTECH.setPage("plan")).catch(() => {}); await tick(p);
  await work(p);
  const s3 = await snap(p);
  const astIds = new Set(ast.map((r) => r.id));
  const resIds = await p.evaluate(() => { const r = CITY_PLAN_UI.opt.result; return r ? JSON.stringify(r).match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g) || [] : []; });
  check(`${tag}-CS10`, "Astana results reference only Astana record IDs", s3.optResult && resIds.every((id) => astIds.has(id)), { ids: resIds.length, foreign: resIds.filter((id) => !astIds.has(id)).slice(0, 3) });
  await p.click('#gov-panel [data-city="shymkent"]'); await tick(p, 600);
  const s4 = await snap(p);
  const lk2 = leaks(s4, ast, shy);
  check(`${tag}-CS11`, "back to Shymkent: Astana plan, resilience, explanation and selection are gone and nothing of Astana is shown",
    s4.city === "shymkent" && s4.points === 0 && !s4.optResult && s4.rsCases === 0 && !s4.rsResult && !s4.expl && s4.selection === "" && !lk2.leakedIds.length && !lk2.leakedNames.length,
    { points: s4.points, opt: s4.optResult, rs: s4.rsCases, sel: s4.selection.slice(0, 40), lk2 });
  await p.click("#govtech-toggle"); await tick(p, 600);
  const s5 = await p.evaluate(() => ({ active: GOVTECH.active, score: document.getElementById("city-score").textContent, title: document.title, panelHidden: document.getElementById("gov-panel").hidden }));
  check(`${tag}-CS12`, "return to the simulator: training model score unchanged (no planning number mixed in), planning panel hidden", !s5.active && s5.score === score0 && s5.panelHidden, { score0, ...s5 });
  check(`${tag}-CS13`, "no page errors (network failures of blocked hosts are recorded separately)", errors.length === 0, { errors: errors.slice(0, 5), network_blocked: net.length });
  await ctx.close();
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  await run(browser, { width: 1440, height: 900 }, "1440");
  await run(browser, { width: 390, height: 844 }, "390");
  await browser.close();
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K10 round-10 city switch on the real main site", url: OPT.url, label: OPT.label, sha: OPT.sha, total: checks.length,
    pass: by("PASS"), fail: by("FAIL"), not_run: by("NOT_RUN"), note: "Plans are the site's SYNTHETIC demo sets on the real slices; this tests transfer between cities, not data quality.", checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 400)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · NOT_RUN ${out.not_run.length} of ${out.total}`);
  process.exitCode = out.fail.length ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
