#!/usr/bin/env node
/*
 * R09 · раунд 15 · голосовой ввод в мастере (prompt R09 п. 7, по желанию) в НАСТОЯЩЕМ приложении:
 *   node tests/civic/R09/voice_r09.cjs [--root <сборка>] [--screenshots <папка>]
 * Распознавание речи браузера подменяется заглушкой (в облаке нет микрофона): проверяем, что кнопка есть только при
 * поддержке, язык ru-RU / kk-KZ по языку интерфейса, распознанное дописывается в поле и попадает в подсказку категории,
 * «Остановить», отказ в микрофоне — понятный текст, закрытие мастера останавливает распознавание.
 * Без заглушки (Chromium без Web Speech) — кнопки нет. Настоящий микрофон — NOT_RUN (LOCAL).
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
const STOP = [71.406553, 51.131155];
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ReadPixels/i;
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined ? " — " + JSON.stringify(detail).slice(0, 300) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" init`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  execSync(`python3 -B -m ui.civic_store --db "${db}" seed-demo --package data/civic/astana/demo_synthetic.json`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });

// Заглушка распознавания: запоминает язык, по start() «слышит» фразу и шлёт результат; mode=deny — отказ в микрофоне.
const FAKE = ([mode, phrase]) => {
  window.__voice = { langs: [], started: 0, stopped: 0 };
  class FakeRecognition {
    start() {
      window.__voice.started += 1; window.__voice.langs.push(this.lang);
      setTimeout(() => {
        if (mode === "deny") { this.onerror && this.onerror({ error: "not-allowed" }); this.onend && this.onend(); return; }
        const r = [[{ transcript: phrase }]]; r[0].isFinal = true;
        this.onresult && this.onresult({ results: r, resultIndex: 0 });
        if (mode === "end") this.onend && this.onend();
      }, 120);
    }
    stop() { window.__voice.stopped += 1; setTimeout(() => this.onend && this.onend(), 20); }
  }
  // Chromium 141+ отдаёт и SpeechRecognition без префикса — экран берёт его первым, подменяем оба имени.
  window.SpeechRecognition = FakeRecognition;
  window.webkitSpeechRecognition = FakeRecognition;
};

async function toText(page, width) {
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 });
  const xy = await page.evaluate(async (p) => {
    const c = map.getCanvas().getBoundingClientRect();
    const panel = document.querySelector(".bc-panel"); const r = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    const mobile = innerWidth < 1024; const leftCard = r && !mobile && r.left + r.width / 2 < (c.left + c.right) / 2;
    const want = { x: ((leftCard ? r.right : c.left) + (r && !mobile && !leftCard ? r.left : c.right)) / 2, y: (c.top + (r && mobile ? r.top : c.bottom)) / 2 };
    map.jumpTo({ center: p, zoom: 17 }); const q = map.project(p);
    map.panBy([c.left + q.x - want.x, c.top + q.y - want.y], { duration: 0 });
    await new Promise((ok) => setTimeout(ok, 600)); const now = map.project(p); return { x: c.left + now.x, y: c.top + now.y };
  }, STOP);
  await sleep(400);
  if (width < 1024) await page.touchscreen.tap(xy.x, xy.y); else await page.mouse.click(xy.x, xy.y);
  await page.waitForSelector(".bc-option--first", { timeout: 10000 });
  await page.click(".bc-option--first");
  await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
}

async function variant(browser, base, width, height, lang, mode) {
  const tag = `${width}-${lang}-${mode}`;
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l]) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) {} }, [lang]);
  const phrase = lang === "kk" ? "аялдамада жарық жоқ" : "на остановке не горит фонарь";
  if (mode !== "none") await ctx.addInitScript(FAKE, [mode, phrase]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text()); });
  try {
    await page.goto(base + "/?lang=" + lang);
    await shellReady(page);
    await toText(page, width);
    const btn = await page.$(".bc-voice");
    if (mode === "none") {
      const native = await page.evaluate(() => typeof (window.SpeechRecognition || window.webkitSpeechRecognition) === "function");
      check(`${tag}: без распознавания в браузере кнопки нет`, native ? !!btn : !btn, { native, button: !!btn });
      return;
    }
    const label = btn ? (await btn.textContent()).trim() : "";
    check(`${tag}: кнопка «${label}» под полем текста`, !!btn && label === (lang === "kk" ? "Дауыспен айту" : "Сказать голосом"));
    await page.fill("#bc-text", lang === "kk" ? "Кешке" : "Вечером");
    await page.click(".bc-voice");
    if (mode === "deny") {
      await page.waitForFunction(() => /микрофон|Микрофон/.test(document.querySelector(".bc-voice__status").textContent), null, { timeout: 5000 }).catch(() => null);
      const st = (await page.textContent(".bc-voice__status")).trim();
      check(`${tag}: отказ в микрофоне — понятный текст, текст в поле не тронут`, /микрофон|Микрофон/.test(st) &&
            (await page.inputValue("#bc-text")) === (lang === "kk" ? "Кешке" : "Вечером"), st);
      return;
    }
    await page.waitForFunction((p) => document.querySelector("#bc-text").value.includes(p), phrase, { timeout: 5000 }).catch(() => null);
    const value = await page.inputValue("#bc-text");
    const voice = await page.evaluate(() => window.__voice);
    check(`${tag}: язык распознавания ${lang === "kk" ? "kk-KZ" : "ru-RU"}, фраза дописана к тексту`,
          voice.langs[0] === (lang === "kk" ? "kk-KZ" : "ru-RU") && value === (lang === "kk" ? "Кешке " : "Вечером ") + phrase, { value, voice });
    const pressed = await page.$eval(".bc-voice", (b) => b.getAttribute("aria-pressed"));
    const stopLabel = (await page.textContent(".bc-voice")).trim();
    check(`${tag}: пока слушает — «${stopLabel}» (aria-pressed)`, pressed === "true" && stopLabel === (lang === "kk" ? "Тоқтату" : "Остановить"));
    await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 8000 }).catch(() => null);
    const cat = ((await page.textContent(".bc-cat-row").catch(() => "")) || "").replace(/\s+/g, " ");
    check(`${tag}: распознанный текст — как набранный: подсказка категории «${cat.slice(0, 40)}»`, /Освещение|Жарықтандыру/.test(cat));
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `voice-${tag}.png`) });
    await page.keyboard.press("Escape");
    await sleep(300);
    const after = await page.evaluate(() => window.__voice.stopped);
    check(`${tag}: закрыли мастер — распознавание остановлено`, after >= 1, after);
    check(`${tag}: нет ошибок на странице`, errors.length === 0, errors.slice(0, 3));
  } catch (err) {
    check(`${tag}: сценарий прошёл без исключений`, false, String(err && err.message).slice(0, 200));
  } finally { await ctx.close(); }
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r09-voice-"));
  const port = await freePort();
  let srv = null, browser = null;
  try {
    srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
    browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
    for (const [w, h, lang, mode] of [[375, 812, "kk", "listen"], [1366, 768, "ru", "listen"], [375, 812, "ru", "deny"], [1366, 768, "ru", "none"]]) {
      await variant(browser, `http://127.0.0.1:${port}`, w, h, lang, mode);
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
