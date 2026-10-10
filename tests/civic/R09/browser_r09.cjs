#!/usr/bin/env node
/*
 * R09 · браузерная проверка пути жителя v2 на стенде tests/civic/R09/stand/serve_r09.py.
 *   node tests/civic/R09/browser_r09.cjs [--screenshots <папка>]
 * Поднимает два стенда (с FIXTURE-ML и без ML), проходит путь в Chromium и печатает PASS/FAIL по пунктам.
 * Код выхода 1, если хоть один пункт FAIL.
 */
"use strict";
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

function loadPlaywright() {
  try { return require("playwright"); } catch (e) {
    const globalRoot = require("child_process").execSync("npm root -g").toString().trim();
    return require(path.join(globalRoot, "playwright"));
  }
}
const { chromium } = loadPlaywright();
const ROOT = path.resolve(__dirname, "../../..");
const args = process.argv.slice(2);
const shotDir = args.includes("--screenshots") ? path.resolve(args[args.indexOf("--screenshots") + 1]) : null;
if (shotDir) fs.mkdirSync(shotDir, { recursive: true });

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: detail || "" });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
}

function startStand(port, extra) {
  return new Promise((resolve, reject) => {
    const proc = spawn("python3", [path.join(__dirname, "stand", "serve_r09.py"), "--port", String(port), "--seed", ...extra],
      { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
    let out = "";
    const timer = setTimeout(() => reject(new Error("stand did not start: " + out)), 30000);
    proc.stdout.on("data", (d) => { out += d; if (out.includes("R09 stand:")) { clearTimeout(timer); resolve(proc); } });
    proc.stderr.on("data", (d) => { out += d; });
    proc.on("exit", (code) => { clearTimeout(timer); reject(new Error("stand exited " + code + ": " + out)); });
  });
}

async function newPage(browser, base, width, height, lang) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1,
                                             hasTouch: width < 1024, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  const page = await context.newPage();
  page.problems = [];
  page.on("console", (msg) => {
    if (/Failed to load resource/.test(msg.text())) return;  // сетевые ответы проверяются ниже по URL
    if (msg.type() === "error" || (msg.type() === "warning" && msg.text().includes("[i18n]"))) page.problems.push(msg.text());
  });
  page.on("response", (res) => {
    // ui-kit и i18n R11 необязательны, пока их нет в дереве (запасные стили и тексты R09).
    if (res.status() >= 400 && !/\/civic\/(ui-kit|i18n)\//.test(res.url())) page.problems.push(res.status() + " " + res.url());
  });
  page.on("pageerror", (err) => page.problems.push(String(err)));
  await page.goto(base + "/stand/");
  await page.evaluate((l) => BirgeComplaint.setLang(l), lang);
  await page.waitForFunction(() => document.documentElement.getAttribute("data-map-ready") === "1", null, { timeout: 15000 });
  return page;
}

async function clickMapAt(page, point) {
  // Точку ставим в середину видимой части карты (на телефоне снизу шторка, на ноутбуке справа панель):
  // jumpTo + panBy без анимации, затем проверяем, что точка действительно в видимой области.
  const xy = await page.evaluate(async (p) => {
    const map = window.standMap;
    const canvas = map.getCanvas().getBoundingClientRect();
    const panel = document.querySelector(".bc-panel");
    const r = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    const mobile = window.innerWidth < 1024;
    const right = r && !mobile ? r.left : canvas.right;
    const bottom = r && mobile ? r.top : canvas.bottom;
    const want = { x: (canvas.left + right) / 2, y: (canvas.top + bottom) / 2 };
    for (let i = 0; i < 3; i++) {
      map.jumpTo({ center: p, zoom: 17 });
      const q = map.project(p);
      map.panBy([canvas.left + q.x - want.x, canvas.top + q.y - want.y], { duration: 0 });
      await new Promise((ok) => setTimeout(ok, 150));
      const now = map.project(p);
      const got = { x: canvas.left + now.x, y: canvas.top + now.y };
      if (Math.abs(got.x - want.x) < 4 && Math.abs(got.y - want.y) < 4) return got;
    }
    const q = map.project(p);
    return { x: canvas.left + q.x, y: canvas.top + q.y, unstable: true };
  }, point);
  const tap = async () => {
    if (page.viewportSize().width < 1024) await page.touchscreen.tap(xy.x, xy.y); else await page.mouse.click(xy.x, xy.y);
  };
  await tap();
  // Если карта не приняла нажатие (точка не появилась), повторяем один раз и считаем это.
  const picked = await page.waitForFunction(() => window.standAdapter.current().features.length > 0, null, { timeout: 2000 })
    .then(() => true, () => false);
  if (!picked) {
    const clicks = await page.evaluate(() => window.standClicks);
    page.retries = (page.retries || 0) + 1;
    page.retryNotes = (page.retryNotes || []).concat(`карта получила кликов: ${clicks}, точка ${JSON.stringify(xy)}`);
    await tap();
  }
}

async function noHorizontalScroll(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1 &&
    [...document.querySelectorAll(".bc-panel *")].every((n) => { const r = n.getBoundingClientRect();
      return r.width === 0 || (r.right <= window.innerWidth + 1 && r.left >= -1); }));
}

async function visibleKeys(page) {
  // Непереведённые ключи и технические слова на экране.
  return page.evaluate(() => {
    const text = document.body.innerText;
    const keys = text.match(/\b(complaint|mine|status|common|cat)\.[a-z0-9_.]+/g) || [];
    const words = text.match(/\b(undefined|null|NaN|target|payload|geometry)\b|ребро|граф/gi) || [];
    return keys.concat(words);
  });
}

async function shot(page, name) {
  if (shotDir) await page.screenshot({ path: path.join(shotDir, name + ".png") });
}

async function residentPath(browser, base, hot, lang, width, height, tag) {
  const page = await newPage(browser, base, width, height, lang);
  const t0 = Date.now();
  let taps = 0;
  await page.click(".bc-fab"); taps++;
  await page.waitForSelector(".bc-panel[data-step='2']");
  await shot(page, `${tag}-1-place`);
  await clickMapAt(page, hot.point); taps++;
  await page.waitForSelector(".bc-option--first", { timeout: 8000 }).catch(async (err) => {
    console.log("DIAG notes=", JSON.stringify(page.retryNotes), "clicks=", await page.evaluate(() => window.standClicks), "step=", await page.$eval(".bc-panel", (e) => e.dataset.step),
                "pick=", JSON.stringify(await page.evaluate(() => window.standAdapter.current())),
                "panel=", (await page.textContent(".bc-panel")).slice(0, 200));
    if (shotDir) await page.screenshot({ path: path.join(shotDir, tag + "-DIAG.png") });
    throw err;
  });
  const question = await page.textContent(".bc-option--first");
  check(`${tag}: шаг 2 предлагает реальный участок улицы`, /Туран/.test(question), question);
  await shot(page, `${tag}-2-candidates`);
  await page.click(".bc-option--first"); taps++;
  await page.waitForSelector(".bc-panel[data-step='3']");
  const hl = await page.evaluate(() => window.standAdapter.current().features.map((f) => f.geometry.type));
  check(`${tag}: выбранный участок подсвечен линией по форме улицы`, hl.includes("LineString"), JSON.stringify(hl));
  const text = lang === "kk" ? "Тротуарда қар тазаланбаған, өте тайғақ" : "Снег на тротуаре не убран, очень скользко";
  await page.fill("#bc-text", text);
  await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 6000 });
  const chip = await page.textContent(".bc-cat-row");
  check(`${tag}: подсказка категории чипом`, lang === "kk" ? /Қар және көктайғақ/.test(chip) : /Снег и гололёд/.test(chip), chip.trim());
  await shot(page, `${tag}-3-text`);
  await page.click(".bc-send"); taps++;
  await page.waitForSelector(".bc-panel[data-step='4']", { timeout: 8000 });
  const title4 = await page.textContent(".bc-title");
  const before = Number((title4.match(/\d+/) || [0])[0]);
  check(`${tag}: шаг 4 «уже сообщили N» (N ≥ 7 по демо-цели)`, before >= 7, title4);
  const leak = await page.evaluate(() => document.querySelector(".bc-panel").innerText.includes("очень скользко") &&
    !document.querySelector("#bc-text"));
  check(`${tag}: чужой текст жалобы не показан`, !leak);
  await shot(page, `${tag}-4-similar`);
  await page.click(".bc-panel[data-step='4'] .bk-btn--primary"); taps++;
  await page.waitForSelector(".bc-panel[data-step='5']");
  const done = await page.textContent(".bc-panel");
  check(`${tag}: «Я тоже» засчитан — стало ${before + 1}`, done.includes(String(before + 1)), (await page.textContent(".bc-lead")) || "");
  const elapsed = (Date.now() - t0) / 1000;
  check(`${tag}: путь за ${taps} нажатий + текст, ${elapsed.toFixed(1)} с автоматом`, taps <= 6 && elapsed < 30);
  const events = await page.evaluate(() => window.standEvents);
  check(`${tag}: событие birge:complaint для тепловой карты`, events.length === 1 && events[0].type === "metoo" &&
    events[0].target && events[0].target.kind === "segment" && events[0].reporters === before + 1, JSON.stringify(events));
  await shot(page, `${tag}-5-done`);
  check(`${tag}: нет горизонтальной прокрутки`, await noHorizontalScroll(page));
  const keys = await visibleKeys(page);
  check(`${tag}: нет ключей и технических слов`, keys.length === 0, keys.join(", "));
  check(`${tag}: нет ошибок консоли и [i18n]`, page.problems.length === 0, page.problems.join(" | "));
  check(`${tag}: карта приняла нажатие с первого раза`, !page.retries, (page.retryNotes || []).join("; "));
  await page.context().close();
}

