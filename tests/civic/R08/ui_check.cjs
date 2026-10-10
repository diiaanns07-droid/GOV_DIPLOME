/*
 * R08 · браузерная проверка «Картины дня» (Playwright, Chromium).
 *
 *   python tests/civic/R08/demo_server.py &                       # http://127.0.0.1:8508
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/ui_check.cjs [base_url] [папка_скриншотов]
 *
 * Проверяет чек-лист UX_BRIEF / UX_SPEC §8 на 1366×768 и 375×812, ru и kk:
 *  нет горизонтальной прокрутки и обрезанного текста, нет ключей перевода и технических слов,
 *  шрифт ≥ 14 px, зоны нажатия ≥ 48 px, 4 числа и сводка видны без прокрутки на ноутбуке,
 *  состояния (загрузка, нет связи, ошибка сервера, пусто, карта жалоб не отвечает, неверная дата),
 *  клик по горячему месту → событие для карты, фильтр района и даты в адресе, смена языка без запроса,
 *  клавиатура (Tab до кнопки печати, видна рамка фокуса), вид для печати (PDF A4).
 * Итог — ui_check.json в папке скриншотов; код выхода 1, если есть FAIL.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8508").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-14-results/R08/screens");
const PAGE = BASE + "/civic/akim/";
const API = "**/api/civic/v2/akim/summary*";
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail == null ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && !ok ? " — " + JSON.stringify(detail) : ""));
}

const TECH = /ребро|граф\b|геометри|сценари|payload|demo-ring|undefined|NaN|\bnull\b|\btarget\b|\bsegment\b|osm-/i;
const KEYLIKE = /\b(akim|common|district|cat|status|stage|object|heat|dates)\.[a-z_]+(\.[a-z_0-9]+)*\b/;

async function open(browser, { width, height, lang, query = "", route } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height }, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  const page = await ctx.newPage();
  const logs = [];
  page.on("console", (m) => {
    if (m.type() === "warning" || m.type() === "error") logs.push(m.type() + ": " + m.text());
  });
  page.on("pageerror", (e) => logs.push("pageerror: " + e.message));
  if (route) await page.route(API, route);
  await page.goto(PAGE + "?lang=" + (lang || "ru") + (query ? "&" + query : ""));
  return { ctx, page, logs };
}

async function waitState(page, state) {
  await page.waitForSelector(`#akim[data-state=${state}]`, { timeout: 15000 });
}

// Мелкий текст, обрезанный текст и маленькие зоны нажатия — одним проходом по DOM.
async function layoutProblems(page) {
  return page.evaluate(() => {
    const out = { hscroll: document.documentElement.scrollWidth - window.innerWidth, small: [], clipped: [], tiny: [] };
    const all = document.querySelectorAll("#akim *, header *");
    for (const el of all) {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const hasText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
      if (hasText && parseFloat(cs.fontSize) < 14) out.small.push(el.className + ":" + el.textContent.trim().slice(0, 30));
      if (hasText && el.scrollWidth > el.clientWidth + 1 && cs.overflow !== "visible" && el.clientWidth > 0)
        out.clipped.push(el.className + ":" + el.textContent.trim().slice(0, 30));
    }
    for (const el of document.querySelectorAll("#akim a, #akim button, #akim select, #akim input")) {
      const r = el.getBoundingClientRect();
      if (r.width && r.height < 44) out.tiny.push((el.className || el.tagName) + ":" + Math.round(r.height));
    }
    return out;
  });
}

async function shot(page, name, full) {
  const file = path.join(OUT, name + (full ? ".jpg" : ".png"));
  await page.screenshot({ path: file, fullPage: !!full, type: full ? "jpeg" : "png", quality: full ? 70 : undefined });
  return file;
}

