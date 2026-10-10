// R01 round 13: junctions between the shell and the real R02/R03/R04 modules of the integration candidate.
//   1. a cabinet opened before the map loads can still draw (R04 map getter / setMap);
//   2. openEditor(objectId) on a fresh cabinet waits for R04's /session check (no login form);
//   3. archive through the cabinet never leaves the record selected as public;
//   4. CivicApiError keeps current_revision (409) and retry_after (429) as safe structured fields;
//   5. while R04's drawing tool or the scenario drawer is active, a map click does not open R03 cards;
//      without a tool it does (control).
// Usage: node tests/civic/R01/browser/r13_junctions.cjs <out_dir>
// Starts `python3 -B app.py` on a free port with a temporary SQLite file (R02 init + R05 synthetic demo
// slice + an editor created through R02's CLI with the password on stdin). Nothing is written to the repo.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os"), crypto = require("crypto");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r13-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff/i;
const PASSWORD = "r13-Esil-" + crypto.randomBytes(9).toString("base64url");
const USER = "r13_editor";
const fk = (k) => `#civic-editor [data-fk="${k}"]`;
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const notRun = (name, reason) => { checks.push({ name, status: "NOT_RUN", detail: reason }); console.log("NOT_RUN " + name + " — " + reason); };
// R03's intermittent "Image civic-r03-demo-ring could not be loaded" (race after the offline style
// swap; R03-owned, fix proposed in research/round-13-results/R01/proposed/r03_r01_proposal.patch) is
// reported as its own FAIL so it neither hides other page errors nor masquerades as an R01 error.
const R03_RING = /Image "civic-r03-demo-ring" could not be loaded/;
function checkPageErrors(name, errs) {
  const ring = errs.filter((e) => R03_RING.test(e)), other = errs.filter((e) => !R03_RING.test(e));
  check(name, other.length === 0, other);
  if (ring.length) check(name + " — R03 demo-ring image race (R03-owned)", false, ring.length + " warning(s)");
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1" };
  const cli = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: [input ? "pipe" : "ignore", "ignore", "inherit"] });
  cli("init");
  cli("seed-demo --package data/civic/astana/demo_synthetic.json");
  cli(`create-editor ${USER} --password-stdin --display-name "Редактор R13"`, PASSWORD + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady, null, { timeout: 40000 });
