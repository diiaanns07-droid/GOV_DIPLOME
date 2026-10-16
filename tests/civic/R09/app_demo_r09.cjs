#!/usr/bin/env node
/*
 * R09 · шаги 1–2 сценария демо (DEMO_SCRIPT R01) в НАСТОЯЩЕМ приложении Birge (сборка R01), 375/1366 × ru/kk.
 *   node tests/civic/R09/app_demo_r09.cjs --root <checkout сборки R01 с путями R09> [--screenshots <папка>]
 * Сервер: python3 -B app.py с CIVIC_DEMO=1 на ВРЕМЕННОЙ SQLite (seed-demo R02 + демо-жалобы R09, если шлюз их сеет).
 * Путь жителя: «Сообщить о проблеме» → нажать прямо на значок/место остановки «Хан Шатыр» → «Это здесь?» →
 * текст демо вперемешку kk/ru → подсказка «Освещение» → «Об этом уже сообщили N человек» → «Я тоже» → N+1.
 * Каждый вариант — новое устройство (новый контекст браузера), поэтому N растёт от варианта к варианту.
 * Надписи на экране сверяются с тем, что говорит ведущий: DEMO_SCRIPT R01 (рус) и DEMO_PHRASES_KK R11 (қаз).
 * Последний вариант проходит и шаг 6 демо: акимат «Взять в работу» → «Отметить исправленным» на той же остановке →
 * у жителя в «Мои обращения» жалоба, к которой он присоединился «Я тоже», — «Исправлено» (статус дошёл до демо-жалобы R09).
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
// Надписи из реплик ведущего (R01 DEMO_SCRIPT, R11 DEMO_PHRASES_KK) — то, что житель должен увидеть на шагах 1–2 демо.
const SAY = {
  ru: { fab: "Сообщить о проблеме", title: "Где проблема?", question: "Это здесь?", suggested: "Похоже на:",
        category: "Освещение", metoo: "Я тоже", done: "Ваш голос учтён" },
  kk: { fab: "Мәселе туралы хабарлау", title: "Мәселе қай жерде?", question: "Осы жерде ме?", suggested: "Ұқсас санат:",
        category: "Жарықтандыру", metoo: "Мен де", done: "Сіздің дауысыңыз есепке алынды" },
};
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
  const staff = { user: "r09-operator", pass: "R09-app-" + Math.random().toString(36).slice(2) + "-Aa1!" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${staff.user} --password-stdin`,
           { cwd: ROOT, env, input: staff.pass + "\n", stdio: ["pipe", "ignore", "inherit"] });
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) { srv.staff = staff; return srv; } } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });

async function shot(page, name) {
  if (SHOTS) { await sleep(450); await page.screenshot({ path: path.join(SHOTS, name + ".png") }); }
}

async function tapStop(page, width) {
  // Ставим остановку в середину свободной части карты (над шторкой на телефоне, слева от панели на ноутбуке).
  const xy = await page.evaluate(async (p) => {
    const c = map.getCanvas().getBoundingClientRect();
    const panel = document.querySelector(".bc-panel"); const r = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    const mobile = innerWidth < 1024;
    // Ноутбук: панель R09 — карточка слева (эталон A) или справа (до 13 окт): середина видимой части карты.
    const leftCard = r && !mobile && r.left + r.width / 2 < (c.left + c.right) / 2;
    const want = { x: ((leftCard ? r.right : c.left) + (r && !mobile && !leftCard ? r.left : c.right)) / 2, y: (c.top + (r && mobile ? r.top : c.bottom)) / 2 };
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

// Шаг 6 демо (DEMO_SCRIPT 2:25–2:50) на той же остановке: акимат закрывает жалобы → житель видит «Исправлено».
async function step6(page, tag, width, lang, staff) {
  const logged = await page.evaluate(async ([u, p]) => (await fetch("/api/civic/v1/session/login", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) })).ok, [staff.user, staff.pass]);
  await page.reload();
  await shellReady(page);
  await page.evaluate(() => window.BirgeShell?.setMode?.("akimat"));
  await sleep(1200);
  await tapStop(page, width);
  const take = await page.waitForSelector(".r07-card [data-act='take']", { timeout: 8000 }).then(() => true, () => false);
  if (take) { await page.click(".r07-card [data-act='take']"); await sleep(1500); }
  const fix = await page.waitForSelector(".r07-card [data-act='fixed']", { timeout: 8000 }).then(() => true, () => false);
  let formUsed = false;
  if (fix) {
    await page.click(".r07-card [data-act='fixed']");
    // С патчем R07_fix_form.patch кнопка карточки открывает форму R09: одна строка «что сделали» (+ фото «после»).
    formUsed = await page.waitForSelector(".r07-fixform [name=what_done]", { timeout: 3000 }).then(() => true, () => false);
    if (formUsed) {
      check(`${tag}: шаг 6 — «Отметить исправленным» открывает форму R09 в карточке, кнопки карточки скрыты`,
            await page.evaluate(() => document.querySelector(".r07-actions").hidden &&
              document.querySelectorAll(".r07-card .bk-btn--primary").length === 1));
      await page.fill(".r07-fixform [name=what_done]", lang === "kk" ? "Шам ауыстырылды" : "Заменили лампу");
      await shot(page, `app-${tag}-6-fixform`);
      await page.click(".r07-fixform button[type=submit]");
    }
    await sleep(2500);
  }
  // До R07 9e337dc карточка пишет «Исправлено», с ним — «Служба сообщила — ждёт проверки» (B-055): принимаем оба.
  const word = lang === "kk" ? /Түзетілді|Қызмет хабарлады|түзетілгенін/ : /Исправлено|Служба сообщила/;
  const card = ((await page.textContent(".r07-card").catch(() => "")) || "").replace(/\s+/g, " ");
  check(`${tag}: шаг 6 демо — акимат: «Взять в работу» → «Отметить исправленным» → ${word}`,
        logged && take && fix && word.test(card), { logged, take, fix, card: card.slice(0, 160) });
  await shot(page, `app-${tag}-6-fixed`);
  // Волна 2: раздел акимата «Обращения» (#complaints, R01 INTEGRATION §11.2) — экран R09 BirgeComplaintList.
  if (await page.evaluate(() => !!window.BirgeComplaintList && !!window.BirgeShell?.setSection)) {
    await page.evaluate(() => window.BirgeShell.setSection("complaints"));
    const inbox = await page.waitForSelector(".bc-inbox__tab", { timeout: 8000 }).then(() => true, () => false);
    const tabs = inbox ? await page.$$eval(".bc-inbox__tab", (n) => n.map((b) => b.textContent.replace(/\s+/g, " ").trim())) : [];
    const rows = inbox ? await page.$$eval(".bc-inbox__row", (n) => n.length) : 0;
    // Эталон A, правило 5: фильтры «Все» + 5 вкладок, по умолчанию — все группы по статусу.
    check(`${tag}: раздел «Обращения» акимата — экран R09: фильтры и цели (${rows})`, inbox && tabs.length === 6 && /^(Все|Барлығы) \d+$/.test(tabs[0]) && rows > 0, tabs);
    await shot(page, `app-${tag}-6-inbox`);
    await page.evaluate(() => window.BirgeShell.setSection("map"));
    await sleep(600);
  }
  await page.evaluate(() => window.BirgeShell?.setMode?.("resident"));
  await sleep(800);
  await page.evaluate(() => window.CivicShell?.openMine?.());
  await page.waitForSelector(".bc-mine__card", { timeout: 8000 }).catch(() => null);
  const cards = await page.$$eval(".bc-mine__card", (n) => n.map((c) => ({ status: c.querySelector(".bk-status")?.dataset.status,
    text: c.textContent.replace(/\s+/g, " ").trim().slice(0, 140) })));
  const joined = cards.filter((c) => /Я тоже|Мен де/.test(c.text));
  // Волна 2, п. 1: «исправлено» службы — это «Служба сообщила об устранении»; жители проверяют сами.
  const ask = await page.$(".bc-wait .bc-verify__yes");
  check(`${tag}: шаг 6 демо — житель: «Служба сообщила об устранении» и «Проблема решена?»`,
        joined.length >= 1 && joined.every((c) => c.status === "reported_fixed") && !!ask, cards);
  await shot(page, `app-${tag}-6-mine`);
  if (!ask) return;
  if (formUsed) {
    const what = ((await page.textContent(".bc-wait")) || "").replace(/\s+/g, " ");
    check(`${tag}: шаг 6 — житель видит, что сделали («${lang === "kk" ? "Шам ауыстырылды" : "Заменили лампу"}»)`,
          what.includes(lang === "kk" ? "Шам ауыстырылды" : "Заменили лампу"), what.slice(0, 160));
  }
  await page.click(".bc-wait .bc-verify__yes");
  const verified = await page.waitForSelector(".bc-mine__card .bk-status[data-status='verified']", { timeout: 8000 })
    .then(() => true, () => false);
  const label = verified ? ((await page.textContent(".bc-mine__card .bk-status[data-status='verified']")) || "").trim() : "";
  check(`${tag}: шаг 7 (волна 2) — житель «Да, исправлено» → «${label}»`, verified &&
        label === (lang === "kk" ? "Тұрғындар тексерді" : "Проверено жителями"), label);
  await shot(page, `app-${tag}-7-verified`);
}

async function variant(browser, base, width, height, lang, staff, opts = {}) {
  const tag = `${width}-${lang}` + (opts.prelogin ? "-prelogin" : "") + (opts.different ? "-different" : "");
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l]) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) {} }, [lang]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text()); });
  await page.goto(base);
  await shellReady(page);
  if (opts.prelogin) {
    // LOCAL_FINAL №1 (Codex): сотрудник вошёл ЗАРАНЕЕ в том же браузере, потом режим «Житель» и путь жалобы.
    const logged = await page.evaluate(async ([u, p]) => (await fetch("/api/civic/v1/session/login", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) })).ok,
      [opts.prelogin.user, opts.prelogin.pass]);
    await page.reload();
    await shellReady(page);
    await page.evaluate(() => window.BirgeShell?.setMode?.("resident"));
    check(`${tag}: сотрудник вошёл до пути жителя`, logged);
  }
  await sleep(800);
  const seen = {};
  const text = async (sel) => ((await page.textContent(sel).catch(() => "")) || "").replace(/\s+/g, " ").trim();
  seen.fab = await text(".bc-fab");
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 });
  seen.title = await text(".bc-title");
  const top = await page.evaluate(() => { const h = document.querySelector(".bc-panel .bc-close").getBoundingClientRect();
    const el = document.elementFromPoint(h.left + h.width / 2, h.top + h.height / 2); return !!(el && el.closest(".bc-panel")); });
  check(`${tag}: шторка жалобы сверху — кнопка «Закрыть» не перекрыта панелями карты`, top);
  await shot(page, `app-${tag}-1-place`);
  const hit = await tapStop(page, width);
  const offered = await page.waitForSelector(".bc-option--first", { timeout: 10000 }).then(() => true, () => false);
  const first = offered ? (await page.textContent(".bc-option--first")).trim() : "";
  seen.question = offered ? await text(".bc-question") : "";
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
  // П3 «ИИ должен быть виден» (R11 IA §11.3): метка «ИИ» ui-kit — перед чипом подсказки категории; старый ui-kit — без метки.
  const ai = await page.evaluate(() => {
    const tagEl = document.querySelector(".bc-cat-row .bk-ai"), chipEl = document.querySelector(".bc-cat-row .bk-chip");
    return { kit: !!(window.BirgeUI && typeof window.BirgeUI.aiTag === "function"), tag: !!tagEl,
             before: !!(tagEl && chipEl && (tagEl.compareDocumentPosition(chipEl) & Node.DOCUMENT_POSITION_FOLLOWING)),
             hint: tagEl ? tagEl.getAttribute("title") : null };
  });
  check(`${tag}: ${ai.kit ? "метка «ИИ» перед подсказкой категории" : "ui-kit без aiTag — у подсказки категории метки нет"}`,
        ai.kit ? ai.tag && ai.before && !!ai.hint : !ai.tag, ai);
  seen.suggested = chip;
  seen.category = chip;
  await shot(page, `app-${tag}-3-text`);
  await page.click(".bc-send");
  // Волна 2: шаг 4 — либо «Я тоже» (похожая жалоба), либо проверка перед отправкой (data-review=1).
  await page.waitForSelector(".bc-panel[data-step='4'], .bc-panel[data-step='5']", { timeout: 15000 });
  const step4 = await page.$(".bc-panel[data-step='4']:not([data-review])");
  const title = (await page.textContent(".bc-title")).trim();
  const n = Number((title.match(/\d+/) || [0])[0]);
  check(`${tag}: шаг 2 демо — «${title}» (похожая жалоба нашлась на чистой демо-базе)`, !!step4 && n >= 3, title);
  const demoTag = step4 ? await page.$$eval(".bc-similar .bk-tag--demo", (x) => x.map((e) => e.textContent.trim())) : [];
  check(`${tag}: похожая демо-жалоба помечена «Пример»`, demoTag.length === 1 && /Пример|Үлгі/.test(demoTag[0]), demoTag);
  await shot(page, `app-${tag}-4-similar`);
  if (!step4) { await ctx.close(); return; }
  if (opts.different) {
    // LOCAL_FINAL №2: «У меня другое» -> успех -> сразу Escape; отложенная подсказка не должна читать null.
    await page.click(".bc-different");
    await page.waitForSelector(".bc-panel[data-review='1'] .bc-send:not([disabled])", { timeout: 10000 });
    await page.click(".bc-panel[data-review='1'] .bc-send");   // экран проверки -> «Отправить»
    await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 10000 });
    await page.keyboard.press("Escape");
    await sleep(2500);
    const late = errors.filter((e) => /null|undefined|TypeError/.test(e));
    check(`${tag}: «У меня другое» и сразу закрыть — без ошибок JavaScript`, late.length === 0, late.slice(0, 3));
    await ctx.close();
    return;
  }
  seen.metoo = await text(".bc-panel[data-step='4'] .bk-btn--primary");
  await page.click(".bc-panel[data-step='4'] .bk-btn--primary");
  await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 10000 });
  seen.done = await text(".bc-title");
  const lead = (await page.textContent(".bc-lead")).trim();
  check(`${tag}: «Я тоже» — стало ${n + 1}`, lead.includes(String(n + 1)), lead);
  await shot(page, `app-${tag}-5-done`);
  const say = SAY[lang];
  const off = Object.keys(say).filter((k) => !(seen[k] || "").includes(say[k])).map((k) => [k, say[k], seen[k]]);
  check(`${tag}: надписи совпадают с репликами ведущего (${Object.keys(say).length})`, off.length === 0, off);
  if (staff) await step6(page, tag, width, lang, staff);
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
    const runs = [[375, 812, "kk"], [375, 812, "ru"], [1366, 768, "ru"], [1366, 768, "kk"]];
    // R09_ONLY_LOCAL=1 — только проверки LOCAL_FINAL №1–2 (быстро; основной сценарий пропускается).
    for (const [i, [w, h, lang]] of (process.env.R09_ONLY_LOCAL ? [] : runs).entries()) {
      await variant(browser, `http://127.0.0.1:${port}/`, w, h, lang, i === runs.length - 1 ? srv.staff : null);
    }
    // LOCAL_FINAL №1–2 — на ОТДЕЛЬНОЙ свежей демо-базе: в основном прогоне шаг 6 уже закрыл жалобы на остановке,
    // и похожих открытых жалоб там не осталось бы.
    srv.kill();
    const port2 = await freePort();
    srv = await startServer(port2, path.join(tmp, "civic-local.sqlite3"));
    await variant(browser, `http://127.0.0.1:${port2}/`, 375, 812, "ru", null, { prelogin: srv.staff });
    await variant(browser, `http://127.0.0.1:${port2}/`, 1366, 768, "kk", null, { prelogin: srv.staff });
    await variant(browser, `http://127.0.0.1:${port2}/`, 375, 812, "ru", null, { different: true });
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