(async () => {
  const browser = await chromium.launch();
  let realSummary = null;

  // ───────────── 1. Четыре экрана: 1366 / 375 × ru / kk ─────────────
  for (const [width, height] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${width}-${lang}`;
      let calls = 0;
      const { ctx, page, logs } = await open(browser, {
        width, height, lang,
        route: async (route) => {
          calls++;
          const resp = await route.fetch();
          const body = await resp.json();
          if (!realSummary) realSummary = body;
          await route.fulfill({ response: resp, json: body });
        },
      });
      await waitState(page, "ok");
      await page.waitForTimeout(600); // полосы растут 480 мс
      await shot(page, `akim-${tag}`);
      await shot(page, `akim-${tag}-full`, true);
      const text = await page.evaluate(() => document.body.innerText);
      const lp = await layoutProblems(page);
      check(`${tag}: нет горизонтальной прокрутки`, lp.hscroll <= 0, lp.hscroll);
      check(`${tag}: нет ключей перевода на экране`, !KEYLIKE.test(text), (text.match(KEYLIKE) || [])[0]);
      check(`${tag}: нет технических слов`, !TECH.test(text), (text.match(TECH) || [])[0]);
      check(`${tag}: нет предупреждений [i18n] и ошибок JS`, logs.length === 0, logs);
      check(`${tag}: шрифт не меньше 14 px`, lp.small.length === 0, lp.small.slice(0, 5));
      check(`${tag}: текст не обрезан`, lp.clipped.length === 0, lp.clipped.slice(0, 5));
      check(`${tag}: зоны нажатия не меньше 44 px`, lp.tiny.length === 0, lp.tiny.slice(0, 5));
      const nums = await page.$$eval(".akim-kpi .bk-kpi__value", (els) => els.map((e) => e.textContent));
      check(`${tag}: 4 крупных числа`, nums.length === 4 && nums.every((n) => /^\d[\d ]*$/.test(n)), nums);
      const deltas = await page.$$eval(".akim-kpi > .bk-kpi__delta", (els) => els.map((e) => [e.dataset.trend, e.textContent.trim()]));
      check(`${tag}: у изменения есть слово, не только цвет`, deltas.length === 4 && deltas.every(([t, s]) => t && s.length > 3), deltas);
      const hot = await page.$$(".akim-hot__item");
      check(`${tag}: 10 горячих мест`, hot.length === 10, hot.length);
      const summary = await page.textContent(".akim-summary__text");
      const expected = realSummary && realSummary.text[lang];
      check(`${tag}: сводка текстом совпадает с сервером`, summary.trim() === (expected || "").trim(), summary.slice(0, 80));
      check(`${tag}: главная проблема выделена`, (await page.$$(".akim-summary__main")).length === 1);
      check(`${tag}: пометка «Пример» у демо-данных`, (await page.$$(".bk-tag--demo")).length >= 1);
      if (width === 1366) {
        const fold = await page.evaluate(() => {
          const r = (s) => document.querySelector(s).getBoundingClientRect();
          return { kpi: Math.max(...Array.from(document.querySelectorAll(".akim-kpi")).map((e) => e.getBoundingClientRect().bottom)),
                   text: r(".akim-summary__text").bottom, hot1: r(".akim-hot__item").bottom, h: innerHeight };
        });
        check(`${tag}: числа, сводка и первое горячее место видны без прокрутки`, fold.kpi < fold.h && fold.text < fold.h && fold.hot1 <= fold.h, fold);
      }
      // Смена языка — без нового запроса (текст сводки пришёл сразу на двух языках).
      const before = calls;
      const other = lang === "ru" ? "kk" : "ru";
      await page.click(`[data-lang=${other}]`);
      await page.waitForFunction((l) => document.documentElement.lang === l, other);
      await page.waitForTimeout(150);
      const switched = await page.textContent(".akim-summary__text");
      check(`${tag}: ҚАЗ/РУС переключает без запроса к серверу`, calls === before && switched.trim() === realSummary.text[other].trim(), { calls, before });
      await ctx.close();
    }
  }

  // ───────────── 2. Действия на ноутбуке ─────────────
  {
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru" });
    await waitState(page, "ok");
    const first = realSummary.hot.items[0].target;
    const href = await page.getAttribute(".akim-hot__item", "href");
    check("горячее место: ссылка на цель карты за 7 дней", href === `/#target=${first.kind}:${encodeURIComponent(first.id)}&days=7`, href);
    await page.evaluate(() => {
      window.__opened = null;
      document.addEventListener("birge:open-target", (e) => { window.__opened = e.detail; e.preventDefault(); });
    });
    const urlBefore = page.url();
    await page.click(".akim-hot__item");
    const opened = await page.evaluate(() => window.__opened);
    check("горячее место: клик отдаёт цель оболочке (birge:open-target)", opened && opened.target.id === first.id && opened.days === 7 && page.url() === urlBefore, opened);

    // Район: клик по полосе района → фильтр, адрес, повторный клик снимает.
    await page.click('.akim-bar-btn:has-text("Нура")');
    await waitState(page, "ok");
    await page.waitForFunction(() => new URLSearchParams(location.search).get("district") === "nura");
    const meta = await page.textContent(".akim__meta");
    const sel = await page.$eval("#akim-district", (e) => e.value);
    const pressed = await page.getAttribute('.akim-bar-btn:has-text("Нура")', "aria-pressed");
    check("район: клик по полосе включает фильтр (адрес, список, подпись)", sel === "nura" && meta.startsWith("Нура") && pressed === "true", { sel, meta, pressed });
    await shot(page, "akim-1366-ru-nura");
    await page.click('.akim-bar-btn:has-text("Нура")');
    await waitState(page, "ok");
    await page.waitForFunction(() => !new URLSearchParams(location.search).get("district"));
    check("район: повторный клик снимает фильтр", (await page.$eval("#akim-district", (e) => e.value)) === "");

    // Дата: вчера → заголовок, кнопка «Сегодня», адрес; «Сегодня» возвращает.
    const yesterday = await page.evaluate(() => new Date(Date.now() + 5 * 3600e3 - 86400e3).toISOString().slice(0, 10));
    await page.fill("#akim-date", yesterday);
    await page.dispatchEvent("#akim-date", "change");
    await waitState(page, "ok");
    await page.waitForFunction((d) => new URLSearchParams(location.search).get("date") === d, yesterday);
    const todayBtn = await page.$(".akim__today");
    const metaPast = await page.textContent(".akim__meta");
    check("дата: прошлый день — «Данные на конец дня» и кнопка «Сегодня»", !!todayBtn && metaPast.includes("конец дня"), metaPast);
    await shot(page, "akim-1366-ru-yesterday");
    await todayBtn.click();
    await waitState(page, "ok");
    await page.waitForFunction(() => !new URLSearchParams(location.search).get("date"));
    check("дата: «Сегодня» возвращает текущий день", !(await page.$(".akim__today")));

    // Клавиатура: Tab доходит до печати, рамка фокуса видна.
    await page.focus("body");
    let reached = false;
    let outline = null;
    for (let i = 0; i < 12 && !reached; i++) {
      await page.keyboard.press("Tab");
      const info = await page.evaluate(() => {
        const el = document.activeElement;
        const cs = getComputedStyle(el);
        return { print: el.classList.contains("akim__print"), outline: cs.outlineStyle + " " + cs.outlineWidth };
      });
      reached = info.print;
      outline = info.outline;
    }
    check("клавиатура: Tab доходит до «Распечатать», рамка фокуса видна", reached && /solid 3px/.test(outline), outline);
    await ctx.close();
  }

  // ───────────── 3. Состояния ─────────────
  async function stateCase(name, route, expectState, expectText, screenshotName, query) {
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru", route, query });
    await waitState(page, expectState);
    const text = await page.evaluate(() => document.getElementById("akim").innerText);
    const okText = expectText.every((t) => text.includes(t));
    check(name, okText, okText ? null : text.slice(0, 300));
    if (screenshotName) await shot(page, screenshotName);
    return { ctx, page };
  }

  {
    // Загрузка: ответ задерживаем, видим скелетон и подпись.
    let release;
    const gate = new Promise((r) => (release = r));
    const { ctx, page } = await open(browser, {
      width: 1366, height: 768, lang: "ru",
      route: async (route) => { await gate; await route.continue(); },
    });
    await waitState(page, "loading");
    await page.waitForSelector(".bk-skel");
    const t = await page.textContent(".akim-loading");
    check("состояние: загрузка — скелетон и «Собираем картину дня…»", t.includes("Собираем картину дня"), t);
    await shot(page, "akim-state-loading");
    release();
    await waitState(page, "ok");
    await ctx.close();
  }
  {
    // Нет связи → «Повторить» возвращает данные.
    let fail = true;
    const { ctx, page } = await stateCase(
      "состояние: нет связи — понятный текст и «Повторить»",
      async (route) => (fail ? route.abort("internetdisconnected") : route.continue()),
      "error", ["Нет связи с сервером", "Повторить"], "akim-state-network");
    fail = false;
    await page.click(".bk-error .bk-btn");
    await waitState(page, "ok");
    check("состояние: после «Повторить» данные на месте", (await page.$$(".akim-kpi .bk-kpi__value")).length === 4);
    await ctx.close();
  }
  (await stateCase("состояние: ошибка сервера 500",
    (route) => route.fulfill({ status: 500, json: { error: "akim_failed", message: "x" } }),
    "error", ["Не получилось загрузить", "Повторить"], null)).ctx.close();
  (await stateCase("состояние: сервер ответил «дата в будущем» — предложено «Сегодня»",
    (route) => route.fulfill({ status: 400, json: { error: "bad_request", field: "date", message: "x" } }),
    "error", ["Выберите сегодня или прошлый день", "Сегодня"], null)).ctx.close();

  // Пусто: та же структура ответа, все числа — ноль.
  const empty = JSON.parse(JSON.stringify(realSummary));
  for (const k of Object.keys(empty.kpi)) Object.assign(empty.kpi[k], { value: 0, prev: 0, abs: 0, pct: null, ratio: null, trend: "flat", mode: "abs", waiting: 0 });
  empty.hot.items = [];
  empty.topics.items = [];
  empty.topics.total = 0;
  empty.districts.items.forEach((d) => Object.assign(d, { value: 0, prev: 0, abs: 0, trend: "flat", mode: "abs" }));
  empty.main_problem = null;
  empty.empty = true;
  Object.assign(empty.objects, { late: [], stale: [], late_count: 0, stale_count: 0 });
  Object.assign(empty.proposals, { top: [], new_count: 0, open_count: 0 });
  empty.text = { ru: "Сегодня новых обращений нет. Просроченных обращений нет. Объектов с отставанием нет.",
                 kk: "Бүгін жаңа өтініш жоқ. Мерзімі өткен өтініш жоқ. Кестеден қалып жатқан нысан жоқ." };
  empty.text_parts = { ru: [{ role: "new", text: "Сегодня новых обращений нет." }], kk: [{ role: "new", text: "Бүгін жаңа өтініш жоқ." }] };
  {
    const { ctx, page } = await stateCase("состояние: пусто — «Сегодня новых обращений нет» и подсказки в блоках",
      (route) => route.fulfill({ json: empty }), "ok",
      ["Сегодня новых обращений нет", "За 7 дней нерешённых жалоб нет", "Все объекты идут по графику", "Новых предложений нет"],
      "akim-state-empty");
    const lp = await layoutProblems(page);
    check("состояние: пусто — нет пустых белых блоков и прокрутки", lp.hscroll <= 0);
    await ctx.close();
  }
  {
    const noHeat = JSON.parse(JSON.stringify(realSummary));
    for (const k of ["hot", "topics", "districts"]) noHeat[k] = { available: false, reason: "heat_unavailable" };
    noHeat.main_problem = null;
    (await stateCase("состояние: карта жалоб не отвечает — блоки честно говорят об этом",
      (route) => route.fulfill({ json: noHeat }), "ok", ["Карта жалоб пока не отвечает"], null)).ctx.close();
  }

  // ───────────── 4. Печать ─────────────
  {
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru" });
    await waitState(page, "ok");
    await page.emulateMedia({ media: "print" });
    const hidden = await page.evaluate(() => ["header.bk-header", ".akim__controls", ".akim-print-bottom"].map(
      (s) => getComputedStyle(document.querySelector(s)).display));
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    check("печать: без шапки, кнопок и выбора даты; белый фон", hidden.every((d) => d === "none") && bg === "rgb(255, 255, 255)", { hidden, bg });
    await shot(page, "akim-print", true);
    const pdf = await page.pdf({ format: "A4", printBackground: true });
    const pages = (pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
    fs.writeFileSync(path.join(OUT, "akim-print.pdf"), pdf);
    check("печать: помещается на 1–3 листа A4", pages >= 1 && pages <= 3, pages);
    await ctx.close();
  }

  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "ui_check.json"), JSON.stringify({ base: BASE, total: results.length, failed, results }, null, 1));
  console.log(`\n${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
