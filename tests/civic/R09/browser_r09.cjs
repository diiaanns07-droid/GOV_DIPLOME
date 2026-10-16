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
// --r11 <папка WEB ветки R11, в ней civic/ui-kit и civic/i18n>: стенд подключает настоящий ui-kit и словари R11.
//   Например: git archive origin/claude/r14-R11 web/civic/ui-kit web/civic/i18n | tar -x -C /tmp/r11 → --r11 /tmp/r11/web
//   (корень репозитория вместо web — стенд без стилей и ложные FAIL, R11 разбор 5 №5).
const r11Dir = args.includes("--r11") ? path.resolve(args[args.indexOf("--r11") + 1]) : null;
// --real: стенд вызывает настоящие R12 engine.civic_geo и R04 ui.civic_ml_api (их пакеты должны лежать в дереве).
const real = args.includes("--real");
// --only local_final: только проверки LOCAL_FINAL №1–2 (быстро); --only wave: только сценарии волны 1–2.
const only = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
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
    // Прогон упал необработанной ошибкой — стенд не остаётся занимать порт до следующего прогона.
    process.on("exit", () => { try { proc.kill(); } catch (e) { /* уже остановлен */ } });
    let out = "";
    const timer = setTimeout(() => reject(new Error("stand did not start: " + out)), 90000);
    proc.stdout.on("data", (d) => { out += d; if (out.includes("R09 stand:")) { clearTimeout(timer); resolve(proc); } });
    proc.stderr.on("data", (d) => { out += d; });
    proc.on("exit", (code) => { clearTimeout(timer); reject(new Error("stand exited " + code + ": " + out)); });
  });
}

async function newPage(browser, base, width, height, lang, opts = {}) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1,
                                             hasTouch: width < 1024, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  // Сессия сотрудника в том же браузере (стенд: cookie stand_staff=1 — как вход R02 в приложении).
  if (opts.staff) await context.addCookies([{ name: "stand_staff", value: "1", url: base }]);
  // Заранее известное устройство жителя (волна 2: автор и «Я тоже» — разные устройства одного сценария).
  if (opts.device) await context.addInitScript((d) => { try { localStorage.setItem("birge.device", d); } catch (e) { /* нет хранилища */ } }, opts.device);
  const page = await context.newPage();
  page.problems = [];
  page.on("console", (msg) => {
    if (/Failed to load resource/.test(msg.text())) return;  // сетевые ответы проверяются ниже по URL
    // Ошибки, предупреждения i18n и предупреждения стиля MapLibre («Expected value…», «layers.…»).
    const text = msg.text();
    if (msg.type() === "error" || (msg.type() === "warning" && /\[i18n\]|Expected value|layers\.|неизвестный ключ/.test(text))) page.problems.push(text);
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

async function centerOn(page, point, zoom = 17) {
  // Точку ставим в середину видимой части карты (на телефоне снизу шторка, на ноутбуке справа панель):
  // jumpTo + panBy без анимации, затем проверяем, что точка действительно в видимой области.
  return page.evaluate(async ([p, zoom]) => {
    const map = window.standMap;
    const canvas = map.getCanvas().getBoundingClientRect();
    const panel = document.querySelector(".bc-panel");
    const r = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    const mobile = window.innerWidth < 1024;
    // Ноутбук: панель R09 — карточка слева (эталон A, с 13 окт), раньше была справа — видимая часть карты по другую сторону.
    const leftCard = r && !mobile && r.left + r.width / 2 < (canvas.left + canvas.right) / 2;
    const left = leftCard ? r.right : canvas.left;
    const right = r && !mobile && !leftCard ? r.left : canvas.right;
    const bottom = r && mobile ? r.top : canvas.bottom;
    const want = { x: (left + right) / 2, y: (canvas.top + bottom) / 2 };
    for (let i = 0; i < 3; i++) {
      map.jumpTo({ center: p, zoom });
      const q = map.project(p);
      map.panBy([canvas.left + q.x - want.x, canvas.top + q.y - want.y], { duration: 0 });
      await new Promise((ok) => setTimeout(ok, 150));
      const now = map.project(p);
      const got = { x: canvas.left + now.x, y: canvas.top + now.y };
      if (Math.abs(got.x - want.x) < 4 && Math.abs(got.y - want.y) < 4) return got;
    }
    const q = map.project(p);
    return { x: canvas.left + q.x, y: canvas.top + q.y, unstable: true };
  }, [point, zoom]);
}

async function clickMapAt(page, point) {
  const xy = await centerOn(page, point);
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
  // Сначала дождаться конца анимаций (въезд шага 240 мс сдвигает содержимое на 18 px — это не вёрстка).
  await page.evaluate(() => Promise.race([new Promise((ok) => setTimeout(ok, 1500)), Promise.all(document.getAnimations()
    .filter((a) => a.effect && a.effect.getComputedTiming().iterations !== Infinity)   // бесконечные (скелетон) не ждём
    .map((a) => a.finished.catch(() => null)))])).catch(() => null);
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

// R11 №5: ни одно слово подписи категории не разорвано на две строки и не вылезает за кнопку.
async function checkGridWords(page, tag) {
  const res = await page.evaluate(() => {
    const broken = [];
    const buttons = [...document.querySelectorAll(".bk-catgrid > button")];
    buttons.forEach((b) => {
      const span = b.querySelector("span");
      const node = span && span.firstChild;
      if (!node) return;
      const text = node.textContent;
      let i = 0;
      text.split(/(\s+)/).forEach((part) => {
        if (part.trim()) {
          const r = document.createRange();
          r.setStart(node, i); r.setEnd(node, i + part.length);
          const lines = new Set([...r.getClientRects()].map((x) => Math.round(x.top)));
          const br = b.getBoundingClientRect(), wr = r.getBoundingClientRect();
          if (lines.size > 1 || wr.right > br.right + 0.5) broken.push(part);
        }
        i += part.length;
      });
    });
    const columns = new Set(buttons.map((b) => Math.round(b.getBoundingClientRect().left))).size;
    return { broken, columns, count: buttons.length };
  });
  // count === 12: без кнопок проверка не должна «проходить» впустую.
  check(`${tag}: [R11-5] слова в сетке категорий не рвутся (кнопок: ${res.count}, колонок: ${res.columns})`,
        res.count === 12 && res.broken.length === 0 && res.columns >= 1 && res.columns <= 3, res.broken.join(", "));
}

// UX_BRIEF №2: в панели жалобы текст не мельче 13 px (шкала чистого дизайна 13/15/17/22/28 — решение владельца 12 окт,
// R11 CLEAN_PASS §4: порог «мелкий текст» < 13 px, было 14), кнопки и поля не ниже 44 px (ui-kit даёт 48).
async function uxSizes(page) {
  return page.evaluate(() => {
    const bad = [];
    document.querySelectorAll(".bc-panel:not([hidden]) *, .bc-fab").forEach((n) => {
      const r = n.getBoundingClientRect();
      if (!r.width || getComputedStyle(n).visibility === "hidden") return;
      const own = [...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
      if (own && parseFloat(getComputedStyle(n).fontSize) < 13) bad.push("text " + n.textContent.trim().slice(0, 24) + " " + getComputedStyle(n).fontSize);
      if (/^(BUTTON|A|INPUT|TEXTAREA)$/.test(n.tagName) && r.height < 44) bad.push("tap " + n.textContent.trim().slice(0, 24) + " " + Math.round(r.height));
    });
    return bad;
  });
}

// Волна 2 (обязательные мелочи): перед отправкой — экран проверки (шаг 4, data-review=1) с «Отправить».
async function sendFromReview(page, timeout = 10000) {
  await page.waitForSelector(".bc-panel[data-review='1'] .bc-send:not([disabled])", { timeout });
  await page.click(".bc-panel[data-review='1'] .bc-send");
}

async function shot(page, name) {
  // Дать закончиться анимациям шторки и тоста (240–300 мс), иначе кадр ловит полупрозрачное промежуточное состояние.
  if (shotDir) { await page.waitForTimeout(450); await page.screenshot({ path: path.join(shotDir, name + ".png") }); }
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
  const hotLabel = lang === "kk" ? hot.target.label_kk : hot.target.label_ru;
  // R11 №4: вопрос без вставки названия (иначе «Это Остановка …?»), варианты — сами названия.
  const q = (await page.textContent(".bc-question")).trim();
  check(`${tag}: [R11-4] вопрос «${q}» без названия цели, вариант без «Да,»`,
        q === (lang === "kk" ? "Осы жерде ме?" : "Это здесь?") && !/^\s*(Да|Иә),/.test(question) &&
        question.trim().startsWith(hotLabel), question.trim());
  check(`${tag}: шаг 2 первым предлагает реальную остановку OSM`, question.includes(hotLabel), question);
  const others = await page.$$eval(".bc-option:not(.bk-btn--ghost)", (n) => n.length);
  check(`${tag}: рядом ещё участок улицы и «Другое место»`, others >= 2 && !!(await page.$(".bc-option.bk-btn--ghost")), String(others));
  await shot(page, `${tag}-2-candidates`);
  await page.click(".bc-option--first"); taps++;
  await page.waitForSelector(".bc-panel[data-step='3']");
  const hl = await page.evaluate(() => window.standAdapter.current().features.map((f) => f.geometry.type));
  const exact = await page.evaluate((p) => { const f = window.standAdapter.current().features[0];
    return f && f.geometry.type === "Point" && f.geometry.coordinates[0] === p[0] && f.geometry.coordinates[1] === p[1]; }, hot.point);
  check(`${tag}: выбранная остановка подсвечена в своей точке OSM`, exact, JSON.stringify(hl));
  // R11 №1: все слои подсветки добавились (раньше line-dasharray с выражением ронял bc-area-line).
  const layers = await page.evaluate(() => ["bc-area", "bc-area-line", "bc-area-approx", "bc-line-casing", "bc-line", "bc-point"]
    .filter((id) => !window.standMap.getLayer(id)));
  check(`${tag}: [R11-1] все 6 слоёв подсветки на карте, ошибок стиля нет`, layers.length === 0 &&
        !page.problems.some((p) => /layers\.|dasharray/.test(p)), layers.join(","));
  // R11 №2: цель и точка нажатия различаются: у цели pick=false (11 px), у нажатия pick=true (6 px).
  const pick = await page.evaluate(() => ({
    radius: JSON.stringify(window.standMap.getPaintProperty("bc-point", "circle-radius")),
    flags: window.standAdapter.current().features.map((f) => f.properties.pick) }));
  check(`${tag}: [R11-2] цель 11 px и точка нажатия 6 px различаются, без предупреждения null`,
        pick.radius.includes("coalesce") && JSON.stringify(pick.flags) === "[false,true]" &&
        !page.problems.some((p) => /Expected value/.test(p)), JSON.stringify(pick));
  const text = lang === "kk" ? "Аялдаманың павильоны сынған, шатыры жоқ" : "Павильон остановки сломан, нет крыши";
  await page.fill("#bc-text", text);
  await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 6000 });
  // R11 №3: кнопка «Отправить» активна сразу после подсказки модели, без нового нажатия клавиши.
  const sendEnabled = await page.$eval(".bc-send", (b) => !b.disabled);
  check(`${tag}: [R11-3] «Отправить» активна сразу после подсказки /classify`, sendEnabled);
  // R11 №6: в чипе не больше одной галочки — её рисует ui-kit (::before), своей в тексте нет. Эталон A (13 окт): выбранный
  // чип — тёмная заливка без галочки (.chip.on), поэтому ::before может быть пустым; выбор виден по заливке.
  const ticks = await page.$eval(".bc-cat-row .bk-chip[aria-pressed='true']", (c) => ({
    inText: (c.textContent.match(/✓/g) || []).length, before: getComputedStyle(c, "::before").content,
    bg: getComputedStyle(c).backgroundColor }));
  const darkFill = /rgb\((\d+), (\d+), (\d+)\)/.test(ticks.bg) && ticks.bg.match(/\d+/g).slice(0, 3).every((v) => +v < 80);
  check(`${tag}: [R11-6] не больше одной галочки в чипе категории, выбор виден`, ticks.inText === 0 &&
        (/✓/.test(ticks.before) || darkFill), JSON.stringify(ticks));
  const sizes3 = await uxSizes(page);
  check(`${tag}: [UX] шаг 3 — текст ≥ 13 px, кнопки ≥ 44 px`, sizes3.length === 0, sizes3.join("; "));
  const chip = await page.textContent(".bc-cat-row");
  check(`${tag}: подсказка категории чипом`, lang === "kk" ? /Аялдамалар мен көлік/.test(chip) : /Остановки и транспорт/.test(chip), chip.trim());
  await shot(page, `${tag}-3-text`);
  await page.click(".bc-send"); taps++;
  await page.waitForSelector(".bc-panel[data-step='4']:not([data-review])", { timeout: 8000 });
  const title4 = await page.textContent(".bc-title");
  const before = Number((title4.match(/\d+/) || [0])[0]);
  check(`${tag}: шаг 4 «уже сообщили N» (N ≥ 7 по демо-цели)`, before >= 7, title4);
  const demoTag = await page.$$eval(".bc-similar .bk-tag--demo", (x) => x.map((e) => e.textContent.trim()));
  check(`${tag}: похожая демо-жалоба на шаге 4 помечена «Пример»`, demoTag.length === 1, demoTag.join());
  const leak = await page.evaluate(() => document.querySelector(".bc-panel").innerText.includes("нет крыши") &&
    !document.querySelector("#bc-text"));
  check(`${tag}: чужой текст жалобы не показан`, !leak);
  await shot(page, `${tag}-4-similar`);
  if (tag === "375-ru") {
    // R15 (ночь): лимит «Я тоже» (429) — понятное сообщение без «Повторить» (повтор снова упрётся в лимит).
    await page.route("**/metoo", (route) => route.fulfill({ status: 429, contentType: "application/json",
      body: JSON.stringify({ ok: false, error: { code: "too_many_requests" }, retry_after: 60 }) }));
    await page.click(".bc-panel[data-step='4'] .bk-btn--primary");
    await page.waitForSelector(".bc-toast:not([hidden])", { timeout: 8000 });
    const limited = await page.$eval(".bc-toast", (t) => ({ text: t.textContent, retry: !!t.querySelector(".bk-btn") }));
    check(`${tag}: [R15] «Я тоже» при лимите — сообщение без «Повторить»`, !limited.retry && /много|көп/.test(limited.text),
          JSON.stringify(limited));
    await page.unroute("**/metoo");
    page.problems = page.problems.filter((p) => !/^429 .*\/metoo$/.test(p));   // 429 подставлен тестом намеренно
    await page.click(".bc-toast .bc-toast__close");
  }
  await page.click(".bc-panel[data-step='4'] .bk-btn--primary"); taps++;
  await page.waitForSelector(".bc-panel[data-step='5']");
  const done = await page.textContent(".bc-panel");
  check(`${tag}: «Я тоже» засчитан — стало ${before + 1}`, done.includes(String(before + 1)), (await page.textContent(".bc-lead")) || "");
  const elapsed = (Date.now() - t0) / 1000;
  check(`${tag}: путь за ${taps} нажатий + текст, ${elapsed.toFixed(1)} с автоматом`, taps <= 6 && elapsed < 30);
  const events = await page.evaluate(() => window.standEvents);
  check(`${tag}: событие birge:complaint для тепловой карты`, events.length === 1 && events[0].type === "metoo" &&
    events[0].target && events[0].target.id === hot.target.id && events[0].reporters >= 2 && events[0].reporters <= before + 1,
    JSON.stringify(events));
  await shot(page, `${tag}-5-done`);
  const sizes5 = await uxSizes(page);
  check(`${tag}: [UX] шаг 5 — текст ≥ 13 px, кнопки ≥ 44 px`, sizes5.length === 0, sizes5.join("; "));
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
  if (await page.$(".bc-option")) {
    // Ровно один способ выбрать «примерное место»: вариант R12 (с улицей в подписи) или своя кнопка «Другое место».
    const approx = await page.$$eval(".bc-option", (n) => n.map((x) => x.textContent.trim())
      .filter((t) => /Примерн|Шамамен|Другое место|Басқа орын/.test(t)));
    check(`${tag}: одна кнопка «примерного места», без дублей`, approx.length === 1, approx.join(" | "));
    await page.click(".bc-option.bk-btn--ghost, .bc-option:has-text('Примерн'), .bc-option:has-text('Шамамен')");
  }
  await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
  const place = await page.textContent(".bc-place");
  check(`${tag}: нет объекта рядом — «примерное место»`, lang === "kk" ? /Шамамен/.test(place) : /Примерное место/.test(place), place);
  const hl = await page.evaluate(() => window.standAdapter.current().features.map((f) => f.geometry.type));
  check(`${tag}: примерная область подсвечена`, hl.includes("Polygon"));
  await page.fill("#bc-text", lang === "kk" ? "Аулада шамдар жанбайды" : "Во дворе не горят фонари вечером");
  await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 6000 });
  // Житель меняет категорию вручную через сетку из 12.
  await page.click(".bc-change");
  const chips = await page.$$eval(".bk-catgrid > button", (n) => n.length);
  check(`${tag}: сетка из 12 категорий`, chips === 12, String(chips));
  await checkGridWords(page, tag);
  await shot(page, `${tag}-grid`);
  await page.click(".bk-catgrid > button:nth-child(5)");
  // «Далее» -> похожих нет -> экран проверки: место, проблема, текст, фото и кто что увидит (волна 2, мелочи).
  await page.click(".bc-send");
  await page.waitForSelector(".bc-panel[data-review='1']", { timeout: 10000 }).catch(async (err) => {
    console.log("DIAG step=", await page.$eval(".bc-panel", (e) => e.dataset.step), "panel=", (await page.textContent(".bc-panel")).slice(0, 300));
    throw err;
  });
  const review = await page.evaluate(() => {
    const p = document.querySelector(".bc-panel");
    return { title: p.querySelector(".bc-title").textContent.trim(), rows: p.querySelectorAll(".bc-review__row").length,
             text: (p.querySelector(".bc-review__text") || {}).textContent || "", vis: (p.querySelector(".bc-visibility") || {}).textContent || "",
             primary: p.querySelectorAll(".bk-btn--primary").length, edit: !!p.querySelector(".bc-edit") };
  });
  check(`${tag}: [W2] проверка перед отправкой — место, проблема, текст, фото; одна главная кнопка и «Изменить»`,
        review.rows === 4 && review.text.length > 5 && review.primary === 1 && review.edit &&
        (lang === "kk" ? /Жіберер алдында/.test(review.title) : /Проверьте перед отправкой/.test(review.title)), JSON.stringify(review));
  check(`${tag}: [W2] «это увидят все / только служба» и подсказка убрать личное`,
        lang === "kk" ? /Барлығы көреді/.test(review.vis) && /Тек қызмет/.test(review.vis) && /ЖСН/.test(review.vis)
                      : /Увидят все/.test(review.vis) && /Только служба/.test(review.vis) && /ИИН/.test(review.vis), review.vis);
  await shot(page, `${tag}-review`);
  // Обрыв сети при отправке (волна 1, п. 10): обращение в очереди на телефоне, автоповтор, понятное сообщение.
  await page.route("**/api/civic/v2/complaints", (route) => route.request().method() === "POST" ? route.abort() : route.continue());
  await page.click(".bc-panel[data-review='1'] .bc-send");
  await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 15000 });
  const queued = await page.evaluate(() => ({ title: document.querySelector(".bc-title").textContent.trim(),
    lead: (document.querySelector(".bc-lead") || {}).textContent || "",
    outbox: JSON.parse(localStorage.getItem("birge.complaint.outbox") || "[]") }));
  check(`${tag}: [W1-10] нет сети — «${queued.title}», в очереди 1 обращение с текстом`,
        (lang === "kk" ? /телефонда сақталды/.test(queued.title) && /өзі жіберіледі/.test(queued.lead)
                       : /сохранено на телефоне/.test(queued.title) && /отправится само/.test(queued.lead)) &&
        queued.outbox.length === 1 && queued.outbox[0].body.text.length > 5, JSON.stringify({ t: queued.title, n: queued.outbox.length }));
  await shot(page, `${tag}-offline`);
  await page.unroute("**/api/civic/v2/complaints");
  await page.click(".bc-panel[data-step='5'] .bk-btn--primary");   // «Отправить сейчас» (иначе — автоповтор через 5–60 с)
  await page.waitForSelector(".bc-code__value", { timeout: 15000 });
  const code = await page.textContent(".bc-code__value");
  check(`${tag}: отправлено из очереди, номер обращения, очередь пуста`, /^B-\d{4,}$/.test(code) &&
        (await page.evaluate(() => JSON.parse(localStorage.getItem("birge.complaint.outbox") || "[]").length)) === 0, code);
  const after = await page.evaluate(() => [...document.querySelectorAll(".bc-panel .bc-next, .bc-panel .bc-meta")].map((n) => n.textContent).join(" | "));
  check(`${tag}: [W2] после отправки — номер, следующий шаг и как найти`,
        lang === "kk" ? /Әрі қарай: қызмет/.test(after) && /Менің өтініштерім/.test(after) : /Дальше: служба ответит до/.test(after) && /Мои обращения/.test(after), after);
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

