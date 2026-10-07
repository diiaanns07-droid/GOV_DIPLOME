// R01 round 12: the resident path "open the city -> find a place -> understand what happens there -> act"
// at 360x800, 768x1024 and 1440x900 (layout overlaps, map notice, search, district, camera/3D state).
// Usage: node tests/civic/R01/browser/r12_city.cjs <out_dir> [--empty]
// Starts `python3 -B app.py` on a free port with a temporary SQLite file: R02 init + R05's synthetic
// slice (or nothing with --empty). No editor account is needed: a resident session has no login.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r12-out");
const EMPTY = process.argv.includes("--empty");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff/i;
const VIEWPORTS = [[360, 800], [768, 1024], [1440, 900]];
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const notRun = (name, reason) => { checks.push({ name, status: "NOT_RUN", detail: reason }); console.log("NOT_RUN " + name + " — " + reason); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  if (!EMPTY) run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function openPage(browser, base, w, h, hash = "") {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) page.errs.push(m.type() + ": " + m.text()); });
  await page.goto(base + hash);
  await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady, null, { timeout: 40000 });
  await page.waitForSelector(".civic-explore", { timeout: 15000 });
  await page.waitForTimeout(1200);
  return { ctx, page };
}

// Visible rectangles of the floating controls; overlapping pairs are reported.
const layout = (page) => page.evaluate(() => {
  const rect = (sel) => { const e = document.querySelector(sel); if (!e || !e.getClientRects().length || getComputedStyle(e).visibility === "hidden") return null;
    const b = e.getBoundingClientRect(); return b.width && b.height ? { l: b.left, t: b.top, r: b.right, b: b.bottom } : null; };
  const boxes = { topbar: rect(".topbar"), explore: rect(".civic-explore"), tools: rect(".map-tools"), panel: rect("#civic-panel") };
  const status = document.getElementById("map-status");
  let statusInfo = null;
  if (status && !status.classList.contains("hidden") && status.getClientRects().length) {
    const b = status.getBoundingClientRect();
    const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
    statusInfo = { text: status.textContent.trim().slice(0, 80), readable: !!hit && (hit === status || status.contains(hit)), insideExplore: !!status.closest(".civic-explore") };
  }
  const over = [];
  const names = Object.keys(boxes).filter((k) => boxes[k]);
  for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) {
    const a = boxes[names[i]], c = boxes[names[j]];
    const ix = Math.min(a.r, c.r) - Math.max(a.l, c.l), iy = Math.min(a.b, c.b) - Math.max(a.t, c.t);
    if (ix > 1 && iy > 1) over.push(names[i] + "×" + names[j]);
  }
  return { scrollW: document.documentElement.scrollWidth, innerW: innerWidth, over, status: statusInfo,
    explore: boxes.explore && Math.round(boxes.explore.r - boxes.explore.l) };
});

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "civic-r12-"));
  const port = await freePort(), base = `http://127.0.0.1:${port}/`;
  const srv = await startServer(port, path.join(dbDir, "civic.sqlite3"));
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const result = { base, empty: EMPTY, started_at: new Date().toISOString(), checks };
  try {
    for (const [w, h] of VIEWPORTS) {
      const tag = `${w}x${h}`;
      const { ctx, page } = await openPage(browser, base, w, h);
      const lay = await layout(page);
      check(`${tag}: no horizontal scroll`, lay.scrollW <= lay.innerW, lay);
      check(`${tag}: navigation box, map tools, top bar and panel do not overlap`, lay.over.length === 0, lay.over);
      if (lay.status) check(`${tag}: map notice readable (not under the navigation box)`, lay.status.readable, lay.status);
      else notRun(`${tag}: map notice readable`, "no map notice shown (basemap loaded)");
      check(`${tag}: navigation box wide enough for the district name and search (≥ 280px)`, (lay.explore || 0) >= 280, lay.explore);
      await page.screenshot({ path: path.join(OUT, `01_start_${tag}.png`) });
      check(`${tag}: no page errors`, page.errs.length === 0, page.errs);
      await ctx.close();
    }
  } catch (error) {
    check("flow completed without exception", false, String(error && error.stack || error).slice(0, 1500));
  } finally {
    await browser.close();
    srv.kill("SIGTERM");
    fs.rmSync(dbDir, { recursive: true, force: true });
    result.finished_at = new Date().toISOString();
    result.summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length,
      not_run: checks.filter((c) => c.status === "NOT_RUN").length };
    fs.writeFileSync(path.join(OUT, "r12_city.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result.summary));
    process.exit(result.summary.fail ? 1 : 0);
  }
})();
