#!/usr/bin/env node
/*
 * R09 · эталон A, правило 5 Linear «список ↔ карта»: «Обращения» акимата (R09) и значки карты жалоб (R07) в НАСТОЯЩЕМ
 * приложении (сборка R01 с путями R09 и модулем R07).
 *   node tests/civic/R09/hover_r09.cjs --root <сборка> [--screenshots <папка>]
 * Наведение на строку «Обращений» → значок места на карте подсвечен (.r07-badge--hot); уход — подсветка снята;
 * наведение на значок → строка подсвечена (.bk-lrow.is-hover). Событие — window "birge:target-hover" { kind, id, source }.
 * Подсветку значка делает R07 (research/round-14-results/R09/R07_target_hover.patch); без неё — FAIL с пояснением.
 * Сервер: python3 -B app.py с CIVIC_DEMO=1 на временной SQLite (как app_demo_r09.cjs). Ничего не пишет в репозиторий.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const os = require("os");
const net = require("net");
const { spawn, execSync } = require("child_process");

function loadPlaywright() {
  try { return require("playwright"); } catch (e) {
    return require(path.join(execSync("npm root -g").toString().trim(), "playwright"));
  }
}
const { chromium } = loadPlaywright();
const args = process.argv.slice(2);
const ROOT = path.resolve(args.includes("--root") ? args[args.indexOf("--root") + 1] : path.resolve(__dirname, "../../.."));
const SHOTS = args.includes("--screenshots") ? path.resolve(args[args.indexOf("--screenshots") + 1]) : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
const STOP = [71.406553, 51.131155];   // остановка «Хан Шатыр» демо (OSM node 4109037549)
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined ? " — " + JSON.stringify(detail).slice(0, 300) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (a) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const staff = { user: "r09-hover", pass: "Linear-5-" + Math.random().toString(36).slice(2) + "-Aa1!" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${staff.user} --password-stdin`,
           { cwd: ROOT, env, input: staff.pass + "\n", stdio: ["pipe", "ignore", "inherit"] });
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) { srv.staff = staff; return srv; } } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r09-hover-"));
  const port = await freePort();
  let srv = null, browser = null;
  try {
    srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
    browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1, locale: "ru-RU" });
    await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", "ru"); } catch (e) {} });
    const page = await ctx.newPage();
    const base = `http://127.0.0.1:${port}/`;
    await page.goto(base);
    await shellReady(page);
    const logged = await page.evaluate(async ([u, p]) => (await fetch("/api/civic/v1/session/login", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) })).ok, [srv.staff.user, srv.staff.pass]);
    await page.reload();
    await shellReady(page);
    await page.evaluate(() => window.BirgeShell?.setMode?.("akimat"));
    await sleep(1500);
    const hasSection = await page.evaluate(() => !!window.BirgeComplaintList && !!window.BirgeShell?.setSection);
    check("сотрудник вошёл, есть раздел «Обращения»", logged && hasSection, { logged, hasSection });
    if (!hasSection) return;
    // Значки мест (не районов) — на крупном масштабе: карта у остановки «Хан Шатыр» демо, затем раздел «Обращения».
    await page.evaluate((c) => map.jumpTo({ center: c, zoom: 16 }), STOP);
    await page.waitForFunction(() => document.querySelectorAll(".r07-badge[data-key]:not([data-key^='district:'])").length > 0, null, { timeout: 15000 }).catch(() => null);
    await page.evaluate(() => window.BirgeShell.setSection("complaints"));
    await page.waitForSelector(".bc-inbox__item .bk-lrow", { timeout: 10000 });
    await sleep(500);
    // Строка, у места которой на карте есть свой значок (не в кластере).
    const pick = await page.evaluate(() => {
      const keys = new Set([...document.querySelectorAll(".r07-badge[data-key]")].map((b) => b.dataset.key));
      const rows = [...document.querySelectorAll(".bc-inbox__item[data-target]")];
      for (const li of rows) {
        const id = li.getAttribute("data-target");
        const key = [...keys].find((k) => k.slice(k.indexOf(":") + 1) === id);
        if (key) return { id, key, index: rows.indexOf(li), badges: keys.size, rows: rows.length };
      }
      return { id: null, badges: keys.size, rows: rows.length };
    });
    check(`есть строка «Обращений» со значком на карте (${pick.rows} строк, ${pick.badges} значков)`, !!pick.id, pick);
    if (!pick.id) return;
    const row = page.locator(".bc-inbox__item[data-target]").nth(pick.index).locator(".bc-inbox__row");
    const events = [];
    await page.exposeFunction("r09HoverLog", (d) => events.push(d));
    await page.evaluate(() => window.addEventListener("birge:target-hover", (e) => window.r09HoverLog(e.detail)));
    await row.hover();
    await sleep(300);
    const hot = await page.evaluate((key) => {
      const b = document.querySelector('.r07-badge[data-key="' + CSS.escape(key) + '"]');
      return { hot: !!b && b.classList.contains("r07-badge--hot"), others: document.querySelectorAll(".r07-badge--hot").length };
    }, pick.key);
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "hover-row.png") });
    check("наведение на строку — событие birge:target-hover { source: inbox } с местом строки",
          events.some((d) => d && d.source === "inbox" && d.id === pick.id), events.slice(-3));
    check("наведение на строку — значок этого места на карте подсвечен (R07 .r07-badge--hot)", hot.hot && hot.others === 1,
          hot.hot ? hot : Object.assign(hot, { why: "R07 не слушает birge:target-hover — нужен R07_target_hover.patch" }));
    await page.mouse.move(5, 760);
    await sleep(300);
    const off = await page.evaluate(() => document.querySelectorAll(".r07-badge--hot").length);
    check("уход со строки — подсветка значка снята", off === 0, { hot: off });
    // Обратно: значок под мышью → строка подсвечена (как у «Горячих мест» R07).
    await page.evaluate((key) => document.querySelector('.r07-badge[data-key="' + CSS.escape(key) + '"]')
      .dispatchEvent(new MouseEvent("mouseenter")), pick.key);
    await sleep(300);
    const lit = await page.evaluate((id) => {
      const li = document.querySelector('.bc-inbox__item[data-target="' + CSS.escape(id) + '"]');
      // У места может быть несколько строк (разные темы/статусы) — подсвечены все строки этого места и только они.
      const same = document.querySelectorAll('.bc-inbox__item[data-target="' + CSS.escape(id) + '"]').length;
      return { row: !!li && li.querySelector(".bk-lrow").classList.contains("is-hover"), all: document.querySelectorAll(".bc-inbox .is-hover").length, same };
    }, pick.id);
    check("наведение на значок — строки этого места в «Обращениях» подсвечены (.bk-lrow.is-hover)", lit.row && lit.all === lit.same,
          lit.row ? lit : Object.assign(lit, { why: "R07 не шлёт birge:target-hover с карты — нужен R07_target_hover.patch" }));
    await page.evaluate((key) => document.querySelector('.r07-badge[data-key="' + CSS.escape(key) + '"]')
      .dispatchEvent(new MouseEvent("mouseleave")), pick.key);
    await sleep(300);
    const gone = await page.evaluate(() => document.querySelectorAll(".bc-inbox .is-hover").length);
    check("уход со значка — подсветка строки снята", gone === 0, { lit: gone });
    await ctx.close();
  } catch (e) {
    check("прогон без исключений", false, String(e && e.stack || e).slice(0, 400));
  } finally {
    if (browser) await browser.close();
    if (srv) { srv.kill(); await new Promise((r) => (srv.exitCode !== null ? r() : srv.once("exit", r))); }
    fs.rmSync(tmp, { recursive: true, force: true });
    const ok = results.filter((r) => r.ok).length;
    console.log(`ИТОГ: ${ok}/${results.length} ${ok === results.length ? "PASS" : "FAIL"}`);
    process.exitCode = ok === results.length ? 0 : 1;
  }
})();