// UX_BRIEF правило 7: у «Мои обращения» есть загрузка (скелетон), «пока пусто» с подсказкой и ошибка с «Повторить».
async function mineStates(browser, base, lang, width, height, tag) {
  const page = await newPage(browser, base, width, height, lang);
  const MINE = "**/api/civic/v2/complaints/mine";
  // Запрос мог закончиться без нас (страницу перезагрузили, пока ответ «шёл» 2,5 с) — тогда continue не нужен.
  await page.route(MINE, async (route) => { await new Promise((ok) => setTimeout(ok, 2500)); await route.continue().catch(() => null); });
  await page.evaluate(() => window.standUi.openMine());
  const loading = await page.waitForSelector(".bc-panel .bc-loading .bk-skel", { timeout: 3000 }).then(() => true, () => false);
  const loadingText = loading ? (await page.textContent(".bc-panel .bc-loading")).trim() : "";
  check(`${tag}: «Мои обращения» — загрузка: скелетон и «${loadingText}»`, loading && /Загружаем|жүктелуде/.test(loadingText));
  await shot(page, `${tag}-mine-loading`);
  await page.waitForSelector(".bc-panel .bk-empty", { timeout: 8000 });
  if (width < 1024) {
    // Пусто — шторка по содержимому, без пустого белого низа (UX_BRIEF правило 7); карта над ней видна.
    await page.waitForTimeout(400);
    const sheet = await page.evaluate(() => { const p = document.querySelector(".bc-panel"); const r = p.getBoundingClientRect();
      const last = p.querySelector(".bk-empty button").getBoundingClientRect();
      return { snap: p.dataset.snap, top: Math.round(r.top), gap: Math.round(r.bottom - last.bottom), h: innerHeight }; });
    check(`${tag}: «Мои обращения» пусто — шторка по содержимому (верх ${sheet.top} px, под кнопкой ${sheet.gap} px)`,
          sheet.snap === "peek" && sheet.top > sheet.h * 0.4 && sheet.gap < 120, JSON.stringify(sheet));
  }
  const empty = await page.evaluate(() => {
    const box = document.querySelector(".bc-panel .bk-empty"); const b = box.querySelector("button").getBoundingClientRect();
    return { title: box.querySelector(".bk-empty__title").textContent.trim(), text: box.textContent.trim(), h: Math.round(b.height) };
  });
  check(`${tag}: «Мои обращения» — пусто: «${empty.title}», подсказка и кнопка «Сообщить» (${empty.h} px)`,
        /ничего не отправляли|ештеңе жібермедіңіз/.test(empty.title) && /Сообщить о проблеме|Мәселе туралы хабарлау/.test(empty.text)
        && empty.h >= 44, JSON.stringify(empty));   // эталон A: кнопки 44 (.btn)
  await shot(page, `${tag}-mine-empty`);
  // Правило 4 эталона A (R10 §9): повторное открытие — сразу из памяти, и пустой список тоже (сервер ещё отвечает 2,5 с).
  await page.evaluate(() => window.standUi.openMine());
  await page.waitForTimeout(300);
  const again = await page.evaluate(() => ({ empty: !!document.querySelector(".bc-panel .bk-empty"),
                                             loading: !!document.querySelector(".bc-panel .bc-loading, .bc-panel .bk-skel") }));
  check(`${tag}: «Мои обращения» — повторное открытие сразу из памяти (пусто без «Загружаем…»)`,
        again.empty && !again.loading, JSON.stringify(again));
  await page.waitForTimeout(2400);   // ответ этого открытия приходит — дальше без «висящих» запросов
  await page.unroute(MINE);
  await page.route(MINE, (route) => route.abort());
  const errorBox = async (sel) => page.evaluate((s) => {
    const box = document.querySelector(s); const b = box.querySelector("button").getBoundingClientRect();
    return { title: box.querySelector(".bk-error__title").textContent.trim(), button: box.querySelector("button").textContent.trim(),
             role: box.getAttribute("role"), h: Math.round(b.height), list: !!document.querySelector(".bc-panel .bk-empty") };
  }, sel);
  // Нет связи, а список уже был: сверху «Нет связи» с «Повторить», ниже — то, что было (не пустой экран ошибки).
  await page.evaluate(() => window.standUi.openMine());
  await page.waitForSelector(".bc-panel .bk-error.bc-stale", { timeout: 8000 });
  const stale = await errorBox(".bc-panel .bk-error.bc-stale");
  check(`${tag}: «Мои обращения» — нет связи при списке в памяти: «${stale.title}» и «${stale.button}» над списком`,
        /Нет связи|байланыс жоқ/.test(stale.title) && /Повторить|Қайталау/.test(stale.button) && stale.role === "alert"
        && stale.h >= 44 && stale.list, JSON.stringify(stale));
  // Первое открытие без связи (страница заново — памяти нет): экран ошибки с иллюстрацией и «Повторить».
  await page.reload();
  await page.evaluate((l) => BirgeComplaint.setLang(l), lang);
  await page.waitForFunction(() => document.documentElement.getAttribute("data-map-ready") === "1", null, { timeout: 15000 });
  await page.evaluate(() => window.standUi.openMine());
  await page.waitForSelector(".bc-panel .bk-error:not(.bc-stale)", { timeout: 8000 });
  const error = await errorBox(".bc-panel .bk-error:not(.bc-stale)");
  check(`${tag}: «Мои обращения» — нет связи: «${error.title}» и «${error.button}» (${error.h} px)`,
        /Нет связи|байланыс жоқ/.test(error.title) && /Повторить|Қайталау/.test(error.button) && error.role === "alert" && error.h >= 44
        && !error.list, JSON.stringify(error));
  await shot(page, `${tag}-mine-error`);
  await page.unroute(MINE);
  await page.click(".bc-panel .bk-error button");
  const back = await page.waitForSelector(".bc-panel .bk-empty", { timeout: 8000 }).then(() => true, () => false);
  check(`${tag}: «Повторить» загружает снова`, back);
  await page.click(".bc-panel .bk-empty button");
  const wizard = await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 5000 }).then(() => true, () => false);
  check(`${tag}: кнопка из пустого списка открывает «Где проблема?»`, wizard);
  check(`${tag}: нет горизонтальной прокрутки`, await noHorizontalScroll(page));
  const keys = await visibleKeys(page);
  check(`${tag}: нет ключей и технических слов`, keys.length === 0, keys.join(", "));
  check(`${tag}: нет ошибок консоли`, page.problems.filter((p) => !/Failed to load resource|ERR_FAILED/.test(p)).length === 0,
        page.problems.join(" | "));
  await page.context().close();
}

