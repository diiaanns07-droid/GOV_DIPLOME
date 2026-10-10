// R01 round 14, build B1: the demo path across modules in one app (CONTRACT §0, steps 1–4 and 6).
//   resident: «Сообщить о проблеме» (R09) -> place on the map -> text and category -> sent (B-0001)
//             -> the target is on the heat map (R07) with +1 person -> «Мои обращения» shows it
//   akimat:   «Картина дня» (R08) counts the new complaint; a hot place opens its target on the map
//             -> target card «Взять в работу» -> «Отметить исправленным» (R07 buttons, R09 staff API via the shell)
// Usage: node tests/civic/R01/browser/r14_b1.cjs <out_dir>
// Starts `python3 -B app.py` with CIVIC_DEMO=1 (synthetic R07 complaints, flagged demo) on a temporary SQLite file.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r14-b1-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet/i;
const R03_RING = /civic-r03-demo-ring/;  // known R12/R03 map race, reported separately (BUILD_LOG)
const USER = "operator", PASSWORD = "Tz7-qerB-91vk-Lmsd";
const NURA = [71.4148, 51.1131];
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: ["pipe", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run(`create-editor ${USER} --password-stdin`, PASSWORD + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
  && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).then(() => page.waitForTimeout(800));
// Sum of people over all heat targets (30 days) — what the map shows.
const heatPeople = (page) => page.evaluate(async () => {
  const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=16")).json();
  return d.items.reduce((a, it) => a + (it.count || 0), 0);
});
// Click the map at a lon/lat (the point is panned into the free part of the map first).
async function clickMapAt(page, lngLat) {
  const xy = await page.evaluate((p) => {
    const c = map.getCanvas().getBoundingClientRect();
    map.jumpTo({ center: p, zoom: 15 });
    const q = map.project(p);
    return { x: c.left + q.x, y: c.top + q.y };
  }, lngLat);
  await page.waitForTimeout(400);
  await page.mouse.click(xy.x, xy.y);
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-b1-"));
  const port = await freePort();
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const errs = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
    page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) errs.push(m.type() + ": " + m.text()); });
    await page.addInitScript(() => { try { if (!localStorage.getItem("birge.mode")) localStorage.setItem("birge.mode", "resident"); } catch (e) {} });
    await page.goto(base);
    await ready(page);
    const modules = await page.evaluate(async () => (await (await fetch("/api/civic/v2/modules")).json()).modules);
    check("B1: complaints (R09), heat (R07), day summary (R08) are connected",
      ["complaints.create", "complaints.mine", "heat", "heat.target", "akim.summary"].every((k) => modules[k]?.status === "ready"),
      Object.fromEntries(Object.entries(modules).map(([k, v]) => [k, v.status])));
    const heatState = await page.evaluate(() => window.CivicShell.heat.state());
    check("resident: heat map is in the panel, soft resident view, demo complaints flagged", heatState.role === "resident" && heatState.items > 0, heatState);
    const before = await heatPeople(page);

    // ---- step 1–2: the resident reports a problem
    const fab = await page.evaluate(() => { const b = document.querySelector(".bc-fab"); return b && getComputedStyle(b).display !== "none" ? b.textContent.trim() : null; });
    check("resident: one main button «Сообщить о проблеме»", fab === "Сообщить о проблеме", fab);
    await page.click(".bc-fab");
    await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 });
    await clickMapAt(page, NURA);
    await page.waitForSelector(".bc-panel[data-step='3'], .bc-option", { timeout: 10000 });
    if (await page.$(".bc-option.bk-btn--ghost")) await page.click(".bc-option.bk-btn--ghost");
    else if (await page.$(".bc-option--first")) await page.click(".bc-option--first");
    await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 10000 });
    const place = (await page.textContent(".bc-place")) || "";
    check("resident: place chosen (no R12 yet — «примерное место» area, the complaint still has a target)", place.trim().length > 3, place.trim());
    await page.fill("#bc-text", "На остановке вечером темно, не горят фонари");
    await page.waitForSelector(".bc-grid, .bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 8000 });
    if (await page.$(".bc-grid")) await page.click(".bc-grid__chip:nth-child(5)");  // «Освещение» (no R04 model yet)
    await page.click(".bc-send");
    await page.waitForSelector(".bc-panel[data-step='4'], .bc-panel[data-step='5']", { timeout: 15000 });
    if (await page.$(".bc-panel[data-step='4']")) await page.click(".bc-different");
    await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 15000 });
    const code = ((await page.textContent(".bc-code__value")) || "").trim();
    check("resident: sent, complaint number shown", /^B-\d{4,}$/.test(code), code);
    await page.screenshot({ path: path.join(OUT, "01_resident_sent_1366.png") });

    // ---- step 3: the target is on the heat map with one more person
    let after = before;
    for (let i = 0; i < 10 && after === before; i++) { await sleep(300); after = await heatPeople(page); }
    check("heat map counts the new complaint at once (+1 person)", after === before + 1, { before, after });
    const mine = await page.evaluate(async () => {
      const r = await fetch("/api/civic/v2/complaints/mine", { headers: { "X-Birge-Device": localStorage.getItem("birge.device") || "" } });
      return { status: r.status, body: await r.json() };
    });
    const items = mine.body?.data?.items || mine.body?.data || [];
    const own = Array.isArray(items) ? items[0] : null;
    check("«Мои обращения» API returns the complaint for this device", mine.status === 200 && !!own?.target?.id, { status: mine.status, own: own && { id: own.id, target: own.target } });
    // Accuracy (CONTRACT §8): the resident's approximate place is drawn where they tapped, marked «примерное место».
    const geo = await page.evaluate(async ([t, p]) => {
      const d = await (await fetch(`/api/civic/v2/heat/target?kind=${t.kind}&id=${encodeURIComponent(t.id)}&days=30`)).json();
      const ring = d.item?.geometry?.coordinates?.[0] || [];
      const xs = ring.map((c) => c[0]), ys = ring.map((c) => c[1]);
      return { inside: ring.length > 0 && p[0] >= Math.min(...xs) && p[0] <= Math.max(...xs) && p[1] >= Math.min(...ys) && p[1] <= Math.max(...ys),
        approximate: d.item?.approximate, district: d.item?.district, corner: ring[0], point: p };
    }, [own.target, Array.isArray(own.point) ? own.point : NURA]);
    check("map accuracy: the approximate-place cell contains the tapped point and is marked approximate", geo.inside && geo.approximate === true, geo);
    await page.click(".bc-panel[data-step='5'] .bk-btn--primary").catch(() => null);
    await page.keyboard.press("Escape");
    await page.click("#birge-header [data-action=mine]");
    const cards = await page.waitForSelector(".bc-mine__card", { timeout: 8000 }).then(() => page.$$eval(".bc-mine__card", (n) => n.length)).catch(() => 0);
    check("header «Мои обращения» opens the list with the sent complaint", cards >= 1, cards);
    await page.screenshot({ path: path.join(OUT, "02_resident_mine_1366.png") });
    await page.keyboard.press("Escape");

    // ---- step 4: akimat — «Картина дня»
    await page.click("#birge-header [data-mode=akimat]");
    const fabAkimat = await page.evaluate(() => getComputedStyle(document.querySelector(".bc-fab")).display);
    check("akimat: no «Сообщить о проблеме» button", fabAkimat === "none", fabAkimat);
    await page.click("#birge-header [data-section=day]");
    await page.waitForSelector("#birge-day .akim-hot__item", { timeout: 15000 });
    const day = await page.evaluate(async () => ({ text: document.querySelector("#birge-day-root").innerText.slice(0, 300),
      api: (await (await fetch("/api/civic/v2/akim/summary")).json()).kpi?.new_day?.value }));
    check("«Картина дня» opens inside Birge and counts today's complaints (incl. the new one)", day.api >= 1 && /Картина дня/.test(day.text), day);
    await page.screenshot({ path: path.join(OUT, "03_day_1366.png") });
    await page.click("#birge-day .akim-hot__item");
    // R07 >= 306074b сначала плавно ведёт камеру к цели (до ~1,2 с), потом выбирает её — ждём выбор, а не паузу.
    await page.waitForFunction(() => !!window.CivicShell.heat?.state?.().selected, null, { timeout: 8000 }).catch(() => {});
    const opened = await page.evaluate(() => ({ section: document.body.dataset.birgeSection, selected: window.CivicShell.heat.state().selected, hash: location.hash }));
    check("hot place in «Картина дня» opens its target on the map (no page reload)", opened.section === "map" && !!opened.selected, opened);
    await page.screenshot({ path: path.join(OUT, "04_hot_target_1366.png") });

    // ---- step 6: staff takes the complaint and marks it fixed from the target card
    await page.evaluate(([u, p]) => window.CivicShell.api.login(u, p), [USER, PASSWORD]);
    await page.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), own.target);
    await page.waitForSelector("[data-act='take'], [data-act='fixed']", { timeout: 10000 });
    if (await page.$("[data-act='take']")) {
      await page.click("[data-act='take']");
      await page.waitForTimeout(1200);
    }
    const status1 = await page.evaluate(async (id) => (await (await fetch("/api/civic/v2/complaints/" + id)).json()).data?.complaint?.status
      ?? (await (await fetch("/api/civic/v2/complaints/" + id)).json()).data?.status, own.id);
    check("«Взять в работу» on the target card changes the status (staff session + CSRF via the shell)", status1 === "in_progress", status1);
    await page.waitForSelector("[data-act='fixed']", { timeout: 10000 });
    await page.click("[data-act='fixed']");
    await page.waitForTimeout(1500);
    const fixed = await page.evaluate(async (id) => {
      const d = (await (await fetch("/api/civic/v2/complaints/" + id)).json()).data;
      return d?.complaint?.status ?? d?.status;
    }, own.id);
    const heatFixed = await page.evaluate(async (t) => {
      const d = await (await fetch(`/api/civic/v2/heat/target?kind=${t.kind}&id=${encodeURIComponent(t.id)}&days=30`)).json();
      return { fixed_until: d.item?.fixed_until ?? d.fixed_until ?? null, level: d.item?.level ?? d.level };
    }, own.target);
    check("«Отметить исправленным»: complaint fixed and the target turns green «исправлено» on the map", fixed === "fixed" && !!heatFixed.fixed_until, { fixed, heatFixed });
    await page.screenshot({ path: path.join(OUT, "05_fixed_1366.png") });
    const ring = errs.filter((e) => R03_RING.test(e)), other = errs.filter((e) => !R03_RING.test(e));
    check("no page errors or warnings", other.length === 0, other);
    if (ring.length) console.log("NOTE R03/R12 demo-ring map race seen " + ring.length + "× (reported to R12, not counted)");
    await ctx.close();
  } finally {
    await browser.close();
    srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length };
  fs.writeFileSync(path.join(OUT, "r14_b1.json"), JSON.stringify({ summary, checks }, null, 1));
  console.log(JSON.stringify(summary));
  process.exit(summary.fail ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
