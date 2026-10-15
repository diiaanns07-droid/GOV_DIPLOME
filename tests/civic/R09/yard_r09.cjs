#!/usr/bin/env node
/*
 * R09 · раунд 15 · ссылка «Мой двор» на экране успеха (prompt R09 п. 6) в НАСТОЯЩЕМ приложении:
 *   node tests/civic/R09/yard_r09.cjs [--root <дерево сборки>] [--screenshots <папка>]
 * Житель: «Сообщить о проблеме» → остановка «Хан Шатыр» → текст → «Я тоже» → экран успеха.
 *   • модуль R16 в сборке (window.BirgeTogether, ветка R01 раунда 15) — под кнопками тихая ссылка «Мой двор»; нажатие
 *     закрывает мастер и открывает раздел «Мой двор» оболочки (жалоба не на двор — двор выбирает R16);
 *   • R16 нет (FINAL-4) — ссылки нет.
 * Сервер: python3 -B app.py (CIVIC_DEMO=1) на ВРЕМЕННОЙ SQLite (seed-demo). 375-ru и 1366-kk. Ничего не пишет в репозиторий.
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
const STOP = [71.406553, 51.131155];   // остановка «Хан Шатыр» (шаг 2 демо)
const TEXT = "Аялдамада жарық жоқ, вечером на остановке темно";
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ReadPixels/i;
const SAY = { ru: "Что ещё во дворе — «Мой двор»", kk: "Аулада тағы не бар — «Менің аулам»" };
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
const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });

async function tapStop(page, width) {
  const xy = await page.evaluate(async (p) => {
    const c = map.getCanvas().getBoundingClientRect();
    const panel = document.querySelector(".bc-panel"); const r = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    const mobile = innerWidth < 1024; const leftCard = r && !mobile && r.left + r.width / 2 < (c.left + c.right) / 2;
    const want = { x: ((leftCard ? r.right : c.left) + (r && !mobile && !leftCard ? r.left : c.right)) / 2, y: (c.top + (r && mobile ? r.top : c.bottom)) / 2 };
    map.jumpTo({ center: p, zoom: 17 }); const q = map.project(p);
    map.panBy([c.left + q.x - want.x, c.top + q.y - want.y], { duration: 0 });
    await new Promise((ok) => setTimeout(ok, 600)); const now = map.project(p); return { x: c.left + now.x, y: c.top + now.y };
  }, STOP);
  await sleep(500);
  if (width < 1024) await page.touchscreen.tap(xy.x, xy.y); else await page.mouse.click(xy.x, xy.y);
}

async function variant(browser, base, width, height, lang) {
  const tag = `${width}-${lang}`;
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l]) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) {} }, [lang]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text()); });
  try {
    await page.goto(base + "/?lang=" + lang);
    await shellReady(page);
    await sleep(800);
    const r16 = await page.evaluate(() => !!(window.BirgeTogether && (typeof window.BirgeTogether.open === "function"
      || typeof window.BirgeTogether.mount === "function")));
    await page.click(".bc-fab");
    await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 });
    await tapStop(page, width);
    await page.waitForSelector(".bc-option--first", { timeout: 10000 });
    await page.click(".bc-option--first");
    await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
    await page.fill("#bc-text", TEXT);
    await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 8000 }).catch(() => null);
    await page.click(".bc-send");
    await page.waitForSelector(".bc-panel[data-step='4'], .bc-panel[data-step='5']", { timeout: 15000 });
    if (await page.$(".bc-panel[data-step='4']:not([data-review])")) {
      await page.click(".bc-panel[data-step='4'] .bk-btn--primary");          // «Я тоже»
    } else if (await page.$(".bc-panel[data-review='1'] .bc-send")) {
      await page.click(".bc-panel[data-review='1'] .bc-send");                 // проверка перед отправкой → «Отправить»
    }
    await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 10000 });
    const link = await page.$(".bc-panel[data-step='5'] .bc-yard-link");
    if (!r16) {
      check(`${tag}: модуля R16 в сборке нет — на экране успеха ссылки «Мой двор» нет`, !link);
    } else {
      const label = link ? (await link.textContent()).replace(/\s+/g, " ").trim() : "";
      check(`${tag}: R16 в сборке — на экране успеха ссылка «${label}» со значком`, !!link && label === SAY[lang] &&
            !!(await link.$("svg")), label);
      if (SHOTS) { await sleep(400); await page.screenshot({ path: path.join(SHOTS, `yard-${tag}-success.png`) }); }
      if (link) {
        await link.click();
        await page.waitForFunction(() => document.body.dataset.birgeSection === "yard", null, { timeout: 8000 }).catch(() => null);
        const after = await page.evaluate(() => ({ section: document.body.dataset.birgeSection || null,
          wizard: !!document.querySelector(".bc-panel:not([hidden])[data-step]") }));
        check(`${tag}: нажатие — мастер закрыт, открыт раздел «Мой двор»`, after.section === "yard" && !after.wizard, after);
        if (SHOTS) { await sleep(600); await page.screenshot({ path: path.join(SHOTS, `yard-${tag}-opened.png`) }); }
      }
    }
    check(`${tag}: нет ошибок на странице`, errors.length === 0, errors.slice(0, 3));
  } catch (err) {
    check(`${tag}: сценарий прошёл без исключений`, false, String(err && err.message).slice(0, 300));
  } finally {
    await ctx.close();
  }
}

(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "r09-yard-"));
  const port = await freePort();
  let srv = null;
  const browser = await chromium.launch();
  try {
    srv = await startServer(port, path.join(dir, "civic.sqlite3"));
    for (const [w, h, lang] of [[375, 812, "ru"], [1366, 768, "kk"]]) await variant(browser, `http://127.0.0.1:${port}`, w, h, lang);
  } catch (err) {
    check("приложение и браузер запустились", false, String(err && err.message).slice(0, 300));
  } finally {
    await browser.close();
    if (srv) srv.kill();
    fs.rmSync(dir, { recursive: true, force: true });
  }
  const ok = results.filter((r) => r.ok).length;
  console.log(`\nИТОГ: ${ok}/${results.length} ${ok === results.length ? "PASS" : "FAIL"}`);
  process.exit(ok === results.length ? 0 : 1);
})();