// Несколько ОТДЕЛЬНЫХ жалоб об одном и том же на одном месте (так засевает демо R01): «Об этом уже сообщили N» —
// все люди по месту и категории (как число на значке карты), а не только самая похожая жалоба; после «Я тоже» — N+1.
async function placeTotal(browser, base, lang, width, height, tag, point) {
  const api = async (method, p, body, device) => (await fetch(base + "/api/civic/v2" + p, { method,
    headers: { "Content-Type": "application/json", "X-Birge-Device": device }, body: body ? JSON.stringify(body) : undefined })).json();
  const text = "Во дворе разбита детская площадка, сломаны качели";
  // Первая жалоба с заведомо далёкой целью: сервер сам ставит «примерное место» у точки (R15 S12) — берём его как цель.
  const a = await api("POST", "/complaints", { text, category: "yards", point, target: { kind: "object", id: "osm-node-1" } }, "dev-r09-place-total-a1");
  const target = a.data.complaint.target;
  await api("POST", "/complaints", { text: text + " и скамейка", category: "yards", point, target }, "dev-r09-place-total-b2");
  const b = await api("GET", `/complaints/summary?target_id=${encodeURIComponent(target.id)}&category=yards&days=14`, null, "dev-r09-place-total-c3");
  const page = await newPage(browser, base, width, height, lang);
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']");
  await clickMapAt(page, point);
  await page.waitForSelector(".bc-panel[data-step='3'], .bc-option", { timeout: 8000 });
  if (await page.$(".bc-option")) await page.click(".bc-option.bk-btn--ghost, .bc-option:has-text('Примерн'), .bc-option:has-text('Шамамен')");
  await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
  await page.fill("#bc-text", text);
  // Модель стенда по словам «двор», «площадка» подсказывает «Дворы и площадки» — как у двух жалоб выше.
  await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 8000 });
  await page.click(".bc-send");
  const step4 = await page.waitForSelector(".bc-panel[data-step='4']:not([data-review])", { timeout: 10000 }).then(() => true, () => false);
  const title = step4 ? (await page.textContent(".bc-title")).trim() : "";
  const n = Number((title.match(/\d+/) || [0])[0]);
  check(`${tag}: две отдельные жалобы на месте — «${title}» (всего людей по месту: ${b.data.reporters})`,
        step4 && b.data.complaints === 2 && n === b.data.reporters && n === 2, JSON.stringify({ title, summary: b.data.reporters }));
  const badge = step4 ? (await page.textContent(".bc-similar__badge")).trim() : "";
  check(`${tag}: число на карточке похожей жалобы — то же (${badge})`, badge === String(n));
  await shot(page, `${tag}-4-similar`);
  if (step4) {
    await page.click(".bc-panel[data-step='4'] .bk-btn--primary");
    await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 8000 });
    const lead = (await page.textContent(".bc-lead")).trim();
    check(`${tag}: после «Я тоже» — «${lead}»`, lead.includes(String(n + 1)), lead);
    const after = await api("GET", `/complaints/summary?target_id=${encodeURIComponent(target.id)}&category=yards&days=14`, null, "dev-r09-place-total-c3");
    check(`${tag}: на сервере людей по месту стало ${n + 1}, жалоб по-прежнему 2`, after.data.reporters === n + 1 && after.data.complaints === 2,
          JSON.stringify(after.data && { reporters: after.data.reporters, complaints: after.data.complaints }));
    await shot(page, `${tag}-5-done`);
    await page.click(".bc-panel[data-step='5'] .bk-btn--primary");
    await page.waitForSelector(".bc-mine__card", { timeout: 8000 });
    const card = (await page.textContent(".bc-mine__card")).replace(/\s+/g, " ");
    check(`${tag}: в «Мои обращения» — то же число людей (${n + 1}), что на шаге «Я тоже»`, card.includes(String(n + 1)), card.slice(0, 160));
    await shot(page, `${tag}-mine`);
  }
  check(`${tag}: нет ошибок консоли`, page.problems.length === 0, page.problems.join(" | "));
  await page.context().close();
}

async function withoutMl(browser, base, hot, tag) {
  const page = await newPage(browser, base, 375, 812, "ru");
  await page.click(".bc-fab");
  await clickMapAt(page, hot.point);
  await page.waitForSelector(".bc-option--first", { timeout: 8000 });
  await page.click(".bc-option--first");
  await page.fill("#bc-text", "Павильон остановки сломан");
  await page.waitForSelector(".bk-catgrid", { timeout: 8000 });
  check(`${tag}: /classify недоступен — сразу сетка категорий, без ошибки`,
        !(await page.isVisible(".bc-toast:not([hidden])")));
  await checkGridWords(page, tag);
  await page.click(".bk-catgrid > button:nth-child(4)");  // «Остановки и транспорт»
  await page.click(".bc-send");
  await page.waitForSelector(".bc-panel[data-step='4']:not([data-review])", { timeout: 8000 });
  check(`${tag}: /similar недоступен — «Я тоже» по той же цели`, /\d/.test(await page.textContent(".bc-title")),
        await page.textContent(".bc-title"));
  await page.click(".bc-different");  // «У меня другое» -> проверка перед отправкой
  await sendFromReview(page);
  await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 8000 });
  check(`${tag}: «У меня другое» — новая жалоба отправлена`, /^B-/.test(await page.textContent(".bc-code__value")));
  const errorsShown = await page.isVisible(".bc-toast:not([hidden])");
  check(`${tag}: житель не видит ошибок ML`, !errorsShown);
  await shot(page, `${tag}-done`);
  await page.context().close();
}

// R10 B-019 / LOCAL №2 / R11 B1 №3: значок тепловой карты R07 (маркер MapLibre с собственным обработчиком,
// гасящим всплытие, как в heat.js) не должен «съедать» нажатие в «Где проблема?».
async function badgeTap(browser, base, hot, lang, width, height, tag) {
  const page = await newPage(browser, base, width, height, lang);
  await page.evaluate((p) => {
    window.r07Clicks = 0;
    const make = (kind, at) => {
      const el = document.createElement("button");
      el.className = "r07-badge"; el.type = "button"; el.dataset.kind = kind; el.textContent = kind === "district" ? "Нұра · 12" : "13";
      el.style.cssText = "min-width:40px;height:32px;border-radius:16px;background:#a32d2d;color:#fff;border:2px solid #fff";
      el.addEventListener("click", (ev) => { ev.stopPropagation(); window.r07Clicks++; });   // как R07: свой обработчик
      return new window.maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(at).addTo(window.standMap);
    };
    make("object", p);
    make("district", [p[0] + 0.004, p[1] + 0.002]);
  }, hot.point);
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']");
  const picking = await page.evaluate(() => document.documentElement.classList.contains("bc-picking"));
  await centerOn(page, hot.point);
  const box = await page.$eval(".r07-badge[data-kind='object']", (b) => { const r = b.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  if (width < 1024) await page.touchscreen.tap(box.x, box.y); else await page.mouse.click(box.x, box.y);
  const offered = await page.waitForSelector(".bc-option--first", { timeout: 8000 }).then(() => true, () => false);
  const first = offered ? (await page.textContent(".bc-option--first")).trim() : "";
  const hotLabel = lang === "kk" ? hot.target.label_kk : hot.target.label_ru;
  check(`${tag}: нажатие на значок тепловой карты выбирает это место («${first.slice(0, 40)}»)`,
        picking && offered && first.startsWith(hotLabel), `bc-picking=${picking}`);
  check(`${tag}: значок не открыл свою карточку во время выбора места`, (await page.evaluate(() => window.r07Clicks)) === 0);
  // Значок района только приближает карту — район не место жалобы.
  const zoom0 = await page.evaluate(() => window.standMap.getZoom());
  await centerOn(page, [hot.point[0] + 0.004, hot.point[1] + 0.002], 12);
  const dist = await page.$eval(".r07-badge[data-kind='district']", (b) => { const r = b.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2, visible: r.width > 0 }; });
  const before = await page.evaluate(() => window.standAdapter.current().features.length);
  if (dist.visible) {
    if (width < 1024) await page.touchscreen.tap(dist.x, dist.y); else await page.mouse.click(dist.x, dist.y);
  }
  await page.waitForTimeout(800);
  const after = await page.evaluate(() => ({ zoom: window.standMap.getZoom(),
    point: JSON.stringify(window.standAdapter.current().features.find((f) => f.properties.pick) || null) }));
  check(`${tag}: значок района приближает карту, а не выбирает место`, dist.visible && after.zoom >= 14 &&
        (await page.evaluate(() => window.r07Clicks)) === 0, `zoom ${zoom0.toFixed(1)} -> 12 -> ${after.zoom.toFixed(1)}`);
  // После выбора места значок снова работает как значок R07.
  await page.keyboard.press("Escape");
  await page.waitForSelector(".bc-panel", { state: "hidden" });
  const after2 = await page.evaluate(() => document.documentElement.classList.contains("bc-picking"));
  await page.$eval(".r07-badge[data-kind='object']", (b) => b.click());
  check(`${tag}: мастер закрыт — значок снова открывает свою карточку`, !after2 &&
        (await page.evaluate(() => window.r07Clicks)) === 1);
  check(`${tag}: нет ошибок консоли`, page.problems.length === 0, page.problems.join(" | "));
  await page.context().close();
}

// Ночь раунда 14: раскладка на телефоне по UX_REVIEW R11 (день 2 №7–10, B1 №2 и №8, B2 №3).
async function phoneLayout(browser, base, hot, lang, tag) {
  const page = await newPage(browser, base, 375, 812, lang);
  const fab = await page.$eval(".bc-fab", (b) => { const r = b.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), left: Math.round(r.left), text: b.textContent.trim() }; });
  // Эталон A (.fab): во всю ширину с полями 16, высота 54.
  check(`${tag}: [R11 №7/B1 №8, эталон] «Сообщить о проблеме» во всю ширину, одна строка, 54 px`,
        fab.w >= 340 && fab.left === 16 && fab.h >= 54 && fab.h <= 58, JSON.stringify(fab));
  await page.evaluate(() => { const c = document.createElement("article"); c.className = "r07-card"; c.id = "fake-r07";
    document.body.appendChild(c); });
  const hiddenWithCard = await page.$eval(".bc-fab", (b) => getComputedStyle(b).display === "none");
  await page.evaluate(() => document.getElementById("fake-r07").remove());
  const backAfter = await page.$eval(".bc-fab", (b) => getComputedStyle(b).display !== "none");
  check(`${tag}: [R11 B1 №8] кнопка спрятана, пока открыта карточка места R07`, hiddenWithCard && backAfter);
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']");
  const peek = await page.$eval(".bc-panel", (p) => ({ snap: p.dataset.snap, h: Math.round(p.getBoundingClientRect().height) }));
  check(`${tag}: [R11 B1 №2] шаг 2 до выбора места — низкая шторка (${peek.h} px), карта видна`,
        peek.snap === "peek" && peek.h <= 300, JSON.stringify(peek));
  // Точка внутри двора (0 м) — «Вы здесь», а не метры.
  await page.route("**/api/civic/v2/targets**", (route) => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ ok: true, data: { candidates: [
      { target: { kind: "area", id: "yard-123", label_ru: "Двор — улица Сауран", label_kk: "Аула — Сауран көшесі" }, distance_m: 0,
        geometry: { type: "Polygon", coordinates: [[[hot.point[0] - 0.0005, hot.point[1] - 0.0003], [hot.point[0] + 0.0005, hot.point[1] - 0.0003],
          [hot.point[0] + 0.0005, hot.point[1] + 0.0003], [hot.point[0] - 0.0005, hot.point[1] - 0.0003]]] } },
      { target: hot.target, distance_m: 12.4, geometry: { type: "Point", coordinates: hot.point } }] } }) }));
  await clickMapAt(page, hot.point);
  await page.waitForSelector(".bc-option--first");
  const metas = await page.$$eval(".bc-option .bc-option__meta", (n) => n.map((x) => x.textContent.trim()));
  const half = await page.$eval(".bc-panel", (p) => p.dataset.snap);
  check(`${tag}: [R11 B2 №3] точка внутри двора — «${metas[0]}», рядом — метры`,
        metas[0] === (lang === "kk" ? "Сіз осындасыз" : "Вы здесь") && /12\s?м/.test(metas[1] || "") && half === "half",
        JSON.stringify({ metas, half }));
  await page.unroute("**/api/civic/v2/targets**");
  await page.click(".bc-option--first");
  await page.fill("#bc-text", lang === "kk" ? "Аулада шамдар жанбайды, түнде қараңғы" : "Во дворе не горят фонари, ночью темно");
  await page.waitForTimeout(900);
  if (!(await page.$(".bc-cat-row .bk-chip[aria-pressed='true']"))) await page.click(".bk-catgrid > button:nth-child(5)").catch(() => {});
  // Сбой сервера (500) — тост с «Повторить» (обрыв сети ведёт в очередь, его проверяет newComplaintAndMine).
  await page.route("**/api/civic/v2/complaints", (route) => route.request().method() === "POST"
    ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ ok: false, error: { code: "internal" } }) })
    : route.continue());
  await page.click(".bc-send");
  const viaSimilar = await page.waitForSelector(".bc-panel[data-review='1'], .bc-different", { timeout: 10000 })
    .then(async (el) => (await el.getAttribute("class")).includes("bc-different"));
  if (viaSimilar) await page.click(".bc-different");
  await sendFromReview(page);
  await page.waitForSelector(".bc-toast:not([hidden])", { timeout: 15000 });
  page.problems = page.problems.filter((p) => !/^500 .*\/complaints$/.test(p));   // 500 подставлен тестом намеренно
  await page.waitForTimeout(400);  // замер после анимации появления
  const toast = await page.$eval(".bc-toast", (t) => { const r = t.getBoundingClientRect(); const b = t.querySelector(".bk-btn");
    const br = b.getBoundingClientRect(); const x = t.querySelector(".bk-iconbtn");
    return { w: Math.round(r.width), inside: br.right <= r.right + 0.5 && br.left >= r.left - 0.5, close: !!x,
             centred: Math.abs((r.left + r.right) / 2 - window.innerWidth / 2) < 2,
             lines: Math.round(t.querySelector(".bk-toast__text").getBoundingClientRect().height / 20) }; });
  check(`${tag}: [R11 №8] тост ошибки широкий (${toast.w} px), «Повторить» внутри, есть ✕`,
        toast.w >= 330 && toast.inside && toast.close && toast.centred && toast.lines <= 3, JSON.stringify(toast));
  await shot(page, `${tag}-toast`);
  await page.unroute("**/api/civic/v2/complaints");
  await page.click(".bc-toast .bk-btn");
  await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 15000 });
  const due = await page.$$eval(".bc-panel .bc-next", (n) => n.map((x) => x.textContent).join(" | "));
  // Волна 2: срок ответа — в строке «Дальше: …» (complaint.step5.next), дата в общем формате (R11 №10).
  // kk — текст словаря R11 b06020a: «Әрі қарай: қызмет жауабының мерзімі — 15 қазан».
  const months = lang === "kk" ? /Әрі қарай: қызмет (жауабының мерзімі — )?\d{1,2}\u00a0(қаңтар|ақпан|наурыз|сәуір|мамыр|маусым|шілде|тамыз|қыркүйек|қазан|қараша|желтоқсан)/
    : /Дальше: служба ответит до \d{1,2}\u00a0(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)/;
  check(`${tag}: [R11 №10/B1 №10] срок ответа — «Дальше: …» и общий формат даты`, months.test(due), due);
  const ticks = await page.$eval(".bc-panel .bk-steps", (l) => (l.textContent.match(/✓/g) || []).length);
  check(`${tag}: [R11 №9] в шкале статуса нет своей «✓»`, ticks === 0);
  await page.click(".bc-panel[data-step='5'] .bk-btn--primary");
  await page.waitForSelector(".bc-mine__card");
  const date = await page.$eval(".bc-mine__card .bc-meta", (m) => m.textContent);
  check(`${tag}: [R11 №10] дата в «Мои обращения» — не «қаз»/«10 қаз»`, !/\bқаз\b/.test(date) && /\u00a0/.test(date), date);
  const code = await page.$eval(".bc-mine__card .bc-nowrap", (c) => c.getClientRects().length);
  check(`${tag}: номер обращения в «Мои обращения» не рвётся на две строки`, code === 1, String(code));
  await shot(page, `${tag}-mine`);
  check(`${tag}: нет ключей и технических слов`, (await visibleKeys(page)).length === 0);
  check(`${tag}: нет ошибок консоли`, page.problems.filter((p) => !/Failed to load resource|ERR_FAILED/.test(p)).length === 0,
        page.problems.join(" | "));
  await page.context().close();
}