async function newComplaintAndMine(browser, base, lang, width, height, tag, point) {
  const page = await newPage(browser, base, width, height, lang);
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']");
  // Место без кандидатов (поле без улиц) -> «примерное место», цель всё равно есть.
  await clickMapAt(page, point);
  await page.waitForSelector(".bc-panel[data-step='3'], .bc-option", { timeout: 8000 });
  if (await page.$(".bc-option")) await page.click(".bc-option.bk-btn--ghost");  // «Другое место»
  await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
  const place = await page.textContent(".bc-place");
  check(`${tag}: нет объекта рядом — «примерное место»`, lang === "kk" ? /Шамамен/.test(place) : /Примерное место/.test(place), place);
  const hl = await page.evaluate(() => window.standAdapter.current().features.map((f) => f.geometry.type));
  check(`${tag}: примерная область подсвечена`, hl.includes("Polygon"));
  await page.fill("#bc-text", lang === "kk" ? "Аулада шамдар жанбайды" : "Во дворе не горят фонари вечером");
  await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 6000 });
  // Житель меняет категорию вручную через сетку из 12.
  await page.click(".bc-change");
  const chips = await page.$$eval(".bc-grid__chip", (n) => n.length);
  check(`${tag}: сетка из 12 категорий`, chips === 12, String(chips));
  await shot(page, `${tag}-grid`);
  await page.click(".bc-grid__chip:nth-child(5)");
  // Обрыв сети при отправке: тост с «Повторить», текст не теряется.
  await page.route("**/api/civic/v2/complaints", (route) => route.request().method() === "POST" ? route.abort() : route.continue());
  await page.click(".bc-send");
  await page.waitForSelector(".bc-toast:not([hidden])", { timeout: 15000 }).catch(async (err) => {
    console.log("DIAG notes=", JSON.stringify(page.retryNotes), "clicks=", await page.evaluate(() => window.standClicks), "step=", await page.$eval(".bc-panel", (e) => e.dataset.step),
                "panel=", (await page.textContent(".bc-panel")).slice(0, 300));
    throw err;
  });
  const toast = await page.textContent(".bc-toast");
  const kept = await page.inputValue("#bc-text");
  check(`${tag}: обрыв сети — понятный тост и текст сохранён`, /Повтор|Қайталау/.test(toast) && kept.length > 5, toast);
  await shot(page, `${tag}-offline`);
  await page.unroute("**/api/civic/v2/complaints");
  await page.click(".bc-toast .bk-btn");
  await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 15000 });
  const code = await page.textContent(".bc-code__value");
  check(`${tag}: отправлено, номер обращения`, /^B-\d{4,}$/.test(code), code);
  const steps = await page.$$eval(".bk-steps__item", (n) => n.map((x) => x.getAttribute("data-state")));
  check(`${tag}: шкала статуса принято → в работе → исправлено`, steps.join() === "current,todo,todo", steps.join());
  await shot(page, `${tag}-sent`);
  await page.click(".bc-panel[data-step='5'] .bk-btn--primary");
  await page.waitForSelector(".bc-mine__card");
  const cards = await page.$$eval(".bc-mine__card", (n) => n.length);
  check(`${tag}: «Мои обращения» показывает отправленное`, cards === 1, String(cards));
  const demoTag = await page.$$eval(".bc-mine .bk-tag--demo", (n) => n.length);
  check(`${tag}: своё обращение не помечено «Пример»`, demoTag === 0);
  await shot(page, `${tag}-mine`);
  check(`${tag}: нет горизонтальной прокрутки`, await noHorizontalScroll(page));
  const keys = await visibleKeys(page);
  check(`${tag}: нет ключей и технических слов`, keys.length === 0, keys.join(", "));
  // Повторная отправка того же черновика не создаёт дубль: request_id тот же (идемпотентность проверена в pytest).
  check(`${tag}: нет ошибок консоли`, page.problems.filter((p) => !/Failed to load resource|ERR_FAILED/.test(p)).length === 0,
        page.problems.join(" | "));
  await page.context().close();
}