async function loginInCabinet(page) {
  await page.waitForSelector(fk("login-user"), { timeout: 15000 });
  await page.fill(fk("login-user"), USER);
  await page.fill(fk("login-pass"), PASSWORD);
  await page.click(fk("login-submit"));
  await page.waitForSelector(fk("new"), { timeout: 15000 });
}
// Screen point of a published point object inside the free map area (not under panel/drawer/tools/box).
// Test setup: if none is free, the camera is centred on a point object first (instant jump).
const freePointOfObject = async (page) => {
  const found = await findFreePoint(page);
  if (found) return found;
  await page.evaluate(() => {
    const f = map.querySourceFeatures("civic-r03-objects").find((x) => x.geometry.type === "Point" || x.geometry.type === "LineString");
    if (f) map.jumpTo({ center: f.geometry.type === "Point" ? f.geometry.coordinates : f.geometry.coordinates[Math.floor(f.geometry.coordinates.length / 2)], zoom: Math.max(map.getZoom(), 14) });
  });
  await page.waitForTimeout(700);
  return findFreePoint(page);
};
const findFreePoint = (page) => page.evaluate(() => {
  // A clickable spot on each published geometry: the point, a line's middle vertex, a polygon's centroid.
  const spot = (g) => g.type === "Point" ? g.coordinates : g.type === "LineString" ? g.coordinates[Math.floor(g.coordinates.length / 2)]
    : g.type === "Polygon" ? (() => { const r = g.coordinates[0].slice(0, -1); return [r.reduce((a, q) => a + q[0], 0) / r.length, r.reduce((a, q) => a + q[1], 0) / r.length]; })() : null;
  const feats = map.querySourceFeatures("civic-r03-objects").map((f) => ({ ...f, at: spot(f.geometry) })).filter((f) => f.at);
  const c = map.getContainer().getBoundingClientRect();
  const blockers = ["#civic-panel", ".civic-explore", ".map-tools", ".topbar", "#civic-editor", "#civic-scenarios"]
    .map((s) => document.querySelector(s)).filter((e) => e && e.getClientRects().length && getComputedStyle(e).visibility !== "hidden" && !e.hidden)
    .map((e) => e.getBoundingClientRect());
  for (const f of feats) {
    const p = map.project(f.at);
    const x = c.left + p.x, y = c.top + p.y;
    if (x < 20 || y < 20 || x > innerWidth - 20 || y > innerHeight - 20) continue;
    if (blockers.some((b) => x >= b.left - 8 && x <= b.right + 8 && y >= b.top - 8 && y <= b.bottom + 8)) continue;
    return { id: f.properties.cid, x, y };
  }
  window.__r13diag = { features: feats.length, types: map.querySourceFeatures("civic-r03-objects").map((f) => f.geometry.type),
    pts: feats.slice(0, 3).map((f) => { const p = map.project(f.at); return [Math.round(c.left + p.x), Math.round(c.top + p.y)]; }),
    blockers: blockers.map((b) => [b.left, b.top, b.right, b.bottom].map(Math.round)) };
  return null;
});

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "civic-r13-"));
  const port = await freePort(), base = `http://127.0.0.1:${port}/`;
  const srv = await startServer(port, path.join(dbDir, "civic.sqlite3"));
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const result = { base, started_at: new Date().toISOString(), checks };
  try {
    const published = (await (await fetch(base + "api/civic/v1/objects")).json()).data.items;
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    const errs = [];
    page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
    page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) errs.push(m.type() + ": " + m.text()); });

    // ---- 1. cabinet opened before the map is ready
    await page.goto(base + "?tools=all", { waitUntil: "domcontentloaded" });  // round-13 tools hidden from Birge by default
    await page.waitForFunction(() => typeof window.CivicShell?.openEditor === "function", null, { timeout: 15000 });
    const mapReadyAtOpen = await page.evaluate(() => { const r = typeof mapReady !== "undefined" && !!mapReady; window.CivicShell.openEditor(); return r; });
    await loginInCabinet(page);
    await ready(page);
    await page.click(fk("new"));
    await page.check(fk("place-approximate"));
    const toolEnabled = await page.waitForFunction((sel) => { const b = document.querySelector(sel); return b && !b.disabled; }, fk("tool-point"), { timeout: 10000 }).then(() => true).catch(() => false);
    if (mapReadyAtOpen) notRun("cabinet opened before the map loads can draw once the map is ready", "map was already ready when the cabinet opened (could not reproduce the early open)");
    else check("cabinet opened before the map loads can draw once the map is ready (map getter / setMap)", toolEnabled, { mapReadyAtOpen, toolEnabled });

    // ---- 5a. editor tool active: a map click on a public object does not open its card
    await page.click(fk("tool-point"));
    await page.waitForTimeout(300);
    const toolPoint = await freePointOfObject(page);
    if (!toolPoint) notRun("editor tool: map click on a public object does not open its card", "no published point object in the free map area at 1440x900");
    else {
      await page.mouse.click(toolPoint.x, toolPoint.y);
      await page.waitForTimeout(900);
      const st = await page.evaluate(() => ({ selected: window.CivicShell.selected, view: window.CivicShell.mapView,
        placed: !!document.querySelector('#civic-editor [data-fk="geometry_confirmed"]') }));
      check("editor tool: map click places R04's point but does not open an R03 card", !st.selected && st.view !== "card" && st.placed, { ...st, clicked: toolPoint.id });
    }
    await page.screenshot({ path: path.join(OUT, "01_editor_tool_click_1440.png") });
    await page.click("#civic-editor [data-close=editor]");
    await page.waitForTimeout(500);
    const afterTool = await page.evaluate(() => ({ selected: window.CivicShell.selected, view: window.CivicShell.mapView }));
    check("after the editor closes no card or object chooser is left from tool clicks", !afterTool.selected && afterTool.view === "list", afterTool);

    // ---- 2. openEditor(objectId) on a fresh cabinet with a live session opens the object, not the login form
    // Archive a non-point record: the point records are needed for the map-click checks below.
    const target = published.find((i) => i.geometry && i.geometry.type !== "Point") || published[0];
    await page.evaluate((id) => window.CivicShell.openEditor(id), target.id);
    const opened = await page.waitForFunction((title) => { const t = document.querySelector('#civic-editor [data-fk="title"]'); return t && t.value === title; }, target.title, { timeout: 15000 }).then(() => true).catch(() => false);
    const loginShown = await page.isVisible(fk("login-user")).catch(() => false);
    check("openEditor(objectId) on a fresh cabinet waits for /session and opens the record", opened && !loginShown, { opened, loginShown, id: target.id });

    // ---- 3. archive: the record must not stay selected as public
    await page.evaluate((id) => window.CivicShell.selectObject(id), target.id);
    await page.waitForTimeout(800);
    await page.click(fk("archive"));
    await page.click(`${fk("chip-0")}`).catch(() => null);
    if (await page.locator(fk("reason")).count()) { const v = await page.inputValue(fk("reason")); if (!v) await page.fill(fk("reason"), "Проверка архива (R13 смоук)"); }
    await page.click(fk("confirm"));
    await page.waitForFunction(() => /архив/i.test(document.querySelector("#civic-editor").textContent), null, { timeout: 15000 }).catch(() => null);
    await page.waitForTimeout(1500);
    const afterArchive = await page.evaluate(async (id) => ({ selected: window.CivicShell.selected, hash: location.hash,
      publicStatus: (await fetch("/api/civic/v1/objects/" + encodeURIComponent(id))).status,
      cardOpenForIt: !!document.querySelector("#civic-map-root .civic-r03-card:not([hidden])") && window.CivicShell.selected === id }), target.id);
    check("archive through the cabinet: record gone publicly and not selected as public", afterArchive.publicStatus === 404 && afterArchive.selected !== target.id && !afterArchive.hash.includes(target.id), afterArchive);
    await page.screenshot({ path: path.join(OUT, "02_after_archive_1440.png") });
    await page.click("#civic-editor [data-close=editor]");

    // ---- 4. structured error details
    const errInfo = await page.evaluate(async () => {
      const api = window.CivicShell.api;
      const list = await api.request("GET", "/staff/objects");
      const it = list.items.find((x) => x.publication !== "archived");
      const fresh = await api.request("GET", "/staff/objects/" + encodeURIComponent(it.id));
      const rev = fresh.item.revision;
      let conflict = null;
      try { await api.request("POST", "/staff/objects/" + encodeURIComponent(it.id) + "/update", { expected_revision: rev - 1 >= 1 ? rev - 1 : rev + 5, changes: { title: fresh.item.title }, reason: "проверка конфликта" }); }
      catch (e) { conflict = { status: e.status, code: e.code, current: e.current_revision, inner: e.error?.current_revision, rev, stack: "stack" in (e.error || {}) }; }
      let rate = null;
      for (let i = 0; i < 8 && !rate; i++) {
        try { await api.request("POST", "/session/login", { username: "r13-nobody", password: "wrong-" + i }); }
        catch (e) { if (e.status === 429) rate = { status: e.status, code: e.code, retry: e.retry_after, inner: e.error?.retry_after }; }
      }
      return { conflict, rate };
    });
    const c = errInfo.conflict, r = errInfo.rate;
    check("409 keeps current_revision as a structured field (err.current_revision and err.error.current_revision)",
      !!c && c.status === 409 && Number.isInteger(c.current) && c.current === c.inner && c.current === c.rev && !c.stack, c);
    check("429 keeps retry_after (body or Retry-After header) as a structured field", !!r && Number.isInteger(r.retry) && r.retry > 0 && r.retry === r.inner, r);

    // ---- 5b. scenario drawer open: a map click does not open cards; 5c. control: without a tool it does
    await page.evaluate(() => window.CivicShell.selectObject(null));
    await page.waitForTimeout(400);
    await page.click("#civic-scenarios-button");
    await page.waitForTimeout(1200);
    const scenPoint = await freePointOfObject(page);
    if (!scenPoint) notRun("scenario drawer: map click does not open cards", "no published point object in the free map area with the drawer open " + JSON.stringify(await page.evaluate(() => window.__r13diag)));
    else {
      await page.mouse.click(scenPoint.x, scenPoint.y);
      await page.waitForTimeout(900);
      const sel = await page.evaluate(() => ({ selected: window.CivicShell.selected, view: window.CivicShell.mapView }));
      check("scenario drawer open: a map click on a public object does not open its card", !sel.selected && sel.view !== "card", { ...sel, clicked: scenPoint.id });
    }
    await page.click("#civic-scenarios [data-close=scenarios]");
    await page.waitForTimeout(600);
    const afterScen = await page.evaluate(() => window.CivicShell.mapView);
    check("after the scenario drawer closes no object chooser is left", afterScen === "list", afterScen);
    const ctrlPoint = await freePointOfObject(page);
    if (!ctrlPoint) notRun("control: without a tool a map click opens the card", "no published point object in the free map area");
    else {
      await page.mouse.click(ctrlPoint.x, ctrlPoint.y);
      await page.waitForTimeout(1200);
      const sel = await page.evaluate(() => ({ selected: window.CivicShell.selected, view: window.CivicShell.mapView }));
      // Overlapping demo records open R03's chooser instead of a card; either means R03 reacted.
      check("control: without a tool a map click reaches R03 (card or chooser) — suppression is conditional", !!sel.selected || sel.view === "pick", { ...sel, clicked: ctrlPoint.id });
    }
    // ---- 6. A/B -> explanation of the server's own result -> inputs change -> withdrawn -> new result
    const assistantBodies = [];
    page.on("request", (r) => { if (r.method() === "POST" && /\/api\/civic\/v1\/assistant$/.test(r.url())) assistantBodies.push(r.postDataJSON()); });
    await page.click("#civic-scenarios-button");
    await page.waitForFunction(() => document.querySelectorAll("#civic-scenarios-root select")[1]?.options.length > 1, null, { timeout: 15000 });
    const k03 = await page.evaluate(() => [...document.querySelectorAll("#civic-scenarios-root select")[1].options].find((o) => /k03/i.test(o.value))?.value
      || [...document.querySelectorAll("#civic-scenarios-root select")[1].options].find((o) => o.value)?.value);
    await page.selectOption("#civic-scenarios-root select >> nth=1", k03);
    await page.waitForTimeout(800);
    const explainHiddenBefore = await page.evaluate(() => document.getElementById("civic-scenario-explain").hidden);
    await page.click("#civic-scenarios-root button:has-text('Сравнить')");
    const shown = await page.waitForSelector("#civic-scenario-explain:not([hidden]) .civic-r09-chip", { timeout: 30000 }).then(() => true).catch(() => false);
    check("A/B: no explanation before a computation; after a successful compare the assistant offers to explain it", explainHiddenBefore && shown, { explainHiddenBefore, shown });
    if (shown) {
      await page.click("#civic-scenario-explain .civic-r09-chip >> nth=0");
      const answered = await page.waitForFunction(() => /План A|план A|гипотез/.test(document.querySelector("#civic-scenario-explain .civic-r09-answer")?.textContent || ""), null, { timeout: 20000 })
        .then(() => true).catch(() => false);
      const body = assistantBodies[assistantBodies.length - 1] || {};
      const keys = Object.keys(body).sort().join(",");
      check("A/B explanation comes from the server's result: request carries only question/object_id/scenario_id", answered && keys === "object_id,question,scenario_id"
        && /^result:[0-9a-f]{16,64}$/.test(body.scenario_id || ""), { answered, keys, scenario: body.scenario_id });
      await page.screenshot({ path: path.join(OUT, "03_ab_explanation_1440.png") });
      const firstId = body.scenario_id;
      // Change the analysis moment: R07 drops its result, the explanation must go with it.
      await page.evaluate(() => { const i = document.querySelector('#civic-scenarios-root input[aria-label="Момент анализа"]');
        const d = new Date(i.value || "2026-10-10T12:00"); d.setHours(d.getHours() + 30); i.value = d.toISOString().slice(0, 16); i.dispatchEvent(new Event("change", { bubbles: true })); });
      await page.waitForTimeout(500);
      const withdrawn = await page.evaluate(() => document.getElementById("civic-scenario-explain").hidden);
      check("A/B: changing the inputs withdraws the explanation of the previous result", withdrawn, { withdrawn });
      await page.click("#civic-scenarios-root button:has-text('Сравнить')");
      await page.waitForSelector("#civic-scenario-explain:not([hidden]) .civic-r09-chip", { timeout: 30000 }).catch(() => null);
      await page.click("#civic-scenario-explain .civic-r09-chip >> nth=0").catch(() => null);
      await page.waitForTimeout(2500);
      const second = (assistantBodies[assistantBodies.length - 1] || {}).scenario_id;
      check("A/B: a new computation is explained under its own result digest", !!second && second !== firstId, { firstId, second });
    }
    await page.click("#civic-scenarios [data-close=scenarios]");
    checkPageErrors("no page errors", errs);
    await ctx.close();
  } catch (error) {
    check("flow completed without exception", false, String(error && error.stack || error).slice(0, 1500));
  } finally {
    await browser.close();
    srv.kill("SIGTERM");
    fs.rmSync(dbDir, { recursive: true, force: true });
    result.finished_at = new Date().toISOString();
    result.summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length,
      not_run: checks.filter((c) => c.status === "NOT_RUN").length };
    fs.writeFileSync(path.join(OUT, "r13_junctions.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result.summary));
    process.exit(result.summary.fail ? 1 : 0);
  }
})();