// LOCAL_FINAL №1 (Codex, Windows): сотрудник вошёл раньше жителя в том же браузере -> ответы API для сотрудника
// (без поля reporters) -> мастер пропускал шаг «Я тоже» и создавал новую жалобу. Стенд: cookie stand_staff=1.
async function staffFirst(browser, base, hot, lang, width, height, tag) {
  const page = await newPage(browser, base, width, height, lang, { staff: true });
  const staffSeen = await page.evaluate(async (id) => {
    const r = await fetch("/api/civic/v2/complaints/" + id); return (await r.json()).data.complaint;
  }, hot.complaint_id);
  check(`${tag}: сессия сотрудника активна (ответ API — для сотрудника)`, staffSeen && "text" in staffSeen,
        staffSeen ? Object.keys(staffSeen).slice(0, 6).join(",") : "");
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']");
  await clickMapAt(page, hot.point);
  await page.waitForSelector(".bc-option--first", { timeout: 8000 });
  await page.click(".bc-option--first");
  await page.waitForSelector(".bc-panel[data-step='3']");
  await page.fill("#bc-text", lang === "kk" ? "Аялдаманың павильоны сынған, шатыры жоқ" : "Павильон остановки сломан, нет крыши");
  await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 6000 });
  await page.click(".bc-send");
  const step = await page.waitForSelector(".bc-panel[data-step='4'], .bc-panel[data-step='5']", { timeout: 10000 })
    .then(async (el) => (await el.getAttribute("data-step")) + ((await el.getAttribute("data-review")) ? "-review" : ""));
  const title = await page.textContent(".bc-title");
  check(`${tag}: [LOCAL-1] при входе сотрудника шаг «Я тоже» не пропущен`, step === "4" && /\d/.test(title), `шаг ${step}: ${title}`);
  check(`${tag}: [LOCAL-1] текст чужой жалобы жителю не показан и при входе сотрудника`,
        !(await page.textContent(".bc-panel")).includes("нет крыши") || !!(await page.$("#bc-text")));
  await shot(page, `${tag}-similar`);
  check(`${tag}: нет ошибок консоли`, page.problems.length === 0, page.problems.join(" | "));
  await page.context().close();
}

// LOCAL_FINAL №2: «У меня другое» -> успех -> сразу Escape. Отложенная подсказка /classify (таймер шага ③) читала
// state уже после закрытия: «Cannot read properties of null (reading 'text')».
async function quickClose(browser, base, hot, lang, width, height, tag) {
  const page = await newPage(browser, base, width, height, lang);
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']");
  await clickMapAt(page, hot.point);
  await page.waitForSelector(".bc-option--first", { timeout: 8000 });
  await page.click(".bc-option--first");
  await page.waitForSelector(".bc-panel[data-step='3']");
  await page.fill("#bc-text", lang === "kk" ? "Аялдаманың павильоны сынған, шатыры жоқ" : "Павильон остановки сломан, нет крыши");
  await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 6000 });
  await page.click(".bc-send");
  await page.waitForSelector(".bc-panel[data-step='4']:not([data-review])", { timeout: 10000 });
  await page.click(".bc-different");
  await sendFromReview(page);
  for (const how of ["escape"]) {
    await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 10000 });
    if (how === "escape") await page.keyboard.press("Escape");
  }
  await page.waitForTimeout(2500);   // дольше таймера подсказки (0,7 с) и ответа /classify
  const nullErrors = page.problems.filter((p) => /null|undefined|TypeError/.test(p));
  check(`${tag}: [LOCAL-2] после быстрого закрытия нет ошибок JavaScript`, nullErrors.length === 0, nullErrors.join(" | "));
  check(`${tag}: панель закрыта, главная кнопка видна`, (await page.isHidden(".bc-panel")) && (await page.isVisible(".bc-fab")));
  // То же сразу после «Я тоже» и после закрытия с шага ③ во время ожидания подсказки.
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']");
  await clickMapAt(page, hot.point);
  await page.waitForSelector(".bc-option--first", { timeout: 8000 });
  await page.click(".bc-option--first");
  await page.fill("#bc-text", "Павильон сломан, крыши нет совсем");
  await page.keyboard.press("Escape");                          // закрыли, пока таймер подсказки ещё идёт
  await page.waitForTimeout(2000);
  const late = page.problems.filter((p) => /null|undefined|TypeError/.test(p));
  check(`${tag}: [LOCAL-2] закрытие во время подсказки модели без ошибок`, late.length === 0, late.join(" | "));
  await page.context().close();
}

// ---------------------------------------------------------------- волна 1–2 (POLISH_WAVE_2)
// Фото «как с телефона»: JPEG 2400×1800 с сегментом APP1 «Exif» и меткой GPS сразу после SOI.
async function exifJpeg(page, width, height) {
  const b64 = await page.evaluate(async ([w, h]) => {
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const g = c.getContext("2d"); g.fillStyle = "#7aa35c"; g.fillRect(0, 0, w, h); g.fillStyle = "#2c3e50"; g.fillRect(w / 4, h / 4, w / 2, h / 2);
    const blob = await new Promise((ok) => c.toBlob(ok, "image/jpeg", 0.9));
    const src = new Uint8Array(await blob.arrayBuffer());
    const payload = new TextEncoder().encode("Exif\0\0GPSLatitude=51.1283;GPSLongitude=71.4305;R09-SECRET-GPS");
    const app1 = new Uint8Array(4 + payload.length);
    app1.set([0xFF, 0xE1, (payload.length + 2) >> 8, (payload.length + 2) & 255]); app1.set(payload, 4);
    const out = new Uint8Array(src.length + app1.length);
    out.set(src.slice(0, 2)); out.set(app1, 2); out.set(src.slice(2), 2 + app1.length);
    let s = ""; for (let i = 0; i < out.length; i += 0x8000) s += String.fromCharCode.apply(null, out.subarray(i, i + 0x8000));
    return btoa(s);
  }, [width, height]);
  return Buffer.from(b64, "base64");
}

// Размер JPEG по маркеру SOF0/SOF2 (без библиотек).
function jpegSize(buf) {
  let i = 2;
  while (i + 9 < buf.length) {
    if (buf[i] !== 0xFF) return null;
    const marker = buf[i + 1], len = buf.readUInt16BE(i + 2);
    if (marker === 0xC0 || marker === 0xC2) return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) };
    i += 2 + len;
  }
  return null;
}

const staffApi = async (base, method, p, body) => (await fetch(base + "/api/civic/v2" + p, { method,
  headers: { "Content-Type": "application/json", "Cookie": "stand_staff=1", "X-CSRF-Token": "stand" },
  body: body ? JSON.stringify(body) : undefined })).json();
const deviceApi = async (base, method, p, body, device) => (await fetch(base + "/api/civic/v2" + p, { method,
  headers: { "Content-Type": "application/json", "X-Birge-Device": device }, body: body ? JSON.stringify(body) : undefined })).json();

// Карта по умолчанию не сложнее (защита от перегруза, п. 1): до открытия мастера — ни одного слоя R09 и
// из элементов R09 на экране только кнопка «Сообщить о проблеме».
async function defaultMapUnchanged(page, tag) {
  const seen = await page.evaluate(() => ({
    layers: window.standMap.getStyle().layers.map((l) => l.id).filter((id) => /^bc-/.test(id)),
    visible: [...document.querySelectorAll("[class*='bc-']")].filter((n) => !n.closest(".bc-fab") && n.getClientRects().length &&
      getComputedStyle(n).visibility !== "hidden" && !n.hidden && !n.closest("[hidden]"))
      .map((n) => n.className).filter((c) => !/bc-fab/.test(c)) }));
  check(`${tag}: [защита п.1] карта по умолчанию — без новых слоёв, на экране только кнопка R09`,
        seen.layers.length === 0 && seen.visible.length === 0 && await page.isVisible(".bc-fab"), JSON.stringify(seen));
}