async function withoutMl(browser, base, hot, tag) {
  const page = await newPage(browser, base, 375, 812, "ru");
  await page.click(".bc-fab");
  await clickMapAt(page, hot.point);
  await page.waitForSelector(".bc-option--first", { timeout: 8000 });
  await page.click(".bc-option--first");
  await page.fill("#bc-text", "Снег не убран, скользко");
  await page.waitForSelector(".bc-grid", { timeout: 8000 });
  check(`${tag}: /classify недоступен — сразу сетка категорий, без ошибки`,
        !(await page.isVisible(".bc-toast:not([hidden])")));
  await page.click(".bc-grid__chip:nth-child(2)");
  await page.click(".bc-send");
  await page.waitForSelector(".bc-panel[data-step='4']", { timeout: 8000 });
  check(`${tag}: /similar недоступен — «Я тоже» по той же цели`, /\d/.test(await page.textContent(".bc-title")),
        await page.textContent(".bc-title"));
  await page.click(".bc-different");  // «У меня другое»
  await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 8000 });
  check(`${tag}: «У меня другое» — новая жалоба отправлена`, /^B-/.test(await page.textContent(".bc-code__value")));
  const errorsShown = await page.isVisible(".bc-toast:not([hidden])");
  check(`${tag}: житель не видит ошибок ML`, !errorsShown);
  await shot(page, `${tag}-done`);
  await page.context().close();
}

