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
// --r11 <папка с web/civic/ui-kit и web/civic/i18n R11>: стенд подключает настоящий ui-kit и словари R11.
const r11Dir = args.includes("--r11") ? path.resolve(args[args.indexOf("--r11") + 1]) : null;
// --real: стенд вызывает настоящие R12 engine.civic_geo и R04 ui.civic_ml_api (их пакеты должны лежать в дереве).
const real = args.includes("--real");
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
    const timer = setTimeout(() => reject(new Error("stand did not start: " + out)), 90000);
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
    const right = r && !mobile ? r.left : canvas.right;
    const bottom = r && mobile ? r.top : canvas.bottom;
    const want = { x: (canvas.left + right) / 2, y: (canvas.top + bottom) / 2 };
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
  // R11 №6: в чипе одна галочка — её рисует ui-kit (::before), своей в тексте нет.
  const ticks = await page.$eval(".bc-cat-row .bk-chip[aria-pressed='true']", (c) => ({
    inText: (c.textContent.match(/✓/g) || []).length, before: getComputedStyle(c, "::before").content }));
  check(`${tag}: [R11-6] одна галочка в чипе категории`, ticks.inText === 0 && /✓/.test(ticks.before), JSON.stringify(ticks));
  const chip = await page.textContent(".bc-cat-row");
  check(`${tag}: подсказка категории чипом`, lang === "kk" ? /Аялдамалар мен көлік/.test(chip) : /Остановки и транспорт/.test(chip), chip.trim());
  await shot(page, `${tag}-3-text`);
  await page.click(".bc-send"); taps++;
  await page.waitForSelector(".bc-panel[data-step='4']", { timeout: 8000 });
  const title4 = await page.textContent(".bc-title");
  const before = Number((title4.match(/\d+/) || [0])[0]);
  check(`${tag}: шаг 4 «уже сообщили N» (N ≥ 7 по демо-цели)`, before >= 7, title4);
  const leak = await page.evaluate(() => document.querySelector(".bc-panel").innerText.includes("нет крыши") &&
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
    events[0].target && events[0].target.id === hot.target.id && events[0].reporters === before + 1, JSON.stringify(events));
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
  await page.fill("#bc-text", "Павильон остановки сломан");
  await page.waitForSelector(".bk-catgrid", { timeout: 8000 });
  check(`${tag}: /classify недоступен — сразу сетка категорий, без ошибки`,
        !(await page.isVisible(".bc-toast:not([hidden])")));
  await checkGridWords(page, tag);
  await page.click(".bk-catgrid > button:nth-child(4)");  // «Остановки и транспорт»
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
    await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "ru", 375, 812, "375-ru");
    await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "kk", 375, 812, "375-kk");
    await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "ru", 1366, 768, "1366-ru");
    await residentPath(browser, "http://127.0.0.1:8791", info1.hot, "kk", 1366, 768, "1366-kk");
    // Разные «пустые» точки: иначе вторая жалоба в той же ячейке правильно получит «Я тоже» к первой.
    await newComplaintAndMine(browser, "http://127.0.0.1:8791", "kk", 375, 812, "375-kk-new", [71.4605, 51.0785]);
    await newComplaintAndMine(browser, "http://127.0.0.1:8791", "ru", 1366, 768, "1366-ru-new", [71.3965, 51.0765]);
    await withoutMl(browser, "http://127.0.0.1:8792", info2.hot, "375-noml");
    await badgeTap(browser, "http://127.0.0.1:8791", info1.hot, "kk", 375, 812, "375-kk-badge");
    await badgeTap(browser, "http://127.0.0.1:8791", info1.hot, "ru", 1366, 768, "1366-ru-badge");
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
