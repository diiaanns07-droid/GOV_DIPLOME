// R01 round 14: screenshots of the main Birge screens for review (R11 UX, R10 acceptance, the owner).
//   akimat and resident × 1366 and 375 × ru and kk; akimat 1366 also with the «Что построить?» catalog open.
// Usage: node tests/civic/R01/browser/r14_shots.cjs <out_dir>
// Starts `python3 -B app.py` with CIVIC_DEMO=1 on a temporary SQLite file (synthetic demo data only).
// Not a pass/fail test: prints a short layout report (horizontal scroll, overlaps of fixed overlays) per shot.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r14-shots-out");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

// Visible boxes of overlays that must not cover each other on the map.
const layout = (page) => page.evaluate(() => {
  const box = (sel) => {
    const n = document.querySelector(sel);
    if (!n || !n.getClientRects().length || getComputedStyle(n).visibility === "hidden") return null;
    const r = n.getBoundingClientRect();
    return r.width && r.height ? { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right), b: Math.round(r.bottom) } : null;
  };
  const boxes = { legend: box(".r07-maplegend"), catalog: box('.b3d-dock[data-state="catalog"]'), toggle: box(".birge-b3d-toggle"),
    explore: box(".civic-explore"), panel: box("#civic-panel"), tools: box(".map-tools"), fab: box(".bc-fab") };
  const hit = (a, b) => a && b && a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;
  const names = Object.keys(boxes), overlaps = [];
  for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++)
    if (hit(boxes[names[i]], boxes[names[j]]) && !(names[i] === "explore" && names[j] === "panel")) overlaps.push(names[i] + "×" + names[j]);
  const small = [...document.querySelectorAll("body *")].filter((n) => n.childNodes.length && [...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim())
    && n.getClientRects().length && getComputedStyle(n).visibility !== "hidden" && parseFloat(getComputedStyle(n).fontSize) < 14
    && !n.closest(".maplibregl-ctrl-attrib, [hidden], .birge-day")).slice(0, 8).map((n) => n.className + ": " + n.textContent.trim().slice(0, 30) + " (" + getComputedStyle(n).fontSize + ")");
  return { scrollX: document.documentElement.scrollWidth > innerWidth, overlaps, small };
});

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-shots-"));
  const port = await freePort();
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  try {
    for (const [w, h] of [[1366, 768], [375, 812]]) for (const lang of ["ru", "kk"]) for (const mode of ["akimat", "resident"]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
      await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) {} }, [mode, lang]);
      const page = await ctx.newPage();
      await page.goto(`http://127.0.0.1:${port}/`);
      await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
        && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});
      await page.waitForTimeout(1500);
      const name = `${mode}-${w}-${lang}`;
      await page.screenshot({ path: path.join(OUT, name + ".png") });
      console.log(name, JSON.stringify(await layout(page)));
      if (mode === "akimat" && await page.$(".birge-b3d-toggle")) {
        if (w < 761) await page.evaluate(() => document.querySelector("#civic-sheet-handle")?.click());  // шторка вниз
        await page.waitForTimeout(400);
        const toggle = await page.$(".birge-b3d-toggle");
        if (toggle && await toggle.isVisible()) {
          await toggle.click();
          await page.waitForTimeout(600);
          await page.screenshot({ path: path.join(OUT, name + "-catalog.png") });
          console.log(name + "-catalog", JSON.stringify(await layout(page)));
        }
      }
      await ctx.close();
    }
  } finally {
    await browser.close();
    srv.kill();
  }
}
main().catch((e) => { console.error(e); process.exit(1); });