async function keyboard(browser, base, tag) {
  const page = await newPage(browser, base, 1366, 768, "ru");
  let reached = false;
  for (let i = 0; i < 12 && !reached; i++) {
    await page.keyboard.press("Tab");
    reached = await page.evaluate(() => document.activeElement && document.activeElement.classList.contains("bc-fab"));
  }
  check(`${tag}: Tab доходит до главной кнопки`, reached);
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  check(`${tag}: видна рамка фокуса`, outline && outline !== "none", outline);
  await page.keyboard.press("Enter");
  await page.waitForSelector(".bc-panel[data-step='2']");
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
  check(`${tag}: фокус переходит на заголовок шага`, focused === "bc-title", focused);
  await page.keyboard.press("Escape");
  check(`${tag}: Escape закрывает панель`, await page.isHidden(".bc-panel"));
  await page.context().close();
}

(async () => {
  const procs = [];
  let exitCode = 0;
  try {
    procs.push(await startStand(8791, []));
    procs.push(await startStand(8792, ["--no-ml"]));
    const browser = await chromium.launch();
    const info1 = await (await fetch("http://127.0.0.1:8791/stand/info")).json();
    const info2 = await (await fetch("http://127.0.0.1:8792/stand/info")).json();
    await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "ru", 375, 812, "375-ru");
    await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "kk", 375, 812, "375-kk");
    await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "ru", 1366, 768, "1366-ru");
    // Разные «пустые» точки: иначе вторая жалоба в той же ячейке правильно получит «Я тоже» к первой.
    await newComplaintAndMine(browser, "http://127.0.0.1:8791", "kk", 375, 812, "375-kk-new", [71.4605, 51.0785]);
    await newComplaintAndMine(browser, "http://127.0.0.1:8791", "ru", 1366, 768, "1366-ru-new", [71.3965, 51.0765]);
    await withoutMl(browser, "http://127.0.0.1:8792", info2.hot, "375-noml");
    await keyboard(browser, "http://127.0.0.1:8791", "1366-kbd");
    await browser.close();
  } catch (err) {
    console.error(err);
    check("стенд и браузер запустились", false, String(err && err.message));
  } finally {
    procs.forEach((p) => p.kill());
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - failed}/${results.length} PASS`);
  if (failed) exitCode = 1;
  process.exit(exitCode);
})();
