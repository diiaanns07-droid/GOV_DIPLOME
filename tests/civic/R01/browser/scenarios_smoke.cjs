// R01: R07 scenario comparison inside the integrated page (same map, drawer, real API).
// Usage: node tests/civic/R01/browser/scenarios_smoke.cjs <out_dir>
"use strict";
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "scen-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff/i;
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null }); console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined ? " — " + JSON.stringify(detail) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "civic-scen-"));
  const port = await freePort(), base = `http://127.0.0.1:${port}/`;
  const srv = spawn("python3", ["-B", "app.py", "--port", String(port)], { cwd: REPO, env: { ...process.env, CIVIC_DB_PATH: path.join(dbDir, "civic.sqlite3") }, stdio: ["ignore", "pipe", "pipe"] });
  let log = ""; srv.stdout.on("data", (d) => (log += d)); srv.stderr.on("data", (d) => (log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(base + "api/health")).ok) break; } catch {} await sleep(200); }
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const result = { base, checks };
  try {
    for (const [w, h, extra, tag] of [[1440, 900, {}, "1440"], [390, 844, { isMobile: true, hasTouch: true, deviceScaleFactor: 2 }, "390"]]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, ...extra });
      const page = await ctx.newPage(); const errs = [];
      page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
      page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) errs.push(m.type() + ": " + m.text()); });
      await page.goto(base + "?tools=all");  // scenarios are hidden from Birge without it
      await page.evaluate(() => localStorage.clear());
      await page.goto(base + "?tools=all");  // scenarios are hidden from Birge without it
      await page.waitForFunction(() => window.CivicShell?.mode === "civic" && mapReady && window.CivicShell.modules?.scenarios, null, { timeout: 40000 });
      const status = await page.evaluate(() => window.CivicShell.modules.scenarios.status);
      check(`[${tag}] scenarios module ready on server`, status === "ready", status);
      // Round 14: a phone opens in the resident view where akimat tools are hidden; this smoke tests the tool itself.
      if (w < 761) await page.evaluate(() => window.BirgeShell?.setMode("akimat"));
      if (w < 761) await page.click("#civic-sheet-handle");
      await page.click("#civic-scenarios-button");
      await page.waitForSelector("#civic-scenarios-root .civic-r07-panel select", { timeout: 15000 });
      await page.waitForFunction(() => document.querySelectorAll("#civic-scenarios-root select")[1]?.options.length > 1, null, { timeout: 15000 });
      const graphs = await page.evaluate(() => [...document.querySelectorAll("#civic-scenarios-root select")[0].options].map((o) => o.textContent));
      check(`[${tag}] driving graph shown as NOT_READY, synthetic labelled`, graphs.some((t) => /NOT_READY/.test(t)) && graphs.some((t) => /СИНТЕТИКА/.test(t)), graphs);
      // prepared K03 Astana pedestrian case
      const caseValue = await page.evaluate(() => { const sel = document.querySelectorAll("#civic-scenarios-root select")[1]; const opt = [...sel.options].find((o) => o.value); return opt && opt.value; });
      await page.selectOption("#civic-scenarios-root select >> nth=1", caseValue);
      await page.waitForTimeout(800);
      await page.click("#civic-scenarios-root button:has-text('Сравнить')");
      await page.waitForFunction(() => /A|B/.test(document.querySelector("#civic-scenarios-root .civic-r07-panel")?.textContent || "") && !document.querySelector("#civic-scenarios-root .civic-r07-panel button:disabled"), null, { timeout: 30000 });
      await page.waitForTimeout(1200);
      const state = await page.evaluate(() => ({
        layers: map.getStyle().layers.filter((l) => l.id.startsWith("civic-r07-")).length,
        canvases: document.querySelectorAll("canvas").length, scrollW: document.documentElement.scrollWidth,
        limits: document.querySelector(".civic-scenario-limits")?.offsetParent !== null,
        attribution: /ODbL/.test(document.querySelector("#civic-scenarios .civic-attribution")?.textContent || ""),
        text: document.querySelector("#civic-scenarios-root").textContent.slice(0, 4000),
      }));
      check(`[${tag}] comparison drawn on the same map`, state.layers > 0 && state.canvases === 1, { layers: state.layers, canvases: state.canvases });
      check(`[${tag}] limits and ODbL attribution visible`, state.limits && state.attribution);
      // Mentions of traffic/CO2/travel time are allowed only as disclaimers (sentence with a negation).
      const claims = state.text.split(/(?<=[.!?;])\s+/).filter((t) => /пробк|CO2|выброс|время в пути|минут/i.test(t) && !/(^|[^а-яё])(не|нет|без)([^а-яё]|$)/i.test(t));
      check(`[${tag}] no traffic/CO2/travel-time claims (disclaimers only)`, claims.length === 0, claims);
      check(`[${tag}] no horizontal scroll`, state.scrollW <= w, state.scrollW);
      await page.screenshot({ path: path.join(OUT, `scenarios_${tag}.png`) });
      await page.click("#civic-scenarios [data-close=scenarios]");
      await page.waitForTimeout(500);
      const after = await page.evaluate(() => map.getStyle().layers.filter((l) => l.id.startsWith("civic-r07-")).length + Object.keys(map.getStyle().sources).filter((s) => s.startsWith("civic-r07-")).length);
      check(`[${tag}] closing the drawer removes R07 layers/sources`, after === 0, after);
      check(`[${tag}] no page errors`, errs.length === 0, errs);
      await ctx.close();
    }
  } catch (error) {
    check("scenario flow completed", false, String(error && error.stack || error).slice(0, 1200));
  } finally {
    await browser.close(); srv.kill(); fs.rmSync(dbDir, { recursive: true, force: true });
  }
  result.summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length };
  fs.writeFileSync(path.join(OUT, "scenarios_smoke.json"), JSON.stringify(result, null, 1) + "\n");
  console.log(JSON.stringify(result.summary));
  process.exit(result.summary.fail ? 1 : 0);
})();
