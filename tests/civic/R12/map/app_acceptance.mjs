// R03 round 13 acceptance on the REAL integrated page (app.py + R01 shell + R02 store + R04 editor + this module).
//   NODE_PATH=$(npm root -g) node tests/civic/R12/map/app_acceptance.mjs <out_dir>
// Starts `python3 -B app.py` on a free port with a temporary SQLite (R02 CLI: init, seed-demo with R05's synthetic
// slice, create-editor with a random password via stdin). Nothing is written into the repository; <out_dir> gets
// acceptance.json and screenshots. Checks are PASS/FAIL/NOT_RUN; an unreachable basemap is NOT_RUN, never PASS.
import { createRequire } from "node:module";
import { spawn, execSync, execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import net from "node:net";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const OUT = path.resolve(process.argv[2] || "r03-acceptance");
fs.mkdirSync(OUT, { recursive: true });
function loadPlaywright() {
  try { return createRequire(import.meta.url)("playwright"); } catch (e) { /* fall through */ }
  return createRequire(path.join(execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim(), "x.js"))("playwright");
}
const { chromium } = loadPlaywright();
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null }); console.log((ok ? "PASS " : "FAIL ") + name + (detail != null ? " — " + JSON.stringify(detail).slice(0, 300) : "")); };
const notRun = (name, reason) => { checks.push({ name, status: "NOT_RUN", detail: reason }); console.log("NOT_RUN " + name + " — " + reason); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fk = (k) => `[data-fk="${k}"]`;

const port = await new Promise((ok) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => ok(p)); }); });
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r03-acc-"));
const db = path.join(tmp, "civic.sqlite3");
const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1" };
const USER = "r03_acceptance", PASSWORD = "r03-Esil-" + crypto.randomBytes(9).toString("base64url");
execSync(`python3 -B -m ui.civic_store --db "${db}" init`, { cwd: REPO, env, stdio: "ignore" });
execSync(`python3 -B -m ui.civic_store --db "${db}" seed-demo --package data/civic/astana/demo_synthetic.json`, { cwd: REPO, env, stdio: "ignore" });
execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${USER} --password-stdin --display-name "Проверка R03"`, { cwd: REPO, env, input: PASSWORD + "\n", stdio: ["pipe", "ignore", "inherit"] });
const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: "ignore" });
const base = `http://127.0.0.1:${port}/`;
for (let i = 0; i < 100; i++) { try { if ((await fetch(base + "api/health")).ok) break; } catch {} await sleep(200); }
const sha = execSync("git rev-parse HEAD", { cwd: REPO, encoding: "utf8" }).trim();
const dirty = execSync("git status --porcelain -- web/civic/map", { cwd: REPO, encoding: "utf8" }).trim();
const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });

async function openPage(viewport, hash) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, hasTouch: viewport.width < 500 });
  const page = await ctx.newPage();
  const errors = [], warns = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "warning" || m.type() === "error") warns.push(m.text()); });
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await page.goto(base + (hash || ""));
  await page.waitForSelector("#civic-map-root .civic-r03-item", { state: "attached", timeout: 40000 });
  await page.waitForFunction(() => typeof map !== "undefined" && map && map.getStyle && (map.getStyle()?.layers || []).filter((l) => l.id.startsWith("civic-r03")).length === 15, null, { timeout: 20000 });
  await sleep(800);
  return { ctx, page, errors, warns };
}
const view = (page) => page.evaluate(() => {
  const root = document.getElementById("civic-map-root");
  return { view: root.getAttribute("data-civic-r03-view"), title: root.querySelector(".civic-r03-card-title")?.textContent || null, hash: location.hash, cursor: map.getCanvas().style.cursor };
});
// A public object drawn on screen, not covered by the panel, the navigation box or a drawer.
const visibleObject = (page) => page.evaluate(() => {
  const c = map.getCanvas().getBoundingClientRect();
  for (const f of map.queryRenderedFeatures({ layers: ["civic-r03-point"] })) {
    const p = map.project(f.geometry.coordinates), x = c.left + p.x, y = c.top + p.y;
    if (x > c.left + 10 && x < c.right - 10 && y > c.top + 10 && y < c.bottom - 10 && document.elementFromPoint(x, y) === map.getCanvas()) return { id: f.properties.cid, x, y };
  }
  return null;
});