async function waveWizard(browser, base, lang, width, height, tag, point) {
  const page = await newPage(browser, base, width, height, lang);
  await defaultMapUnchanged(page, tag);
  // Сезонный порядок (волна 1, п. 11): ноябрь–март — снег и гололёд первыми, апрель–октябрь — дороги.
  const season = await page.evaluate(() => { const first = (ms) => BirgeComplaint.seasonalCategories(ms)[0].id;
    return { jan: first(Date.UTC(2026, 0, 15, 6)), mar: first(Date.UTC(2026, 2, 31, 6)), apr: first(Date.UTC(2026, 3, 1, 6)),
             jul: first(Date.UTC(2026, 6, 15, 6)), nov: first(Date.UTC(2026, 10, 1, 6)), n: BirgeComplaint.seasonalCategories(Date.now()).length }; });
  check(`${tag}: [W1-11] сезонный порядок категорий`, season.jan === "snow_ice" && season.mar === "snow_ice" && season.nov === "snow_ice" &&
        season.apr === "roads" && season.jul === "roads" && season.n === 12, JSON.stringify(season));
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']");
  await clickMapAt(page, point);
  await page.waitForSelector(".bc-panel[data-step='3'], .bc-option", { timeout: 8000 });
  if (await page.$(".bc-option")) await page.click(".bc-option.bk-btn--ghost, .bc-option:has-text('Примерн'), .bc-option:has-text('Шамамен')");
  await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
  // «Газон» — не газ: срочного баннера нет.
  await page.fill("#bc-text", lang === "kk" ? "Подъезд алдындағы газон бұзылған" : "У подъезда разбит газон");
  await page.waitForTimeout(300);
  check(`${tag}: [W1-3] «газон» не вызывает баннер про газ`, !(await page.$(".bc-emergency")));
  if (!(await page.$(".bk-catgrid"))) await page.click(".bc-change");
  const first = await page.$eval(".bk-catgrid > button", (b) => b.textContent.trim());
  check(`${tag}: [W1-11] в октябре первая в сетке — «Дороги»`, lang === "kk" ? /Жол/.test(first) : /Дорог/.test(first), first);
  // Срочный случай до отправки (волна 1, п. 3): «Звоните 104 сейчас», ссылка tel:, отправить всё равно можно.
  await page.fill("#bc-text", lang === "kk" ? "Подъезде газ иісі шығып тұр" : "В подъезде сильно пахнет газом");
  await page.waitForSelector(".bc-emergency", { timeout: 3000 });
  const banner = await page.$eval(".bc-emergency", (b) => { const a = b.querySelector("a"); const r = a.getBoundingClientRect();
    return { role: b.getAttribute("role"), href: a.getAttribute("href"), h: Math.round(r.height), text: b.textContent,
             danger: b.classList.contains("bk-banner--danger") }; });
  check(`${tag}: [W1-3] баннер «Это может быть опасно. Звоните 104 сейчас», кнопка tel:104 ≥ 44 px`,
        banner.role === "alert" && banner.href === "tel:104" && banner.h >= 44 && banner.danger &&
        (lang === "kk" ? /104/.test(banner.text) : /опасно/.test(banner.text) && /Звоните 104 сейчас/.test(banner.text)), JSON.stringify(banner));
  // Категория «Запахи и воздух» и уточнение «Запах газа» одним нажатием (волна 1, п. 2).
  await page.waitForTimeout(1200);   // подсказка модели по новому тексту успела прийти
  if (!(await page.$(".bk-catgrid"))) await page.click(".bc-change");
  await page.click(".bk-catgrid > button[data-category='smell_air']");
  await page.waitForSelector(".bc-subtopic[data-subtopic='gas']", { timeout: 3000 });
  const subs = await page.$$eval(".bc-subtopic", (n) => n.map((x) => x.dataset.subtopic));
  const noneFirst = await page.$eval(".bc-subtopic[data-subtopic='']", (b) => ({ pressed: b.getAttribute("aria-pressed"), text: b.textContent.trim() }));
  await page.click(".bc-subtopic[data-subtopic='gas']");
  const pressed = await page.$eval(".bc-subtopic[data-subtopic='gas']", (b) => b.getAttribute("aria-pressed"));
  const noneAfter = await page.$eval(".bc-subtopic[data-subtopic='']", (b) => b.getAttribute("aria-pressed"));
  check(`${tag}: [W1-2] уточнения чипами (4 + «${noneFirst.text}» последним), выбор одним нажатием`,
        subs.length === 5 && subs[4] === "" && noneFirst.pressed === "true" && pressed === "true" && noneAfter === "false" &&
        (lang === "kk" ? noneFirst.text === "Нақтылаусыз" : noneFirst.text === "Без уточнения"), subs.join());
  // Фото (волна 1, п. 5): до 3, уменьшается до 1600 px, EXIF/GPS не уходит; подпись «увидит только служба».
  const jpeg = await exifJpeg(page, 2400, 1800);
  await page.setInputFiles("#bc-photo-input", { name: "IMG_0001.jpg", mimeType: "image/jpeg", buffer: jpeg });
  await page.waitForSelector(".bc-photos .bc-thumb img", { timeout: 8000 });
  const photoUi = await page.evaluate(() => ({ thumbs: document.querySelectorAll(".bc-photos .bc-thumb").length,
    add: (document.querySelector(".bc-photo-add") || {}).textContent || "", hint: [...document.querySelectorAll(".bc-photos .bc-meta")].map((n) => n.textContent).join() }));
  check(`${tag}: [W1-5] фото добавлено: миниатюра, счётчик «1 из 3», «увидит только служба»`,
        photoUi.thumbs === 1 && /1/.test(photoUi.add) && (lang === "kk" ? /қызметкер/.test(photoUi.hint) : /только сотрудники/.test(photoUi.hint)), JSON.stringify(photoUi));
  const sizes = await uxSizes(page);
  check(`${tag}: [UX] шаг 3 с баннером, уточнением и фото — текст ≥ 13 px, кнопки ≥ 44 px`, sizes.length === 0, sizes.join("; "));
  const primaries = await page.$$eval(".bc-panel .bk-btn--primary", (n) => n.map((b) => b.className));
  check(`${tag}: [защита п.4, UX_SPEC §10] одна главная кнопка — звонок 104, «Далее» второстепенная`,
        primaries.length === 1 && /bc-emergency__call/.test(primaries[0]), primaries.join(" | "));
  await shot(page, `${tag}-3-emergency-photo`);
  await page.click(".bc-send");
  const similarFirst = await page.waitForSelector(".bc-panel[data-review='1'], .bc-different", { timeout: 10000 })
    .then(async (el) => (await el.getAttribute("class")).includes("bc-different"));
  if (similarFirst) await page.click(".bc-different");
  await page.waitForSelector(".bc-panel[data-review='1']");
  const review = await page.evaluate(() => ({ what: document.querySelector(".bc-review__row:nth-child(2) dd").textContent,
    thumbs: document.querySelectorAll(".bc-review .bc-thumb").length, emergency: !!document.querySelector(".bc-panel .bc-emergency a[href='tel:104']") }));
  check(`${tag}: [W2] проверка: «Запах · Запах газа», фото и баннер 104 видны перед отправкой`,
        review.thumbs === 1 && review.emergency && review.what.includes("·"), JSON.stringify(review));
  await shot(page, `${tag}-review`);
  await sendFromReview(page);
  await page.waitForSelector(".bc-code__value", { timeout: 20000 });
  const code = (await page.textContent(".bc-code__value")).trim();
  const created = await page.evaluate(() => (window.standEvents || []).filter((e) => e.type === "created").pop());
  const staff = (await staffApi(base, "GET", "/complaints/" + created.complaint_id)).data.complaint;
  check(`${tag}: [W1-2/W1-3] запись: subtopic=gas, баннер 104 был показан`, staff.subtopic === "gas" &&
        staff.emergency && staff.emergency.phone === "104" && staff.emergency.banner_shown === true, JSON.stringify({ s: staff.subtopic, e: staff.emergency }));
  const photoMeta = (staff.photos || [])[0];
  const got = photoMeta ? (await staffApi(base, "GET", `/complaints/${staff.id}/photos/${photoMeta.id}`)).data : null;
  const bytes = got ? Buffer.from(got.photo.data_url.split(",")[1], "base64") : Buffer.alloc(0);
  const dims = jpegSize(bytes);
  check(`${tag}: [W1-5] у акимата фото без EXIF/GPS, уменьшено до ≤ 1600 px (${dims && dims.w}×${dims && dims.h})`,
        staff.photos.length === 1 && bytes.length > 1000 && bytes[0] === 0xFF && bytes[1] === 0xD8 &&
        !bytes.includes(Buffer.from("R09-SECRET-GPS")) && !bytes.includes(Buffer.from("Exif")) &&
        dims && Math.max(dims.w, dims.h) <= 1600 && Math.max(dims.w, dims.h) >= 1500, JSON.stringify({ n: staff.photos.length, len: bytes.length, dims }));
  const other = await deviceApi(base, "GET", `/complaints/${staff.id}/photos/${photoMeta && photoMeta.id}`, null, "dev-r09-wave-stranger-01");
  const pub = await deviceApi(base, "GET", `/complaints/${staff.id}`, null, "dev-r09-wave-stranger-01");
  check(`${tag}: [W1-5] чужой житель фото не получает, в публичной записи нет фото и текста`,
        other.ok === false && pub.data && !("photos" in pub.data.complaint) && !("text" in pub.data.complaint), JSON.stringify(other.error || other).slice(0, 120));
  check(`${tag}: номер ${code} показан после отправки`, /^B-\d{4,}$/.test(code), code);
  check(`${tag}: нет ключей и технических слов`, (await visibleKeys(page)).length === 0);
  check(`${tag}: нет горизонтальной прокрутки`, await noHorizontalScroll(page));
  check(`${tag}: нет ошибок консоли`, page.problems.length === 0, page.problems.join(" | "));
  await page.context().close();
}

// Черновик на устройстве (волна 1, п. 10): закрыли вкладку — текст и категория вернулись при следующем открытии.
async function draftSurvives(browser, base, lang, tag, point) {
  const page = await newPage(browser, base, 375, 812, lang);
  await page.click(".bc-fab");
  await clickMapAt(page, point);
  await page.waitForSelector(".bc-panel[data-step='3'], .bc-option", { timeout: 8000 });
  if (await page.$(".bc-option")) await page.click(".bc-option.bk-btn--ghost, .bc-option:has-text('Примерн'), .bc-option:has-text('Шамамен')");
  await page.waitForSelector(".bc-panel[data-step='3']");
  const text = lang === "kk" ? "Аулада қоқыс жәшіктері толып кеткен" : "Во дворе переполнены мусорные баки";
  await page.fill("#bc-text", text);
  await page.waitForTimeout(300);
  await page.reload();
  await page.waitForFunction(() => document.documentElement.getAttribute("data-map-ready") === "1", null, { timeout: 15000 });
  await page.click(".bc-fab");
  await clickMapAt(page, point);
  await page.waitForSelector(".bc-panel[data-step='3'], .bc-option", { timeout: 8000 });
  if (await page.$(".bc-option")) await page.click(".bc-option.bk-btn--ghost, .bc-option:has-text('Примерн'), .bc-option:has-text('Шамамен')");
  await page.waitForSelector(".bc-panel[data-step='3']");
  const restored = await page.inputValue("#bc-text");
  check(`${tag}: [W1-10] черновик пережил перезагрузку страницы`, restored === text, restored);
  // Нет сети совсем (navigator.onLine=false): очередь, затем сеть вернулась — отправка сама, без нажатий.
  await page.waitForSelector(".bc-send:not([disabled])", { timeout: 8000 });
  await page.click(".bc-send");
  const viaSimilar = await page.waitForSelector(".bc-panel[data-review='1'], .bc-different", { timeout: 10000 })
    .then(async (el) => (await el.getAttribute("class")).includes("bc-different"));
  if (viaSimilar) await page.click(".bc-different");
  await page.waitForSelector(".bc-panel[data-review='1'] .bc-send:not([disabled])");
  await page.context().setOffline(true);
  await page.click(".bc-panel[data-review='1'] .bc-send");
  await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 15000 });
  const queuedTitle = (await page.textContent(".bc-title")).trim();
  await page.context().setOffline(false);
  const code = await page.waitForSelector(".bc-code__value", { timeout: 20000 }).then((e) => e.textContent(), () => "");
  const toast = await page.textContent(".bc-toast").catch(() => "");
  check(`${tag}: [W1-10] «${queuedTitle}» → сеть вернулась → отправлено само (${code})`,
        /^B-\d{4,}$/.test((code || "").trim()) && (lang === "kk" ? /жіберілді/.test(toast) : /отправлено/.test(toast)), toast);
  check(`${tag}: черновик очищен после отправки`, await page.evaluate(() => !localStorage.getItem("birge.complaint.draft")));
  check(`${tag}: нет ошибок консоли`, page.problems.filter((p) => !/Failed to load resource|ERR_|net::/.test(p)).length === 0, page.problems.join(" | "));
  await page.context().close();
}

