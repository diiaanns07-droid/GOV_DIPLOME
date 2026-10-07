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

      // ---- street search: same-name streets are labelled by district; keyboard and touch both work
      const input = page.locator(".civic-explore-field input");
      await input.click();
      await input.fill("Кабанбай");
      await page.waitForSelector("#civic-explore-listbox:not([hidden]) [role=option]", { timeout: 8000 });
      const opts = await page.$$eval("#civic-explore-listbox [role=option]", (els) => els.map((e) => ({
        name: e.querySelector(".civic-explore-opt-name").textContent, place: e.querySelector(".civic-explore-opt-place").textContent })));
      check(`${tag}: ambiguous search lists variants with a readable place, no raw coordinates`,
        opts.length >= 2 && opts.every((o) => /район|окрестности/.test(o.place) && !/\d+\.\d{3}/.test(o.place + o.name)), opts.slice(0, 4));
      await page.screenshot({ path: path.join(OUT, `02_search_${tag}.png`) });
      const zoomBefore = await page.evaluate(() => map.getZoom());
      if (w < 761) await page.locator("#civic-explore-listbox [role=option]").nth(1).tap();
      else { await input.press("ArrowDown"); await input.press("ArrowDown"); await input.press("Enter"); }
      await page.waitForTimeout(1300);
      const chosen = await page.evaluate(() => ({ value: document.querySelector(".civic-explore-field input").value,
        listHidden: document.getElementById("civic-explore-listbox").hidden, status: document.querySelector(".civic-explore-status").textContent,
        zoom: map.getZoom() }));
      check(`${tag}: choosing a variant (${w < 761 ? "tap" : "arrows + Enter"}) frames the street and says where`,
        chosen.listHidden && /Кабанбай/.test(chosen.value) && /Показана улица/.test(chosen.status) && chosen.zoom > zoomBefore + 1, chosen);
      const pinFree = await page.evaluate(() => {
        const pin = document.querySelector(".civic-explore-pin");
        if (!pin) return { pin: false };
        const p = pin.getBoundingClientRect();
        const hits = ["#civic-panel", ".civic-explore", ".map-tools", ".topbar"].filter((sel) => {
          const e = document.querySelector(sel); if (!e || !e.getClientRects().length) return false;
          const b = e.getBoundingClientRect();
          return Math.min(p.right, b.right) - Math.max(p.left, b.left) > 1 && Math.min(p.bottom, b.bottom) - Math.max(p.top, b.top) > 1;
        });
        return { pin: true, rect: [p.left, p.top, p.right, p.bottom].map(Math.round), covered: hits, inView: p.left >= 0 && p.right <= innerWidth && p.top >= 0 && p.bottom <= innerHeight };
      });
      check(`${tag}: chosen street is marked in the free map area (not under panel/navigation/tools)`, pinFree.pin && pinFree.inView && pinFree.covered.length === 0, pinFree);
      await page.screenshot({ path: path.join(OUT, `03_street_${tag}.png`) });
      await input.fill("Егемен Қазақстан");
      await page.waitForSelector("#civic-explore-listbox:not([hidden]) [role=option]", { timeout: 8000 });
      const longName = await page.evaluate(() => { const l = document.getElementById("civic-explore-listbox"), b = l.getBoundingClientRect();
        return { overflowX: l.scrollWidth - l.clientWidth, inside: b.left >= 0 && b.right <= innerWidth, first: l.querySelector(".civic-explore-opt-name")?.textContent,
          pageScrollW: document.documentElement.scrollWidth }; });
      check(`${tag}: long Kazakh street name wraps inside the list (no sideways scroll)`, longName.overflowX <= 1 && longName.inside && longName.pageScrollW <= w && /Егемен/.test(longName.first || ""), longName);
      await input.press("Escape");
      const afterEsc1 = await page.evaluate(() => ({ listHidden: document.getElementById("civic-explore-listbox").hidden, value: document.querySelector(".civic-explore-field input").value }));
      await input.press("Escape");
      const afterEsc2 = await page.evaluate(() => document.querySelector(".civic-explore-field input").value);
      check(`${tag}: Escape closes the list, second Escape clears the field`, afterEsc1.listHidden && afterEsc1.value !== "" && afterEsc2 === "", { afterEsc1, afterEsc2 });
      await input.fill("Сарыарка");
      await page.click(".civic-explore-clear");
      const cleared = await page.evaluate(() => ({ value: document.querySelector(".civic-explore-field input").value, focused: document.activeElement === document.querySelector(".civic-explore-field input"),
        clearHidden: document.querySelector(".civic-explore-clear").hidden }));
      check(`${tag}: clear button empties the field and keeps focus`, cleared.value === "" && cleared.focused && cleared.clearHidden, cleared);
      check(`${tag}: no page errors`, page.errs.length === 0, page.errs);
      await ctx.close();
    }

    // ---- street index loading and failure (phone): honest states, retry, district navigation still works
    {
      const mobile = { width: 360, height: 800 };
      const ctx = await browser.newContext({ viewport: mobile, isMobile: true, hasTouch: true });
      const page = await ctx.newPage();
      let release, failNext = true;
      const gate = new Promise((r) => (release = r));
      await page.route("**/civic/map/streets.json", async (route) => {
        if (failNext) { failNext = false; await gate; return route.fulfill({ status: 503, body: "unavailable" }); }
        return route.continue();
      });
      await page.goto(base);
      await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady, null, { timeout: 40000 });
      await page.waitForSelector(".civic-explore", { timeout: 15000 });
      const input = page.locator(".civic-explore-field input");
      await input.fill("Кабанбай");
      const loading = await page.textContent(".civic-explore-status");
      release();
      await page.waitForSelector(".civic-explore-retry", { timeout: 8000 });
      const failed = await page.textContent(".civic-explore-status");
      check("360x800: index loading and failure are stated, not a silent empty list", /Загружаем список улиц/.test(loading) && /недоступен/.test(failed), { loading, failed });
      const cityZoom = await page.evaluate(() => map.getZoom());
      await page.selectOption(".civic-explore select", { index: 1 });
      await page.waitForTimeout(2000);
      const district = await page.evaluate(() => ({ zoom: map.getZoom(), value: document.querySelector(".civic-explore select").value,
        retryKept: !!document.querySelector(".civic-explore-retry") }));
      check("360x800: district navigation works while street search is down (retry stays offered)",
        !!district.value && district.zoom > cityZoom + 0.3 && district.retryKept, { cityZoom, ...district });
      await page.click(".civic-explore-retry");
      await input.fill("Кабанбай");
      const recovered = await page.waitForSelector("#civic-explore-listbox:not([hidden]) [role=option]", { timeout: 8000 }).then(() => true).catch(() => false);
      check("360x800: retry loads the street index", recovered);
      await page.screenshot({ path: path.join(OUT, "04_search_recovered_360x800.png") });
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
