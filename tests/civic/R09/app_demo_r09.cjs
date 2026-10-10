#!/usr/bin/env node
/*
 * R09 · шаги 1–2 сценария демо (DEMO_SCRIPT R01) в НАСТОЯЩЕМ приложении Birge (сборка R01), 375/1366 × ru/kk.
 *   node tests/civic/R09/app_demo_r09.cjs --root <checkout сборки R01 с путями R09> [--screenshots <папка>]
 * Сервер: python3 -B app.py с CIVIC_DEMO=1 на ВРЕМЕННОЙ SQLite (seed-demo R02 + демо-жалобы R09, если шлюз их сеет).
 * Путь жителя: «Сообщить о проблеме» → нажать прямо на значок/место остановки «Хан Шатыр» → «Это здесь?» →
 * текст демо вперемешку kk/ru → подсказка «Освещение» → «Об этом уже сообщили N человек» → «Я тоже» → N+1.
 * Каждый вариант — новое устройство (новый контекст браузера), поэтому N растёт от варианта к варианту.
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
const STOP = [71.406553, 51.131155];   // остановка «Хан Шатыр», OSM node 4109037549 (Нура)
const TEXT = "Аялдамада жарық жоқ, вечером на остановке темно";   // текст демо (DEMO_SCRIPT, шаг 1–2)
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ReadPixels/i;
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
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function shot(page, name) {
  if (SHOTS) { await sleep(450); await page.screenshot({ path: path.join(SHOTS, name + ".png") }); }
}

async function tapStop(page, width) {
  // Ставим остановку в середину свободной части карты (над шторкой на телефоне, слева от панели на ноутбуке).
  const xy = await page.evaluate(async (p) => {
    const c = map.getCanvas().getBoundingClientRect();
    const panel = document.querySelector(".bc-panel"); const r = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    const mobile = innerWidth < 1024;
    const want = { x: (c.left + (r && !mobile ? r.left : c.right)) / 2, y: (c.top + (r && mobile ? r.top : c.bottom)) / 2 };
    map.jumpTo({ center: p, zoom: 17 });
    const q = map.project(p);
    map.panBy([c.left + q.x - want.x, c.top + q.y - want.y], { duration: 0 });
    await new Promise((ok) => setTimeout(ok, 600));
    const now = map.project(p);
    return { x: c.left + now.x, y: c.top + now.y };
  }, STOP);
  await sleep(500);
  // Нажимаем ровно в точку остановки — там, где у R07 стоит значок с числом людей (B-019).
  const hit = await page.evaluate(([x, y]) => { const el = document.elementFromPoint(x, y); return el ? el.className.toString().slice(0, 60) : null; }, [xy.x, xy.y]);
  if (width < 1024) await page.touchscreen.tap(xy.x, xy.y); else await page.mouse.click(xy.x, xy.y);
  return hit;
}

async function variant(browser, base, width, height, lang) {
  const tag = `${width}-${lang}`;
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l]) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) {} }, [lang]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text()); });
  await page.goto(base);
  await page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
    && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });
  await sleep(800);
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 });
  const top = await page.evaluate(() => { const h = document.querySelector(".bc-panel .bc-close").getBoundingClientRect();
    const el = document.elementFromPoint(h.left + h.width / 2, h.top + h.height / 2); return !!(el && el.closest(".bc-panel")); });
  check(`${tag}: шторка жалобы сверху — кнопка «Закрыть» не перекрыта панелями карты`, top);
  await shot(page, `app-${tag}-1-place`);
  const hit = await tapStop(page, width);
  const offered = await page.waitForSelector(".bc-option--first", { timeout: 10000 }).then(() => true, () => false);
  const first = offered ? (await page.textContent(".bc-option--first")).trim() : "";
  check(`${tag}: нажатие на остановку (в том числе на значок карты) — «${first.slice(0, 40)}»`,
        /Хан Шатыр/.test(first), { hit });
  const approxHere = await page.$$eval(".bc-option", (n) => n.filter((x) => /Примерн|Шамамен/.test(x.textContent)
    && /Вы здесь|Сіз осындасыз/.test(x.textContent)).length);
  check(`${tag}: у «Примерного места» нет «Вы здесь»`, approxHere === 0);
  await shot(page, `app-${tag}-2-candidates`);
  if (!offered) { await ctx.close(); return; }
  await page.click(".bc-option--first");
  await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
  await page.fill("#bc-text", TEXT);
  const chip = await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 8000 })
    .then(async () => (await page.textContent(".bc-cat-row")).trim(), () => "");
  check(`${tag}: модель подсказывает «Освещение»`, /Освещение|Жарықтандыру/.test(chip), chip);
  await shot(page, `app-${tag}-3-text`);
  await page.click(".bc-send");
  await page.waitForSelector(".bc-panel[data-step='4'], .bc-panel[data-step='5']", { timeout: 15000 });
  const step4 = await page.$(".bc-panel[data-step='4']");
  const title = (await page.textContent(".bc-title")).trim();
  const n = Number((title.match(/\d+/) || [0])[0]);
  check(`${tag}: шаг 2 демо — «${title}» (похожая жалоба нашлась на чистой демо-базе)`, !!step4 && n >= 3, title);
  const demoTag = step4 ? await page.$$eval(".bc-similar .bk-tag--demo", (x) => x.map((e) => e.textContent.trim())) : [];
  check(`${tag}: похожая демо-жалоба помечена «Пример»`, demoTag.length === 1 && /Пример|Үлгі/.test(demoTag[0]), demoTag);
  await shot(page, `app-${tag}-4-similar`);
  if (!step4) { await ctx.close(); return; }
  await page.click(".bc-panel[data-step='4'] .bk-btn--primary");
  await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 10000 });
  const lead = (await page.textContent(".bc-lead")).trim();
  check(`${tag}: «Я тоже» — стало ${n + 1}`, lead.includes(String(n + 1)), lead);
  await shot(page, `app-${tag}-5-done`);
  const scroll = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
  check(`${tag}: нет прокрутки вбок`, scroll);
  check(`${tag}: нет ошибок на странице`, errors.length === 0, errors.slice(0, 3));
  await ctx.close();
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r09-app-"));
  const port = await freePort();
  let srv = null, browser = null;
  try {
    srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
    browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
    for (const [w, h, lang] of [[375, 812, "kk"], [375, 812, "ru"], [1366, 768, "ru"], [1366, 768, "kk"]]) {
      await variant(browser, `http://127.0.0.1:${port}/`, w, h, lang);
    }
  } catch (err) {
    console.error(err);
    check("приложение и браузер запустились", false, String(err && err.message));
  } finally {
    if (browser) await browser.close();
    if (srv) srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})();