// Центральная сцена волны 2: служба сообщила «исправлено» (что сделали + фото «после») -> «Я тоже» говорит
// «Проблема осталась» -> та же карточка снова в работе -> служба исправила ещё раз -> автор: «Да, исправлено».
// Паспорт решения и одно обновление доходят до обоих; у автора — «Что изменилось» и ссылка на конкретную жалобу.
async function centralScene(browser, base, lang, width, height, tag, point) {
  const suffix = tag.replace(/[^a-z0-9]/gi, "").toLowerCase();
  const devA = "dev-r09-wave-author-" + suffix, devB = "dev-r09-wave-metoo-" + suffix;
  const text = lang === "kk" ? "Аулада кешке шамдар жанбайды" : "Во дворе вечером не горят фонари";
  const a = await deviceApi(base, "POST", "/complaints", { text, category: "lighting", subtopic: "lamp_off", point,
    target: { kind: "object", id: "osm-node-1" } }, devA);
  const id = a.data.complaint.id, code = a.data.complaint.code;
  const joined = await deviceApi(base, "POST", `/complaints/${id}/metoo`, {}, devB);
  check(`${tag}: автор и «Я тоже» — 2 человека`, joined.data && joined.data.complaint.reporters === 2, JSON.stringify(joined.data && joined.data.result));
  // Автор открыл «Мои обращения» до действий службы: дальше «Что изменилось» считается от этого момента.
  const pageA = await newPage(browser, base, width, height, lang, { device: devA });
  await pageA.evaluate(() => window.standUi.openMine());
  await pageA.waitForSelector(".bc-mine__card");
  const first = await pageA.evaluate(() => ({ changes: document.querySelectorAll(".bc-changes").length,
    line: (document.querySelector(".bc-mine__card .bc-assignee") || {}).textContent || "",
    due: (document.querySelector(".bc-mine__card .bc-mine__due") || {}).textContent || "",
    primaries: document.querySelectorAll(".bc-panel .bk-btn--primary").length }));
  // Эталон A (строка статуса карточки .st): срок — справа мелко рядом со статусом, «Передано: служба» — под словом.
  check(`${tag}: первый визит — без «Что изменилось»; на карточке «${first.line}» и срок «${first.due}»; главной кнопки нет`,
        first.changes === 0 && first.primaries === 0 &&
        (lang === "kk" ? first.line === "Жауапты: Жарықтандыру қызметі" && /^\d+ жұмыс күні қалды$/.test(first.due)
                       : first.line === "Передано: Служба освещения" && /^Осталось \d+ рабоч(ий день|их дня|их дней)$/.test(first.due)), JSON.stringify(first));
  await pageA.keyboard.press("Escape");

  // Сотрудник: компонент complaint-staff.js в карточке (как встроят R07 и «Обращения» акимата).
  const staff = await newPage(browser, base, width, height, lang, { staff: true });
  await staff.evaluate((cid) => {
    const box = document.createElement("div");
    box.id = "staff-box";
    box.style.cssText = "position:fixed;inset:0;overflow:auto;background:#fff;z-index:50;padding:16px;max-width:480px";
    document.body.appendChild(box);
    window.staffCtl = BirgeComplaintStaff.mount(box, { complaintId: cid, csrf: "stand" });
  }, id);
  await staff.waitForSelector(".bc-staff__summary", { timeout: 8000 });
  // R11 §2.3: «Отметить исправленным» открывает форму в той же карточке; до действия видно «Увидят N человек».
  const willSee = (await staff.textContent(".bc-staff .bc-staff__open-fix + .bc-meta")).trim();
  const staffPrim = await staff.$$eval("#staff-box .bk-btn--primary", (n) => n.map((b) => b.textContent.trim()));
  const formHidden = !(await staff.$("[name=what_done]"));
  check(`${tag}: [W2-1/§2.3] «${staffPrim[0]}» — одна главная кнопка, форма свёрнута, «${willSee}»`,
        /2/.test(willSee) && staffPrim.length === 1 && formHidden &&
        staffPrim[0] === (lang === "kk" ? "Түзетілді деп белгілеу" : "Отметить исправленным"), staffPrim.join(" | "));
  // Паспорт: «Изменить» → 3 поля (кто отвечает, следующий шаг, ориентир), без полей задержки.
  await staff.click(".bc-staff__edit");
  const fields = await staff.$$eval(".bc-staff__passport-form [name]", (n) => n.map((x) => x.name));
  check(`${tag}: [W2-2/§2.3] паспорт — 3 поля, поля задержки скрыты`, fields.join() === "service,next_step,fix_eta", fields.join());
  const options = await staff.$$eval("[name=service] option", (n) => n.length);
  await staff.fill("[name=next_step]", lang === "kk" ? "Тіректердегі шамдарды ауыстыру" : "Заменить лампы на опорах");
  await staff.fill("[name=fix_eta]", "2026-10-20");
  await staff.click(".bc-staff__passport-form button[type=submit]");
  await staff.waitForSelector(".bc-staff__edit", { timeout: 8000 });
  const notePassport = (await staff.textContent(".bc-staff__note")).trim();
  // Служба задержалась (причина и дата обновления пришли раньше) — «Изменить» показывает ещё 3 поля.
  await staffApi(base, "POST", `/complaints/${id}/passport`, { delay_reason: lang === "kk" ? "Көтергіш күтілуде" : "Ждём подъёмник",
                                                              next_update_at: "2026-10-16" });
  await staff.evaluate(() => window.staffCtl.refresh());
  await staff.waitForSelector(".bc-staff__edit");
  await staff.click(".bc-staff__edit");
  const delayFields = await staff.$$eval(".bc-staff__passport-form [name]", (n) => n.map((x) => x.name + (x.required ? "*" : "")));
  check(`${tag}: [W2-2/§2.3] при задержке — ещё причина, мера, дата обновления (обязательна) · служб ${options - 1}`,
        delayFields.join().startsWith("service,next_step,fix_eta,delay_reason,temp_measure,next_update_at*,needs_decision") && options === 21,
        delayFields.join());
  await staff.fill("[name=temp_measure]", lang === "kk" ? "Уақытша шам қойылды" : "Поставили временный фонарь");
  // R08 «Нужно решение акима» (волна 2 п. 5): отметка открывает 2 варианта и «что нужно от акима».
  const hiddenBefore = await staff.$eval(".bc-staff__decision", (n) => n.hidden);
  await staff.check("[name=needs_decision]");
  await staff.fill("[name=option_1]", lang === "kk" ? "Әкімдік есебінен ауыстыру" : "Заменить за счёт акимата");
  await staff.fill("[name=option_2]", lang === "kk" ? "Электр желілеріне беру" : "Передать электросетям");
  await staff.fill("[name=decision]", lang === "kk" ? "Кім төлейтінін таңдау" : "Выбрать, кто платит");
  await staff.click(".bc-staff__passport-form button[type=submit]");
  await staff.waitForSelector(".bc-staff__edit", { timeout: 8000 });
  const decided = (await staff.textContent(".bc-staff .bc-passport")).replace(/\s+/g, " ");
  const stored = (await staffApi(base, "GET", `/complaints/${id}`)).data.complaint.passport.delay;
  check(`${tag}: [R08 п.5] «Нужно решение руководителя»: поля скрыты до отметки, 2 варианта и «что нужно» сохранены`,
        hiddenBefore && stored.needs_decision === true && stored.options.length === 2 && !!stored.decision &&
        (lang === "kk" ? /Әкімнің шешімі керек/.test(decided) && /1-нұсқа/.test(decided) : /Нужно решение акима/.test(decided) && /Вариант 2: Передать электросетям/.test(decided)),
        decided.slice(0, 160));
  await staff.fill("[name=text]", lang === "kk" ? "Көтергіш сәрсенбіде келеді" : "Подъёмник приедет в среду");
  await staff.click(".bc-staff__broadcast button[type=submit]");
  await staff.waitForFunction(() => !document.querySelector("[name=text]").value, null, { timeout: 8000 });
  const noteUpdate = (await staff.textContent(".bc-staff__note")).trim();
  check(`${tag}: [W2-2/W2-3] паспорт и одно обновление — «${noteUpdate}»`, /2/.test(notePassport) && /2/.test(noteUpdate), notePassport + " | " + noteUpdate);
  // «Сообщить жителям» без строки «что сделали» — подсказка, не отправка.
  await staff.click(".bc-staff__open-fix");
  await staff.waitForSelector(".bc-staff__fix [name=what_done]");
  const fixPrim = await staff.$$eval("#staff-box .bk-btn--primary", (n) => n.map((b) => b.textContent.trim()));
  check(`${tag}: [§2.3] в открытой форме главная — «${fixPrim[0]}»`, fixPrim.length === 1 &&
        fixPrim[0] === (lang === "kk" ? "Тұрғындарға хабарлау" : "Сообщить жителям"), fixPrim.join(" | "));
  await staff.click(".bc-staff__fix button[type=submit]");
  const blocked = await staff.evaluate(() => document.querySelector("[name=what_done]").validity.valueMissing &&
    document.querySelector("[name=what_done]").maxLength === 120);
  check(`${tag}: [W2-1] без «что сделали» (≤ 120 знаков) сообщить нельзя`, blocked);
  await staff.fill("[name=what_done]", lang === "kk" ? "4 шам ауыстырылды" : "Заменили 4 лампы");
  await staff.setInputFiles(".bc-staff .bc-photo-input", { name: "after.jpg", mimeType: "image/jpeg", buffer: await exifJpeg(staff, 1200, 900) });
  await staff.waitForSelector(".bc-staff .bc-thumb img", { timeout: 8000 });
  await shot(staff, `${tag}-staff`);
  await staff.click(".bc-staff__fix button[type=submit]");
  await staff.waitForFunction(() => !document.querySelector("[name=what_done]"), null, { timeout: 15000 });
  let pub = (await deviceApi(base, "GET", `/complaints/${id}`, null, "dev-r09-wave-stranger-02")).data.complaint;
  check(`${tag}: [W2-1] карта: «служба сообщила» = reported_fixed (пунктир), ещё не «проверено»`,
        pub.status === "fixed" && pub.heat_state === "reported_fixed" && pub.resolution.state === "reported", JSON.stringify(pub.resolution));

  // «Я тоже» отвечает: «Проблема осталась» -> та же карточка снова в работе.
  const pageB = await newPage(browser, base, width, height, lang, { device: devB });
  await pageB.evaluate(() => window.standUi.openMine());
  await pageB.waitForSelector(".bc-wait .bc-verify", { timeout: 8000 });
  // Эталон A, телефон: строка «✓ … · проверьте» для шторки «Рядом с вами» — те же данные, что «Ждут вашей проверки».
  // (у подписки «Я тоже» своего номера нет — code пустой; open() тогда открывает «Мои обращения» без выделения)
  const waiting = await pageB.evaluate(async () => (await window.standUi.waitingChecks()).map((x) => [x.id, x.place, x.status, typeof x.open]));
  check(`${tag}: [эталон A] waitingChecks() для «Рядом с вами» — ${waiting.length}`, waiting.length >= 1 &&
        waiting.every((x) => x[0] && x[1] && x[2] === "reported_fixed" && x[3] === "function"), JSON.stringify(waiting));
  const verifyB = await pageB.evaluate(() => ({ title: document.querySelector(".bc-wait h3").textContent.trim(),
    what: document.querySelector(".bc-wait").textContent,
    buttons: [...document.querySelectorAll(".bc-wait .bc-verify__buttons button")].map((b) => b.textContent.trim()),
    after: document.querySelectorAll(".bc-wait .bc-thumb").length,
    badge: (document.querySelector(".bc-mine__card .bk-status") || {}).textContent || "",
    // Лента статусов (дизайн-марафон): последний пункт — следующий этап серым («Проверено жителями» ещё впереди).
    lastStep: (document.querySelector(".bc-mine__card .bc-timeline__item:last-child") || { dataset: {} }).dataset.state }));
  check(`${tag}: [W2-1] «${verifyB.title}»: что сделали, фото «после», 3 ответа; статус «${verifyB.badge}»`,
        verifyB.buttons.length === 3 && (lang === "kk" ? /4 шам/.test(verifyB.what) && verifyB.badge === "Қызмет түзетілгенін хабарлады"
          : /Что сделали: Заменили 4 лампы/.test(verifyB.what) && verifyB.badge === "Служба сообщила об устранении") && verifyB.after === 1 &&
        verifyB.lastStep === "next",   // «Проверено жителями» не пройдено, пока жители не проверили
        JSON.stringify(verifyB));
  await pageB.waitForFunction(() => [...document.querySelectorAll(".bc-wait .bc-thumb img")].every((i) => i.src.startsWith("data:image/")), null, { timeout: 8000 })
    .catch(() => {});
  await shot(pageB, `${tag}-verify`);
  await pageB.click(".bc-wait .bc-verify__no");
  await pageB.waitForSelector(".bc-mine__card .bk-status[data-status='reopened']", { timeout: 8000 });
  pub = (await deviceApi(base, "GET", `/complaints/${id}`, null, "dev-r09-wave-stranger-02")).data.complaint;
  const eventsB = await pageB.evaluate(() => (window.standEvents || []).map((e) => e.type));
  check(`${tag}: [W2-1] «Проблема осталась» — снова в работе, heat_state=reopened, событие для карты`,
        pub.status === "in_progress" && pub.heat_state === "reopened" && pub.resolution.reopen_count === 1 && eventsB.includes("reopened"),
        JSON.stringify({ s: pub.status, h: pub.heat_state, e: eventsB }));
  const card = await pageB.evaluate(() => ({ line: (document.querySelector(".bc-mine__card .bc-assignee") || {}).textContent || "",
    delay: (document.querySelector(".bc-mine__card .bc-delay") || {}).textContent || "" }));
  check(`${tag}: [W1-7/§2.2] «${card.line}» и баннер задержки «${card.delay.slice(0, 60)}…»`,
        (lang === "kk" ? card.line === "Жауапты: Жарықтандыру қызметі" && /Себебі: Көтергіш күтілуде/.test(card.delay)
                       : card.line === "Передано: Служба освещения" && /Причина: Ждём подъёмник/.test(card.delay) && /Временная мера/.test(card.delay)),
        JSON.stringify(card));
  await shot(pageB, `${tag}-reopened`);
  // «Подписки (1)» → «Отписаться»: голос остаётся, обновления больше не приходят.
  await pageB.click(".bc-subs summary");
  await pageB.click(".bc-unsubscribe");
  await pageB.waitForSelector(".bc-panel .bk-empty", { timeout: 8000 });
  pub = (await deviceApi(base, "GET", `/complaints/${id}`, null, "dev-r09-wave-stranger-02")).data.complaint;
  check(`${tag}: [§2.1] «Отписаться» — карточка ушла из «Мои обращения», людей по-прежнему 2`, pub.reporters === 2, String(pub.reporters));
  check(`${tag}: нет ошибок консоли у «Я тоже»`, pageB.problems.length === 0, pageB.problems.join(" | "));
  await pageB.context().close();

  // Служба исправила ещё раз (раунд 2) — теперь обновление увидит только автор.
  await staff.evaluate(() => window.staffCtl.refresh());
  await staff.waitForSelector(".bc-staff__open-fix", { timeout: 8000 });
  const willSee2 = (await staff.textContent(".bc-staff .bc-staff__open-fix + .bc-meta")).trim();
  await staff.click(".bc-staff__open-fix");
  check(`${tag}: после «Отписаться» — «${willSee2}»`, /\b1\b/.test(willSee2), willSee2);
  await staff.fill("[name=what_done]", lang === "kk" ? "Тағы 2 шам ауыстырылды" : "Заменили ещё 2 лампы");
  await staff.click(".bc-staff__fix button[type=submit]");
  await staff.waitForFunction(() => !document.querySelector("[name=what_done]"), null, { timeout: 15000 });
  check(`${tag}: нет ошибок консоли у сотрудника`, staff.problems.length === 0, staff.problems.join(" | "));
  await staff.context().close();

  // Автор: значок новых изменений для меню R01, затем уведомление ведёт на конкретное изменение.
  const badge = await pageA.evaluate(() => window.standUi.changesCount());
  const feed = await deviceApi(base, "GET", "/complaints/changes", null, devA);
  const event = feed.data.items.find((i) => i.kind === "status" && i.status === "fixed") || feed.data.items[0];
  await pageA.goto(base + "/stand/#mine/event=" + event.id);
  await pageA.waitForFunction(() => document.documentElement.getAttribute("data-map-ready") === "1", null, { timeout: 15000 });
  await pageA.waitForSelector(".bc-mine__card--focus", { timeout: 8000 });
  const focus = await pageA.evaluate(() => ({ code: document.querySelector(".bc-mine__card--focus").dataset.code,
    open: !!document.querySelector(".bc-mine__card--focus details[open]"),
    row: (document.querySelector(".bc-changes__item--focus") || {}).dataset ? document.querySelector(".bc-changes__item--focus").dataset.event : null,
    lang: document.documentElement.lang }));
  check(`${tag}: [W2-10] значок «Мои обращения»: ${badge} новых изменений`, badge >= 4, String(badge));
  check(`${tag}: [W2] ссылка #mine/event=… — строка изменения подсвечена, карточка ${code} раскрыта, язык ${focus.lang} не сменился`,
        focus.code === code && focus.open && focus.row === event.id && focus.lang === lang, JSON.stringify(focus));
  await pageA.evaluate((l) => BirgeComplaint.setLang(l), lang);
  const mine = await pageA.evaluate(() => {
    const card = document.querySelector(".bc-mine__card--focus");
    return { changes: (document.querySelector(".bc-changes") || {}).textContent || "",
             items: document.querySelectorAll(".bc-changes__item").length,
             passport: [...card.querySelectorAll(".bc-passport li")].map((n) => n.textContent),
             updates: (card.querySelector(".bc-updates") || {}).textContent || "",
             history: [...card.querySelectorAll(".bc-history li")].map((n) => n.dataset.kind),
             primaries: [...document.querySelectorAll(".bc-panel .bk-btn--primary")].map((b) => b.className),
             open: !!card.querySelector("details[open]") };
  });
  check(`${tag}: [W2-10] «Что изменилось» — изменения с прошлого визита (≤ 3 строки + «Ещё N»)`,
        mine.items >= 1 && mine.items <= 3 + 10 && (lang === "kk" ? /Не өзгерді/.test(mine.changes) : /Что изменилось/.test(mine.changes)), mine.changes.slice(0, 200));
  const pl = mine.passport.join(" | ");
  check(`${tag}: [W2-2] паспорт: следующий шаг, ориентир 20 октября; карточка осталась раскрытой после смены языка`,
        mine.open && (lang === "kk" ? /Келесі қадам: Тіректердегі шамдарды ауыстыру/.test(pl) && /Түзету: шамамен 20/.test(pl)
                                    : /Следующий шаг: Заменить лампы на опорах/.test(pl) && /Устранение: ориентир 20/.test(pl)), pl);
  check(`${tag}: [W2-3] обновление службы и история видны автору`, lang === "kk" ? /сәрсенбіде/.test(mine.updates) : /Подъёмник приедет в среду/.test(mine.updates), mine.updates.slice(0, 200));
  check(`${tag}: [R10 W2-2] «История»: сообщили → … → служба сообщила → вернули → служба сообщила (${mine.history.length} шагов)`,
        mine.history[0] === "created" && mine.history.includes("reopened") && mine.history.filter((k) => k === "fixed").length === 2 &&
        mine.history.indexOf("reopened") > mine.history.indexOf("fixed"), mine.history.join(","));
  check(`${tag}: [защита п.4] на экране одна главная кнопка — «Да, исправлено» в «Ждут вашей проверки»`,
        mine.primaries.length === 1 && /bc-verify__yes/.test(mine.primaries[0]), mine.primaries.join(" | "));
  await shot(pageA, `${tag}-mine-changes`);
  await pageA.click(".bc-wait .bc-verify__yes");
  await pageA.waitForSelector(".bc-mine__card .bk-status[data-status='verified']", { timeout: 8000 });
  pub = (await deviceApi(base, "GET", `/complaints/${id}`, null, "dev-r09-wave-stranger-02")).data.complaint;
  check(`${tag}: [W2-1] автор «Да, исправлено» — verified_fixed (7 дней на карте), голос засчитан`,
        pub.status === "fixed" && pub.heat_state === "verified_fixed" && pub.resolution.state === "verified" && pub.resolution.votes.yes === 1 &&
        pub.resolution.round === 2, JSON.stringify(pub.resolution));
  const after = await pageA.evaluate(() => window.standUi.changesCount());
  check(`${tag}: значок погас после просмотра`, after === 0 || after === 1, String(after));   // 1 — своё «Проверено» после визита
  await shot(pageA, `${tag}-verified`);
  check(`${tag}: нет ключей и технических слов`, (await visibleKeys(pageA)).length === 0, (await visibleKeys(pageA)).join(", "));
  check(`${tag}: нет горизонтальной прокрутки`, await noHorizontalScroll(pageA));
  const sizes = await uxSizes(pageA);
  check(`${tag}: [UX] «Мои обращения» — текст ≥ 13 px, кнопки ≥ 44 px`, sizes.length === 0, sizes.join("; "));
  check(`${tag}: нет ошибок консоли`, pageA.problems.length === 0, pageA.problems.join(" | "));
  await pageA.context().close();
}

