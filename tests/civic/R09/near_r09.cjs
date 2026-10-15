#!/usr/bin/env node
/*
 * R09 · эталон A, телефон: шторка «Рядом с вами» (BirgeComplaint.mountNear; решение R11 INTEGRATION §21.2) в НАСТОЯЩЕМ
 * приложении (CIVIC_DEMO=1, временная SQLite). Оболочка R01 шторку ещё не ставит — тест сам кладёт её внизу экрана,
 * как .p-sheet эталона (375×812, высота 360), карта — та же, данные — GET /api/civic/v2/heat (как у карты жалоб R07).
 *   node tests/civic/R09/near_r09.cjs --root <сборка R01 с путями R09> [--screenshots <папка>]
 * Проверки: заголовок и «ҚАЗ · РУС», 3 ближайших к центру карты места (порядок по расстоянию), плашка числа цвета
 * уровня / «✓» у исправленного службой, нажатие на строку → onOpen(цель), «Все горячие места» → onAll, сдвиг карты —
 * пересчёт без запроса, смена языка, зоны нажатия ≥ 44, без ошибок консоли.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const os = require("os");
const net = require("net");
const { spawn, execSync } = require("child_process");
function loadPlaywright() {
  try { return require("playwright"); } catch (e) { return require(path.join(execSync("npm root -g").toString().trim(), "playwright")); }
}
const { chromium } = loadPlaywright();
const args = process.argv.slice(2);
const ROOT = path.resolve(args.includes("--root") ? args[args.indexOf("--root") + 1] : path.resolve(__dirname, "../../.."));
const SHOTS = args.includes("--screenshots") ? path.resolve(args[args.indexOf("--screenshots") + 1]) : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
const STOP = [71.406553, 51.131155];   // остановка «Хан Шатыр» (Нура)
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
const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });

async function variant(browser, base, lang) {
  const tag = `375-${lang}`;
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 1, hasTouch: true });
  await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", "resident"); } catch (e) {} }, lang);
  const page = await ctx.newPage();
  page.problems = [];
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) page.problems.push(m.text()); });
  page.on("pageerror", (e) => page.problems.push(String(e)));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  try {
    await page.goto(base + "?lang=" + lang, { waitUntil: "domcontentloaded" });
    await shellReady(page);
    // FINAL-4: шторку ставит сама оболочка R01 (#birge-near, birge-ref.js syncNear → mountNear). Проверяем её — настоящую;
    // если оболочка старая и шторки нет — кладём так, как она её ставит: внизу, во всю ширину (эталон .p-sheet).
    const own = await page.waitForSelector("#birge-near .bc-near .bc-near__row", { timeout: 8000 }).then(() => true, () => false);
    await page.evaluate(([stop, own]) => {
      window.nearLog = [];
      map.jumpTo({ center: stop, zoom: 15 });
      if (own) {
        // Нажатия оболочки (focusTarget R07 / список «Горячие места») — записываем, не меняя её поведения.
        const heat = window.CivicShell && window.CivicShell.heat;
        if (heat && heat.focusTarget) { const f = heat.focusTarget.bind(heat); heat.focusTarget = (k, i) => { window.nearLog.push(["open", k, i]); return f(k, i); }; }
        document.addEventListener("click", (e) => { if (e.target.closest && e.target.closest(".bc-near__all")) window.nearLog.push(["all"]); }, true);
        return;
      }
      document.querySelectorAll(".civic-panel").forEach((p) => { p.style.visibility = "hidden"; });
      const host = document.createElement("div");
      host.id = "near-host";
      host.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:20";
      document.body.appendChild(host);
      window.nearCtl = window.BirgeComplaint.mountNear(host, { map,
        onOpen: (target) => window.nearLog.push(["open", target.kind, target.id]), onAll: () => window.nearLog.push(["all"]) });
    }, [STOP, own]);
    check(`${tag}: шторку «Рядом с вами» ставит оболочка (одна шторка на экране)`, own &&
          await page.evaluate(() => document.querySelectorAll(".bc-near").length === 1));
    await page.waitForSelector(".bc-near .bc-near__row", { timeout: 10000 });
    await sleep(500);
    const want = await page.evaluate(async (stop) => {
      const res = await (await fetch("/api/civic/v2/heat?days=30&zoom=15")).json();
      const items = (res.data || res).items.filter((it) => it.target && it.target.kind !== "district" && it.count > 0 && it.anchor &&
        (it.state === "active" || (it.state === "fixed" && it.fixed_kind === "reported")));
      const c = map.getCenter(); const far = (a) => ((a[0] - c.lng) * Math.cos(c.lat * Math.PI / 180)) ** 2 + (a[1] - c.lat) ** 2;
      items.sort((a, b) => far(a.anchor) - far(b.anchor));
      return items.slice(0, 3).map((it) => it.target.kind + ":" + it.target.id);
    }, STOP);
    const seen = await page.evaluate(() => ({
      title: document.querySelector(".bc-near .bk-phsheet__title").textContent.trim(),
      lang: (document.querySelector(".bc-near__lang") || {}).textContent || "",
      keys: [...document.querySelectorAll(".bc-near__row")].map((b) => b.dataset.key),
      rows: [...document.querySelectorAll(".bc-near__row")].map((b) => ({ cnt: b.querySelector(".bk-hot__cnt").textContent.trim(),
        icon: !!b.querySelector(".bk-hot__cnt svg"),
        level: b.querySelector(".bk-hot__cnt").dataset.level, name: b.querySelector(".bk-hot__name").firstChild.textContent,
        sub: b.querySelector(".bk-hot__name small").textContent, h: Math.round(b.getBoundingClientRect().height) })),
      all: (document.querySelector(".bc-near__all") || {}).textContent || "",
      sheet: (() => { const r = document.querySelector(".bc-near").getBoundingClientRect(); return { top: Math.round(r.top), h: Math.round(r.height) }; })(),
      // Геометрия относительно шторки — как .p-sheet эталона A (375 × 812): заголовок 17,+26 · 23 px, первая строка .hot
      // 17,+55 · 341 × 54 (reference_check R10: p-sheet-title, p-hot).
      geo: (() => { const sh = document.querySelector(".bc-near").getBoundingClientRect();
        const rel = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left - sh.left), y: Math.round(r.top - sh.top), w: Math.round(r.width), h: Math.round(r.height) }; };
        const row = document.querySelector(".bc-near__row");
        return { title: rel(document.querySelector(".bc-near .bk-phsheet__title")), row: row ? rel(row) : null }; })(),
    }));
    console.log(`  ${tag}: геометрия шторки (эталон: заголовок 17,26 h23 · строка 17,55 341×54) — ${JSON.stringify(seen.geo)}`);
    check(`${tag}: заголовок «${seen.title}» и «ҚАЗ · РУС» в шапке шторки`, (lang === "kk" ? /маңайыңызда/ : /Рядом с вами/).test(seen.title) &&
          /ҚАЗ/.test(seen.lang) && /РУС/.test(seen.lang), seen.lang);
    check(`${tag}: 3 ближайших к центру карты места, по расстоянию`, seen.keys.length === Math.min(3, want.length) && seen.keys.join() === want.join(),
          { seen: seen.keys, want });
    // П1: у исправленного службой — значок «галочка» набора R11 в плашке, не глиф «✓».
    check(`${tag}: строка — плашка числа цвета уровня (или значок «галочка») · название · «тема · статус», 44+ px`, seen.rows.length > 0 &&
          seen.rows.every((r) => (/^\d+$/.test(r.cnt) && /^[1-4]$/.test(r.level) || r.cnt === "" && r.icon && r.level === "fixed") && r.name && r.sub && r.h >= 44),
          seen.rows);
    check(`${tag}: шторка внизу, высота эталона (360; по-казахски — по содержимому), «${seen.all}»`, seen.sheet.h >= 340 && seen.sheet.h <= (lang === "kk" ? 480 : 400) &&
          seen.sheet.top + seen.sheet.h <= 813 && (lang === "kk" ? /Барлық/ : /Все горячие места/).test(seen.all), seen.sheet);
    // «Сообщить о проблеме» (эталон: поверх низа шторки) не закрывает строки и «Все горячие места».
    const covered = await page.evaluate(() => [...document.querySelectorAll(".bc-near__row, .bc-near__all")].filter((el) => {
      const r = el.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return !hit || !el.contains(hit); }).map((el) => el.textContent.trim().slice(0, 30)));
    check(`${tag}: «Сообщить о проблеме» не закрывает строки и «Все горячие места»`, covered.length === 0, covered);
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `near-${tag}.png`) });
    await page.click(".bc-near__row");
    await sleep(400);
    // Оболочка по нажатию открыла карточку места R07 — шторка спряталась; закрыть карточку, вернуться к шторке.
    await page.evaluate(() => { const h = window.CivicShell && window.CivicShell.heat; if (h && h.close) h.close(); });
    await page.waitForSelector(".bc-near .bc-near__all", { state: "visible", timeout: 5000 }).catch(() => null);
    await page.click(".bc-near__all").catch(() => null);
    const log = await page.evaluate(() => window.nearLog);
    check(`${tag}: нажатие на строку — onOpen(цель), «Все горячие места» — onAll`, log.length === 2 && log[0][0] === "open" &&
          log[0][1] + ":" + log[0][2] === seen.keys[0] && log[1][0] === "all", log);
    // «Все горячие места» открыли список R07 — закрываем, шторка снова на экране.
    await page.keyboard.press("Escape");   // оболочка: Esc закрывает список «Горячие места» (closeLeft) — снова шторка
    await page.waitForSelector(".bc-near .bc-near__lang button", { state: "visible", timeout: 5000 }).catch(() => null);
    // Карту увели на другой конец города — ближайшие пересчитываются на месте (без нового запроса).
    let calls = 0;
    page.on("request", (r) => { if (/\/api\/civic\/v2\/heat\?days=30&zoom=15/.test(r.url())) calls += 1; });
    await page.evaluate(() => map.jumpTo({ center: [71.47, 51.09], zoom: 15 }));
    await sleep(600);
    const moved = await page.evaluate(() => [...document.querySelectorAll(".bc-near__row")].map((b) => b.dataset.key));
    check(`${tag}: сдвиг карты — другие ближайшие, без запроса`, moved.length > 0 && moved.join() !== seen.keys.join() && calls === 0, { moved, calls });
    // Язык из шапки шторки.
    const other = lang === "kk" ? "ru" : "kk";
    const cover = await page.evaluate((v) => { const b = document.querySelector(`.bc-near__lang button[value="${v}"]`);
      if (!b) return "нет кнопки"; const r = b.getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return el === b || b.contains(el) ? "ok" : (el ? (el.id || el.className || el.tagName).toString().slice(0, 80) : "пусто") + " " + JSON.stringify([r.left, r.top, r.width, r.height]); }, other);
    await page.click(`.bc-near__lang button[value="${other}"]`, { timeout: 5000 }).catch((e) => console.log("  клик языка: " + cover + " · " + String(e.message).slice(0, 120)));
    // Обратно на язык варианта — следующая проверка (мастер) идёт на нём.
    await page.waitForFunction((want) => (want === "kk" ? /маңайыңызда/ : /Рядом с вами/).test(document.querySelector(".bc-near .bk-phsheet__title").textContent),
      other, { timeout: 5000 }).catch(() => null);
    const t2 = await page.textContent(".bc-near .bk-phsheet__title");
    check(`${tag}: «ҚАЗ · РУС» в шторке меняет язык — «${t2.trim()}»`, (other === "kk" ? /маңайыңызда/ : /Рядом с вами/).test(t2), t2);
    // VISUAL_BRIEF §3: открыли мастер «Сообщить о проблеме» — шторка «Рядом» скрыта (одна шторка), закрыли — снова видна.
    await page.evaluate(() => { const h = window.CivicShell && window.CivicShell.heat; if (h && h.close) h.close(); });
    await sleep(300);
    const fab = await page.$(".bc-fab:not([hidden])");
    if (fab) {
      await fab.click();
      await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 }).catch(() => null);
      await sleep(300);
      const during = await page.evaluate(() => { const n = document.querySelector(".bc-near");
        const r = n && n.getBoundingClientRect(); const shown = !!n && getComputedStyle(n).visibility !== "hidden" && r.height > 0;
        const sheets = [...document.querySelectorAll(".bc-panel, .bc-near")].filter((x) => getComputedStyle(x).visibility !== "hidden" &&
          !x.hidden && x.getBoundingClientRect().height > 0).length;
        return { shown, sheets }; });
      if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `near-${tag}-wizard.png`) });
      await page.keyboard.press("Escape");
      await page.waitForFunction(() => !document.documentElement.classList.contains("bc-open"), null, { timeout: 5000 }).catch(() => null);
      await sleep(300);
      const after = await page.evaluate(() => { const n = document.querySelector(".bc-near"); return !!n && getComputedStyle(n).visibility !== "hidden"; });
      check(`${tag}: мастер открыт — шторка «Рядом» скрыта (на экране одна шторка), закрыли — снова видна`,
            !during.shown && during.sheets === 1 && after, { during, after });
    } else {
      check(`${tag}: кнопка «Сообщить о проблеме» на экране`, false);
    }
    check(`${tag}: нет ошибок консоли`, page.problems.length === 0, page.problems);
  } finally { await ctx.close(); }
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r09-near-"));
  const port = await freePort();
  let srv = null, browser = null;
  try {
    srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
    browser = await chromium.launch();
    for (const lang of ["ru", "kk"]) await variant(browser, `http://127.0.0.1:${port}/`, lang);
  } catch (e) { check("стенд запустился", false, String(e && e.stack || e)); }
  finally { if (browser) await browser.close(); if (srv) srv.kill(); fs.rmSync(tmp, { recursive: true, force: true }); }
  const ok = results.filter((r) => r.ok).length;
  console.log(`\nИТОГ: ${ok}/${results.length} ${ok === results.length ? "PASS" : "FAIL"}`);
  process.exit(ok === results.length ? 0 : 1);
})();