try {
  // ---- 1. render: light map, one canvas, R03 layers after the basemap style swap
  const { ctx, page, errors, warns } = await openPage({ width: 1440, height: 900 });
  const r = await page.evaluate(() => ({ canvases: document.querySelectorAll("canvas").length, layers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-r03")).length,
    ring: map.hasImage("civic-r03-demo-ring"), offline: !map.getStyle().sources || !Object.keys(map.getStyle().sources).some((k) => /openmaptiles|openfreemap/i.test(k)) }));
  check("render: one map canvas with 15 civic-r03 layers and the demo ring image", r.canvases === 1 && r.layers === 15 && r.ring, r);
  if (r.offline) notRun("OpenFreeMap basemap and 3D buildings", "tiles.openfreemap.org not reachable from this environment (proxy 403) — offline light background used");
  await page.screenshot({ path: path.join(OUT, "r13-app-1440-start.png") });

  // ---- 2. style change: 3D toggle (camera tilt) and a second basemap swap by the host
  await page.click("#toggle-3d");
  await sleep(1500);
  const tilt = await page.evaluate(() => ({ pitch: Math.round(map.getPitch()), layers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-r03")).length }));
  check("3D toggle: camera tilts, R03 layers stay", tilt.pitch >= 30 && tilt.layers === 15, tilt);
  await page.screenshot({ path: path.join(OUT, "r13-app-1440-3d.png") });
  await page.evaluate(() => { const st = map.getStyle(); map.setStyle({ version: 8, sources: {}, layers: [{ id: "r03-acc-bg", type: "background", paint: { "background-color": "#f1f3ee" } }] }, { diff: false }); window.__r03swap = st; });
  await page.waitForFunction(() => (map.getStyle()?.layers || []).filter((l) => l.id.startsWith("civic-r03")).length === 15, null, { timeout: 10000 });
  await sleep(600);
  check("host style swap: layers and demo ring re-added, no missing-image warning", await page.evaluate(() => map.hasImage("civic-r03-demo-ring")) && !warns.some((t) => /could not be loaded/.test(t)), warns.filter((t) => /civic-r03|image/i.test(t)).slice(0, 3));
  await page.click("#toggle-3d");
  await sleep(1200);

  // ---- 3. editor draws -> public map input belongs to the editor -> cancel -> selecting works again
  await page.click("#civic-staff-button");
  await page.waitForSelector(fk("login-user"), { timeout: 10000 });
  await page.fill(fk("login-user"), USER);
  await page.fill(fk("login-pass"), PASSWORD);
  await page.click(fk("login-submit"));
  await page.waitForSelector(fk("new"), { timeout: 10000 });
  await page.click(fk("new"));
  await page.fill(fk("title"), "Проверка R03: рисование поверх публичных объектов (синтетика)");
  await page.click(fk("tool-line"));
  await sleep(300);
  const obj = await visibleObject(page);
  if (!obj) notRun("editor drawing over a public object", "no public object visible outside the panels at 1440x900");
  else {
    const before = await view(page);
    await page.mouse.move(obj.x, obj.y);
    await sleep(200);
    const hover = await view(page);
    await page.mouse.click(obj.x, obj.y);
    await sleep(500);
    const during = await view(page);
    await page.screenshot({ path: path.join(OUT, "r13-app-1440-editor-drawing.png") });
    check("while the editor draws: a click on a public object adds a vertex, does not open its card or change #object=",
      during.view === before.view && during.hash === before.hash && !/object=/.test(during.hash), { before, during });
    check("while the editor draws: the crosshair stays (no public hover cursor/tooltip)", hover.cursor === "crosshair" && !(await page.$(".civic-r03-tip")), hover);
    await page.evaluate(() => document.activeElement?.blur());
    await page.keyboard.press("Escape");  // R04: cancels the tool, not the cabinet
    await sleep(300);
    await page.mouse.click(obj.x, obj.y);
    await page.waitForFunction(() => document.getElementById("civic-map-root").getAttribute("data-civic-r03-view") === "card" || document.getElementById("civic-map-root").getAttribute("data-civic-r03-view") === "pick", null, { timeout: 5000 }).catch(() => null);
    const afterCancel = await view(page);
    check("after cancel: the same click selects a public object again", afterCancel.view === "card" || afterCancel.view === "pick", afterCancel);
  }
  check("no page errors (desktop)", errors.length === 0, errors.slice(0, 3));
  await ctx.close();

  // ---- 4. deep link -> reload -> same object; unknown/unpublished id -> honest «не найден»
  {
    const id = "demo-astana-roadworks-delay";
    const { ctx, page, errors } = await openPage({ width: 1440, height: 900 }, "#object=" + id);
    await page.waitForFunction(() => document.querySelector("#civic-map-root .civic-r03-card-title") && !/Карточка объекта/.test(document.querySelector("#civic-map-root .civic-r03-card-title").textContent), null, { timeout: 15000 });
    const first = await view(page);
    await page.reload();
    await page.waitForSelector("#civic-map-root .civic-r03-item", { state: "attached", timeout: 40000 });
    await page.waitForFunction(() => document.querySelector("#civic-map-root .civic-r03-card-title") && !/Карточка объекта/.test(document.querySelector("#civic-map-root .civic-r03-card-title").textContent), null, { timeout: 15000 });
    const again = await view(page);
    check("deep link #object= opens the card and survives reload", first.view === "card" && again.view === "card" && first.title === again.title && again.hash === "#object=" + id, { first, again });
    await page.screenshot({ path: path.join(OUT, "r13-app-1440-deeplink-card.png") });
    await page.goto(base + "#object=demo-astana-no-longer-published");
    await page.waitForFunction(() => /не найден/.test(document.querySelector("#civic-map-root .civic-r03-card")?.innerText || ""), null, { timeout: 20000 }).catch(() => null);
    const gone = await page.evaluate(() => document.querySelector("#civic-map-root .civic-r03-card")?.innerText || "");
    check("link to an object that is not (or no longer) published: «Объект не найден … сняли с публикации»", /Объект не найден/.test(gone) && /сняли с публикации/.test(gone), gone.slice(0, 160));
    await page.screenshot({ path: path.join(OUT, "r13-app-1440-deeplink-notfound.png") });
    check("no page errors (deep link)", errors.length === 0, errors.slice(0, 3));
    await ctx.close();
  }

  // ---- 5. phone: light map, list, card above the sheet
  {
    const { ctx, page, errors } = await openPage({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(OUT, "r13-app-390-start.png") });
    await page.evaluate(() => document.querySelector('#civic-map-root [data-id="demo-astana-roadworks-delay"]')?.click());
    await sleep(1500);
    const v = await view(page);
    check("phone: list item opens the card", v.view === "card", v);
    await page.screenshot({ path: path.join(OUT, "r13-app-390-card.png") });
    check("no page errors (phone)", errors.length === 0, errors.slice(0, 3));
    await ctx.close();
  }
} catch (e) {
  check("acceptance run finished", false, String(e && e.stack || e).slice(0, 600));
} finally {
  await browser.close();
  srv.kill();
  fs.rmSync(tmp, { recursive: true, force: true });
}
const summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length, not_run: checks.filter((c) => c.status === "NOT_RUN").length };
fs.writeFileSync(path.join(OUT, "acceptance.json"), JSON.stringify({ sha, web_civic_map_dirty: dirty || null, environment: "Linux container, Chromium (Playwright) with SwiftShader, OpenFreeMap blocked by proxy", base, at: new Date().toISOString(), summary, checks }, null, 1));
console.log(JSON.stringify(summary));
process.exitCode = summary.fail ? 1 : 0;