// Акимат · «Обращения» (complaint-list.js, раздел #complaints оболочки R01; R11 IA_WAVE2 §2.5).
async function inboxScreen(browser, base, lang, width, height, tag, point) {
  const suffix = tag.replace(/[^a-z0-9]/gi, "").toLowerCase();
  const made = await deviceApi(base, "POST", "/complaints", { text: lang === "kk" ? "Жолда үлкен шұңқыр" : "Большая яма на дороге",
    category: "roads", subtopic: "pothole", point, target: { kind: "object", id: "osm-node-1" } }, "dev-r09-inbox-" + suffix + "-0001");
  const tid = made.data.complaint.target.id;
  const page = await newPage(browser, base, width, height, lang, { staff: true });
  await page.evaluate(() => {
    window.CivicShell = { csrfToken: () => "stand" };   // в сборке токен даёт оболочка R01
    const box = document.createElement("div");
    box.id = "inbox-box";
    box.style.cssText = "position:fixed;inset:0;overflow:auto;background:#fff;z-index:50;padding:16px";
    document.body.appendChild(box);
    window.opened = null;
    window.inboxCtl = BirgeComplaintList.mount(box, { titleTag: "h2", openTarget: (kind, id) => { window.opened = [kind, id]; } });
  });
  await page.waitForSelector(".bc-inbox__tab", { timeout: 8000 });
  const tabs = await page.$$eval(".bc-inbox__tab", (n) => n.map((b) => ({ id: b.dataset.tab, text: b.textContent.trim(), sel: b.getAttribute("aria-selected") })));
  // Эталон A, правило 5 (Linear): фильтры-чипы «Все» + 5 вкладок §2.5; по умолчанию «Все» — группы по статусу.
  check(`${tag}: [§2.5, эталон п.5] фильтры ${tabs.map((x) => x.text).join(" · ")}`, tabs.map((x) => x.id).join() === "all,new,in_progress,waiting_check,overdue,reopened" &&
        tabs[0].sel === "true" && (lang === "kk" ? /^Барлығы \d+$/.test(tabs[0].text) : /^Все \d+$/.test(tabs[0].text)), JSON.stringify(tabs));
  const groupsSeen = await page.$$eval(".bc-inbox__group", (n) => n.map((g) => ({ id: g.dataset.group,
    head: g.querySelector(".bc-inbox__ghead").textContent.trim(), icon: !!g.querySelector(".bc-inbox__ghead .bc-sicon"),
    rows: [...g.querySelectorAll(".bc-inbox__row")].map((r) => Math.round(r.getBoundingClientRect().height)) })));
  check(`${tag}: [эталон п.5] группы по статусу со значком, строки плотные (≤ 44 на ноутбуке)`, groupsSeen.length >= 1 &&
        groupsSeen.every((g) => g.icon && g.rows.length) && (width < 700 || groupsSeen.every((g) => g.rows.every((hgt) => hgt >= 44 && hgt <= 46))),
        JSON.stringify(groupsSeen));
  const key = `${tid}|roads`;
  const row = await page.$(`.bc-inbox__row[data-key="${key}"]`);
  const rowText = row ? (await row.textContent()).replace(/\s+/g, " ") : "";
  check(`${tag}: [§2.5] строка: место · категория · уточнение · людей · срок — «${rowText.slice(0, 90)}»`, !!row &&
        (lang === "kk" ? /Жолдар · Шұңқыр/.test(rowText) && /1 адам/.test(rowText) && /жұмыс күні қалды/.test(rowText)
                       : /Дороги · Яма, разбитый асфальт/.test(rowText) && /1 человек/.test(rowText) && /Осталось \d+ рабоч/.test(rowText)), rowText);
  // (после проверки текста строки: взятое в работу уже «ответили» — строка «Осталось N дней» пропадает, это верно.)
  // Эталон п.4–5: смена статуса прямо из строки, с мгновенным откликом — строка переезжает в «В работе» до ответа
  // сервера (ответ здесь нарочно задержан на 1,5 с), потом статус на сервере тот же.
  await page.click(`.bc-inbox__status--btn[data-key="${key}"]`);
  await page.waitForSelector(".bc-inbox__menu .bc-inbox__menu-item", { timeout: 3000 });
  const menuItems = await page.$$eval(".bc-inbox__menu .bc-inbox__menu-item", (n) => n.map((b) => b.textContent.trim()));
  await page.route("**/complaints/*/status", async (r) => { await new Promise((res) => setTimeout(res, 1500)); await r.continue(); });
  await page.click(".bc-inbox__menu .bc-inbox__menu-item");
  const movedNow = await page.waitForFunction((k) => {
    const li = document.querySelector(`.bc-inbox__item[data-key="${k}"]`);
    return !!li && li.closest(".bc-inbox__group").dataset.group === "in_progress";
  }, key, { timeout: 400 }).then(() => true, () => false);
  check(`${tag}: [эталон п.4–5] «${menuItems[0]}» из строки — сразу в «В работе», до ответа сервера`,
        menuItems.length === 2 && movedNow && (lang === "kk" ? /Жұмысқа алу/.test(menuItems[0]) : /Взять в работу/.test(menuItems[0])), JSON.stringify(menuItems));
  await page.waitForTimeout(2200);
  await page.unroute("**/complaints/*/status");
  const afterTake = (await staffApi(base, "GET", `/complaints/${made.data.complaint.id}`)).data.complaint.status;
  check(`${tag}: [эталон п.4] после ответа — статус на сервере «в работе», строка там же`, afterTake === "in_progress" &&
        await page.$eval(`.bc-inbox__item[data-key="${key}"]`, (li) => li.closest(".bc-inbox__group").dataset.group) === "in_progress", afterTake);
  await page.click(`.bc-inbox__row[data-key="${key}"]`);
  await page.waitForSelector(".bc-inbox__detail .bc-staff__open-fix", { timeout: 8000 });
  const prim = await page.$$eval(".bc-inbox .bk-btn--primary", (n) => n.map((b) => b.textContent.trim()));
  check(`${tag}: [защита п.4] раскрыта одна группа, одна главная кнопка «${prim[0]}»`, prim.length === 1, prim.join(" | "));
  // Эталон п.2: команды для палитры Ctrl+K оболочки (R01) — «Отметить исправленным — место» для этой цели.
  const cmds = await page.evaluate(async () => (await window.BirgeComplaintList.commands()).map((c) => c.id + " " + c.title));
  check(`${tag}: [эталон п.2] команды палитры Ctrl+K (${cmds.length})`, cmds.some((x) => x.startsWith(`fix:${key} `) &&
        (lang === "kk" ? /Түзетілді деп белгілеу — /.test(x) : /Отметить исправленным — /.test(x))), cmds.slice(0, 3).join(" | "));
  await page.click(".bc-inbox__map");
  const opened = await page.evaluate(() => window.opened);
  check(`${tag}: «Показать на карте» — та же цель`, opened && opened[1] === tid, JSON.stringify(opened));
  const sizes = await page.evaluate(() => {
    const bad = [];
    document.querySelectorAll(".bc-inbox *").forEach((n) => {
      const r = n.getBoundingClientRect();
      if (!r.width || getComputedStyle(n).display === "none") return;
      const own = [...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
      if (own && parseFloat(getComputedStyle(n).fontSize) < 12) bad.push("text " + n.textContent.trim().slice(0, 24));
      // Зона нажатия — с ::after (кнопка статуса строки ui-kit .bk-lrow__st: значок 28, зона 44 через inset: -8px).
      const after = getComputedStyle(n, "::after");
      const grow = after.content && after.content !== "none" && after.position === "absolute" ? Math.max(0, -parseFloat(after.top) || 0) * 2 : 0;
      if (/^(BUTTON|A|INPUT|SELECT)$/.test(n.tagName) && r.height + grow < 44) bad.push("tap " + (n.name || n.textContent.trim().slice(0, 24)) + " " + Math.round(r.height + grow));
    });
    return bad;
  });
  check(`${tag}: [UX] «Обращения» — текст ≥ 12 px (эталон: мета 12), кнопки ≥ 44 px (с зоной ::after)`, sizes.length === 0, sizes.join("; "));
  // Вкладки — одним рядом с прокруткой внутри ряда (R11 разбор 5 №4в); страница вбок не прокручивается.
  const tabsRow = await page.$$eval(".bc-inbox__tab", (n) => new Set(n.map((b) => Math.round(b.getBoundingClientRect().top))).size);
  check(`${tag}: [R11 5 №4в] 5 вкладок одним рядом`, tabsRow === 1, String(tabsRow));
  check(`${tag}: нет горизонтальной прокрутки`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1 &&
        [...document.querySelectorAll(".bc-inbox *")].filter((n) => !n.closest(".bc-inbox__tabs"))
          .every((n) => { const r = n.getBoundingClientRect(); return !r.width || r.right <= innerWidth + 1; })));
  await shot(page, `${tag}-inbox`);
  // Сотрудник сообщает об устранении прямо из списка → группа уходит во «Ждут проверки».
  await page.click(".bc-inbox__detail .bc-staff__open-fix");
  await page.fill(".bc-inbox__detail [name=what_done]", lang === "kk" ? "Шұңқыр жамалды" : "Заделали яму");
  // R10 B-056: фото «после» под CSP сборки (connect-src 'self') и сбой загрузки — сообщение в форме, ничего не отмечено.
  await page.setInputFiles(".bc-inbox__detail .bc-photo-input", { name: "after.jpg", mimeType: "image/jpeg", buffer: await exifJpeg(page, 640, 480) });
  await page.waitForSelector(".bc-inbox__detail .bc-thumb img", { timeout: 8000 });
  await page.route("**/photos", (route) => route.abort());
  await page.click(".bc-inbox__detail .bc-staff__fix button[type=submit]");
  const failed = await page.waitForSelector(".bc-inbox__detail .bc-staff__fix-error", { timeout: 8000 }).then(async (e) => (await e.textContent()).trim(), () => "");
  const still = (await deviceApi(base, "GET", `/complaints/${made.data.complaint.id}`, null, "dev-r09-inbox-stranger-1")).data.complaint.status;
  const enabled = await page.$eval(".bc-inbox__detail .bc-staff__fix button[type=submit]", (b) => !b.disabled);
  check(`${tag}: [B-056] фото не загрузилось — «${failed.slice(0, 40)}…», кнопка доступна, обращение не отмечено`,
        (lang === "kk" ? /Фото жүктелмеді/.test(failed) : /Фото не загрузилось/.test(failed)) && enabled && still !== "fixed", still);
  await page.unroute("**/photos");
  page.problems = page.problems.filter((p) => !/photos|ERR_FAILED|Failed to load/.test(p));   // обрыв подставлен тестом
  await page.click(".bc-inbox__detail .bc-staff__fix button[type=submit]");
  await page.waitForFunction(() => !document.querySelector(".bc-inbox__detail [name=what_done]"), null, { timeout: 15000 });
  await page.click(".bc-inbox__tab[data-tab='waiting_check']");
  const moved = await page.waitForSelector(`.bc-inbox__row[data-key="${key}"]`, { timeout: 8000 }).then(() => true, () => false);
  check(`${tag}: [§2.5] после «Сообщить жителям» — во вкладке «Ждут проверки»`, moved);
  const withPhoto = (await staffApi(base, "GET", `/complaints/${made.data.complaint.id}`)).data.complaint;
  check(`${tag}: [B-056] фото «после» дошло с повторной попытки (CSP connect-src 'self')`,
        ((withPhoto.resolution || {}).photos_after || []).length === 1, JSON.stringify((withPhoto.resolution || {}).photos_after));
  // Пример (demo) — только просмотр, без формы (как карточка R07).
  await page.click(".bc-inbox__tab[data-tab='new']");
  const demoRow = await page.$(".bc-inbox__item[data-demo] .bc-inbox__row");
  if (demoRow) {
    // R11 D-5: в списке «Пример» — одна сноска внизу, не у каждой строки; метка — у раскрытой строки.
    const note = await page.evaluate(() => ({ rowTags: document.querySelectorAll(".bc-inbox__row .bk-tag--demo").length,
      footnote: (document.querySelector(".bc-inbox > .bc-demo-note") || {}).textContent || "" }));
    check(`${tag}: [D-5] «Пример» — сноской под списком, не в строках`, note.rowTags === 0 && /пример|үлгі/i.test(note.footnote), JSON.stringify(note));
    await page.evaluate(() => document.querySelector(".bc-inbox__item[data-demo] .bc-inbox__row").click());
    await page.waitForSelector(".bc-inbox__item--open", { timeout: 5000 });
    const ro = await page.evaluate(() => ({ form: !!document.querySelector(".bc-inbox__detail .bc-staff"),
      text: document.querySelector(".bc-inbox__detail").textContent }));
    check(`${tag}: пример «Пример» — без действий, с пояснением`, !ro.form && (lang === "kk" ? /үлгі/.test(ro.text) : /пример/.test(ro.text)), ro.text.slice(0, 80));
  }
  await page.evaluate((l) => BirgeComplaint.setLang(l === "kk" ? "ru" : "kk"), lang);
  await page.evaluate(() => window.inboxCtl.setLang());
  // Словарь R11 грузится асинхронно — экран перерисуется по событию "birge:lang".
  await page.waitForFunction((want) => document.querySelector(".bc-inbox__title").textContent.trim() === want,
                             lang === "kk" ? "Обращения" : "Өтініштер", { timeout: 5000 }).catch(() => {});
  const other = (await page.textContent(".bc-inbox__title")).trim();
  check(`${tag}: setLang перерисовывает экран («${other}»)`, lang === "kk" ? other === "Обращения" : other === "Өтініштер", other);
  await page.evaluate(() => window.inboxCtl.destroy());
  check(`${tag}: destroy снимает экран`, !(await page.$(".bc-inbox")));
  check(`${tag}: нет ключей и технических слов`, (await visibleKeys(page)).length === 0);
  check(`${tag}: нет ошибок консоли`, page.problems.length === 0, page.problems.join(" | "));
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
  // R01 INTEGRATION §8: Escape закрывает и «Мои обращения», когда фокус вне панели (например, на карте).
  await page.evaluate(() => window.standUi.openMine());
  await page.waitForSelector(".bc-panel[data-step='mine']");
  await page.evaluate(() => { document.activeElement && document.activeElement.blur(); window.standMap.getCanvas().focus(); });
  await page.keyboard.press("Escape");
  check(`${tag}: Escape закрывает «Мои обращения» при фокусе на карте`, await page.isHidden(".bc-panel"));
  await page.context().close();
}

(async () => {
  const procs = [];
  let exitCode = 0;
  try {
    const kit = (r11Dir ? ["--r11", r11Dir] : []).concat(real ? ["--real-geo", "--real-ml"] : []);
    procs.push(await startStand(8791, kit));
    procs.push(await startStand(8792, ["--no-ml"].concat(kit)));
    const browser = await chromium.launch();
    const info1 = await (await fetch("http://127.0.0.1:8791/stand/info")).json();
    const info2 = await (await fetch("http://127.0.0.1:8792/stand/info")).json();
    if (real) check("стенд вызывает настоящие R12 /targets и R04 /classify, /similar (не FIXTURE)",
                    info1.real_geo && info1.real_ml && info2.real_geo && !info2.real_ml, JSON.stringify([info1, info2].map(
                      (i) => ({ geo: i.real_geo, ml: i.real_ml }))));
    if (!only || only === "wave") {
      // Волна 1–2: все 4 сочетания 375/1366 × ru/kk; свои точки на пустых местах (иначе «Я тоже» к жалобам
      // других сценариев).
      const combos = [["ru", 375, 812], ["kk", 375, 812], ["ru", 1366, 768], ["kk", 1366, 768]];
      for (const [i, [lang, w, h]] of combos.entries()) {
        await waveWizard(browser, "http://127.0.0.1:8791", lang, w, h, `${w}-${lang}-wave`, [71.4520 - 0.02 * i, 51.0700]);
      }
      await draftSurvives(browser, "http://127.0.0.1:8791", "ru", "375-ru-draft", [71.4700, 51.0900]);
      for (const [i, [lang, w, h]] of combos.entries()) {
        await centralScene(browser, "http://127.0.0.1:8791", lang, w, h, `${w}-${lang}-scene`, [71.4800 - 0.03 * i, 51.1150]);
      }
      for (const [i, [lang, w, h]] of combos.entries()) {
        await inboxScreen(browser, "http://127.0.0.1:8791", lang, w, h, `${w}-${lang}-inbox`, [71.4900 - 0.035 * i, 51.0600]);
      }
    }
    if (!only) {
      await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "ru", 375, 812, "375-ru");
      await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "kk", 375, 812, "375-kk");
      await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "ru", 1366, 768, "1366-ru");
      await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "kk", 1366, 768, "1366-kk");
      // Разные «пустые» точки: иначе вторая жалоба в той же ячейке правильно получит «Я тоже» к первой.
      await newComplaintAndMine(browser, "http://127.0.0.1:8791", "kk", 375, 812, "375-kk-new", [71.4605, 51.0785]);
      await newComplaintAndMine(browser, "http://127.0.0.1:8791", "ru", 1366, 768, "1366-ru-new", [71.3965, 51.0765]);
      await withoutMl(browser, "http://127.0.0.1:8792", info2.hot, "375-noml");
      await badgeTap(browser, "http://127.0.0.1:8791", info1.hot, "kk", 375, 812, "375-kk-badge");
      await phoneLayout(browser, "http://127.0.0.1:8791", info1.hot, "ru", "375-ru-layout");
      await phoneLayout(browser, "http://127.0.0.1:8791", info1.hot, "kk", "375-kk-layout");
      await badgeTap(browser, "http://127.0.0.1:8791", info1.hot, "ru", 1366, 768, "1366-ru-badge");
      await keyboard(browser, "http://127.0.0.1:8791", "1366-kbd");
      await placeTotal(browser, "http://127.0.0.1:8791", "ru", 375, 812, "375-ru-place", [71.4410, 51.0860]);
      await placeTotal(browser, "http://127.0.0.1:8791", "kk", 1366, 768, "1366-kk-place", [71.4130, 51.1010]);
      for (const [lang, w, h] of [["ru", 375, 812], ["kk", 375, 812], ["ru", 1366, 768], ["kk", 1366, 768]]) {
        await mineStates(browser, "http://127.0.0.1:8791", lang, w, h, `${w}-${lang}-states`);
      }
    }
    // LOCAL_FINAL №1–2 (они ломали демо) — в конце: «У меня другое» создаёт настоящую жалобу на демо-остановке,
    // и в сценариях после неё похожей оказалась бы она, а не демо-жалоба с меткой «Пример».
    for (const [lang, w, h] of (only === "wave" ? [] : [["ru", 375, 812], ["kk", 1366, 768]])) {
      await staffFirst(browser, "http://127.0.0.1:8791", info1.hot, lang, w, h, `${w}-${lang}-staff-first`);
      await quickClose(browser, "http://127.0.0.1:8791", info1.hot, lang, w, h, `${w}-${lang}-quick-close`);
    }
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
