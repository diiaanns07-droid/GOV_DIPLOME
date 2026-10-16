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
 *  UX_REVIEW R11 день 3: одна метка «Пример» (п. 11), одно изменение в карточке на телефоне (п. 10),
 *  полоса этапов у объектов (п. 14), снимок поля даты в ru-RU/kk-KZ (п. 13).
 *  Волна 2 (R11 IA_WAVE2 §5): «Нужно решение акима» 1–3 карточки с двумя вариантами и «Выбрать», «Пульс района»
 *  ≤ 3 строки + «Ещё N», плитка «Исправлено» со строкой проверки жителями, уточнение у горячих мест,
 *  первый экран: на 1366 — числа и первая карточка решения, на 375 — числа 2×2 и заголовок блока решений;
 *  нет решений — блока нет; нет тревог — одна строка. Стенд: demo_server.py --wave2-demo.
 * Как в сборке (ui-kit и i18n R11): demo_server.py --kit-dir <папка с web/civic/ui-kit и web/civic/i18n R11>.
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
      const box = el.getBoundingClientRect();
      if (box.width <= 1 && box.height <= 1) continue; // только для экранного диктора — на экране не видно
      const hasText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
      if (hasText && parseFloat(cs.fontSize) < 12) out.small.push(el.className + ":" + el.textContent.trim().slice(0, 30));
      if (hasText && el.scrollWidth > el.clientWidth + 1 && cs.overflow !== "visible" && el.clientWidth > 0)
        out.clipped.push(el.className + ":" + el.textContent.trim().slice(0, 30));
    }
    for (const el of document.querySelectorAll("#akim a, #akim button, #akim select, #akim input, #akim summary")) {
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
      check(`${tag}: шрифт не меньше 12 px (эталон A: подписи 12)`, lp.small.length === 0, lp.small.slice(0, 5));
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
      // CLEAN_PASS §2/§3 R08 п. 1: «данные — пример» — одна серая строка внизу (common.demo_footnote), меток «Пример» нет.
      const demo = await page.evaluate(() => {
        const f = document.querySelector("#akim .bk-footnote.akim-demo");
        const last = f && Array.from(f.parentElement.children).filter((e) => e.getClientRects().length).pop();
        const fb = f ? f.getBoundingClientRect() : null;
        const below = fb ? Array.from(document.querySelectorAll("#akim .akim-card, #akim .akim-kpis, #akim .akim-summary"))
          .filter((e) => e.getBoundingClientRect().bottom > fb.top + 1).length : -1;
        return { tags: document.querySelectorAll("#akim .bk-tag--demo").length, footnotes: document.querySelectorAll("#akim .bk-footnote").length,
                 note: f ? f.textContent : "", bottom: below === 0, size: f ? parseFloat(getComputedStyle(f).fontSize) : 0, isLast: last === f || below === 0 };
      });
      check(`${tag}: «${lang === "kk" ? "Деректер — үлгі" : "Данные — пример"}» — одна строка внизу, меток «Пример» нет (CLEAN_PASS п. 1)`,
        demo.tags === 0 && demo.footnotes === 1 && demo.note.startsWith(lang === "kk" ? "Деректер — үлгі" : "Данные — пример") && demo.bottom && demo.size === 13, demo);
      // CLEAN_PASS п. 3: плитки без карточек — число 28/600, подпись 15 и ОДНА строка изменения на любой ширине;
      // остальное («за 7 дней», «ждут ответа», «дольше всех», «служба сообщила…») — в «Подробнее».
      const kpiStyle = await page.$$eval(".akim-kpi", (cards) => cards.map((c) => {
        const cs = getComputedStyle(c), v = getComputedStyle(c.querySelector(".bk-kpi__value")), l = getComputedStyle(c.querySelector(".bk-kpi__label"));
        return { deltas: Array.from(c.querySelectorAll(".bk-kpi__delta")).filter((d) => d.getClientRects().length > 0).length,
                 card: cs.boxShadow !== "none" || parseFloat(cs.borderTopWidth) > 0 || !/rgba\(0, 0, 0, 0\)|transparent/.test(cs.backgroundColor),
                 num: v.fontSize + "/" + v.fontWeight, label: l.fontSize };
      }));
      // Эталон A (13 окт): числа — плитки, как «34 новых» в сводке эталона (фон белый 72 %, радиус 12).
      check(`${tag}: числа — плитки эталона, число 22/600, подпись 12 (как в сводке «Сегодня в Астане»), одна строка изменения`,
        kpiStyle.length === 4 && kpiStyle.every((k) => k.deltas === 1 && k.card && k.num === "22px/600" && k.label === "12px"), kpiStyle);
      const more = await page.evaluate(() => {
        const d = document.querySelector(".akim-kpis + .akim-kpi-more, .akim-kpi-more");
        return d ? { open: d.open, summary: d.querySelector("summary").textContent, rows: d.querySelectorAll("li").length } : null;
      });
      check(`${tag}: остальное о числах — в «${lang === "kk" ? "Толығырақ" : "Подробнее"}» (закрыто)`,
        !!more && !more.open && more.summary === (lang === "kk" ? "Толығырақ" : "Подробнее") && more.rows >= 3, more);
      // CLEAN_PASS п. 4: сводка — абзац 17 без плашки, жирная (600) только главная фраза.
      const sum = await page.evaluate(() => {
        const sec = document.querySelector(".akim-summary"), p = document.querySelector(".akim-summary__text");
        const cs = getComputedStyle(sec);
        return { size: getComputedStyle(p).fontSize, plaque: cs.boxShadow !== "none" || parseFloat(cs.borderTopWidth) > 0 || parseFloat(cs.borderLeftWidth) > 0
                   || !/rgba\(0, 0, 0, 0\)|transparent/.test(cs.backgroundColor),
                 bold: Array.from(p.querySelectorAll("*")).filter((e) => parseInt(getComputedStyle(e).fontWeight, 10) >= 600).map((e) => e.className),
                 mainWeight: (document.querySelector(".akim-summary__main") && getComputedStyle(document.querySelector(".akim-summary__main")).fontWeight) || "" };
      });
      check(`${tag}: сводка — абзац 15 px (текст эталона) без плашки, жирная только главная фраза`,
        sum.size === "15px" && !sum.plaque && sum.mainWeight === "600" && sum.bold.length === 1, sum);
      // CLEAN_PASS п. 1–2: заголовок 28/600, одна серая строка 13; поля даты и района — с заливкой; «Распечатать» — ghost.
      const top = await page.evaluate(() => {
        const t = document.querySelector(".akim__title"), cs = getComputedStyle(t);
        return { title: cs.fontSize + "/" + cs.fontWeight, metas: document.querySelectorAll(".akim__meta").length,
                 meta: getComputedStyle(document.querySelector(".akim__meta")).fontSize,
                 fields: document.querySelectorAll(".akim__controls .bk-field").length,
                 print: (document.querySelector(".akim__print") || { className: "" }).className.includes("bk-btn--ghost"),
                 printIcon: !!document.querySelector(".akim__print svg") };
      });
      check(`${tag}: заголовок 22/600 (шкала эталона), одна строка 13, поля с заливкой, «Распечатать» ghost со значком`,
        top.title === "22px/600" && top.metas === 1 && top.meta === "13px" && top.fields === 2 && top.print && top.printIcon, top);
      // CLEAN_PASS §2: два начертания — 400 и 600.
      const weights = await page.evaluate(() => {
        const set = new Set();
        for (const el of document.querySelectorAll("#akim *")) {
          if (!el.getClientRects().length) continue;
          if (Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim())) set.add(getComputedStyle(el).fontWeight);
        }
        return Array.from(set).sort();
      });
      check(`${tag}: начертания эталона — 400, 500, 600 и 700 (цифры на плашках)`, weights.every((w) => ["400", "500", "600", "700"].includes(w)), weights);
      // Эталон A: шкала кеглей 12 / 13 / 14 / 15 / 16 / 19 / 22 / 34 (R11 tokens.css) — других размеров текста нет.
      const sizes = await page.evaluate(() => {
        const set = new Set();
        for (const el of document.querySelectorAll("#akim *")) {
          if (!el.getClientRects().length || el.getBoundingClientRect().width <= 1) continue;
          if (Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim())) set.add(parseFloat(getComputedStyle(el).fontSize));
        }
        return Array.from(set).sort((a, b) => a - b);
      });
      check(`${tag}: кегли только из шкалы эталона 12/13/14/15/16/19/22/34`, sizes.every((s) => [12, 13, 14, 15, 16, 19, 22, 34].includes(s)), sizes);
      // П. 14: у объектов полоса из 6 этапов (ui-kit .bk-stages--compact) и подпись «Этап N из 6: …».
      const stages = await page.$$eval(".akim-objects .akim-obj", (rows) => rows.map((r) => {
        const ol = r.querySelector(".bk-stages--compact");
        return ol ? { n: ol.children.length, cur: ol.querySelectorAll('[data-state="current"]').length,
                      late: ol.classList.contains("bk-stages--late"), cap: (r.querySelector(".bk-stages__caption") || {}).textContent || "" } : null;
      }));
      const capRe = lang === "kk" ? /^Кезең [1-6]\/6: / : /^Этап [1-6] из 6: /;
      check(`${tag}: объекты — полоса 6 этапов и «Этап N из 6» (п. 14)`, stages.length > 0 && stages.every((x) => x && x.n === 6 && x.cur === 1 && capRe.test(x.cap)), stages.slice(0, 3));
      // Дробная кратность по-русски — «в 6,9 раза», не «в 6,9 раз».
      if (lang === "ru") {
        const fr = (text.match(/в \d+,\d+ раз[а]? больше/g) || []);
        check(`${tag}: «в N,N раза больше» для дробных`, fr.every((x) => /раза больше$/.test(x)), fr);
      }
      if (width === 1366) {
        const box = await page.$(".akim__controls");
        if (box) await box.screenshot({ path: path.join(OUT, `akim-date-${lang}.png`) });
        // П3: поле даты Chromium рисует по языку системы (облако — «10/16/2026»); поверх — дата «дд.мм.гггг» из значения поля.
        const dt = await page.evaluate(() => {
          const i = document.querySelector("#akim-date"), t = document.querySelector(".akim__date-text");
          return t ? { text: t.textContent, value: i.value, shown: getComputedStyle(t).display !== "none" } : null;
        });
        check(`${tag}: дата в поле — «дд.мм.гггг» при любом языке браузера`, !!dt && dt.shown
          && dt.text === dt.value.slice(8, 10) + "." + dt.value.slice(5, 7) + "." + dt.value.slice(0, 4), dt);
      }
      // Первый экран по схеме R11 (IA_WAVE2 §5): ноутбук — числа, сводка и первая карточка «Нужно решение акима»
      // (нет решений — первое горячее место); телефон — числа 2×2 и заголовок блока решений.
      const fold = await page.evaluate(() => {
        const r = (s) => (document.querySelector(s) || { getBoundingClientRect: () => ({ top: -1, bottom: -1 }) }).getBoundingClientRect();
        return { kpi: Math.max(...Array.from(document.querySelectorAll(".akim-kpi")).map((e) => e.getBoundingClientRect().bottom)),
                 text: r(".akim-summary__text").bottom, dec1: r(".akim-decision").bottom, decTitle: r("#akim-decisions-title").bottom,
                 hasDec: !!document.querySelector(".akim-decision"), hot1: r(".akim-hot__item").bottom, h: innerHeight };
      });
      if (width === 1366)
        check(`${tag}: без прокрутки — числа, сводка и ${fold.hasDec ? "первая карточка решения" : "первое горячее место"}`,
          fold.kpi < fold.h && fold.text < fold.h && (fold.hasDec ? fold.dec1 > 0 && fold.dec1 <= fold.h : fold.hot1 <= fold.h), fold);
      else check(`${tag}: без прокрутки — числа 2×2 и заголовок «Нужно решение акима»`,
          fold.kpi < fold.h && (!fold.hasDec || (fold.decTitle > 0 && fold.decTitle <= fold.h)), fold);
      // Волна 2: блоки и счётчики (стенд --wave2-demo: проверка жителями и уточнения есть в данных).
      const w2 = await page.evaluate(() => {
        const q = (s) => Array.from(document.querySelectorAll(s));
        return {
          cards: q(".akim-decision").map((c) => ({ opts: c.querySelectorAll(".akim-decision__option").length,
            btns: c.querySelectorAll(".akim-decision__choose").length + c.querySelectorAll(".akim-decision__chosen").length,
            late: (c.querySelector(".akim-late-days") || {}).textContent || "", needed: !!c.querySelector(".akim-decision__needed") })),
          decTitle: (document.querySelector("#akim-decisions-title") || {}).textContent || "",
          pulseVisible: q(".akim-pulse > .akim-pulse__list > li").length,
          pulseMore: q(".akim-pulse__more li").length,
          pulseMoreSummary: (document.querySelector(".akim-pulse__more > summary") || {}).textContent || "",
          pulseRows: q(".akim-pulse__item").map((li) => [li.querySelector(".akim-pulse__title").textContent, li.querySelector(".akim-pulse__reason").textContent]),
          split: (document.querySelector('.akim-kpi-more li[data-kind="fixed"]') || {}).textContent || "",
          overdue: (document.querySelector('.akim-kpi-more li[data-kind="overdue"]') || {}).textContent || "",
          ghost: q(".akim-decision__choose").every((b) => b.classList.contains("bk-btn--ghost") && !b.classList.contains("bk-btn--primary")),
          decBorders: q(".akim-decision").map((c) => { const cs = getComputedStyle(c);
            return [cs.borderTopWidth, cs.boxShadow === "none", /rgba\(0, 0, 0, 0\)|transparent/.test(cs.backgroundColor)]; }),
          hotSubs: q(".akim-hot__sub").map((e) => e.textContent),
        };
      });
      const kk = lang === "kk";
      check(`${tag}: «${kk ? "Әкімнің шешімі керек" : "Нужно решение акима"}» — 1–3 карточки, у каждой 2 варианта и «Выбрать», срок красным`,
        w2.cards.length >= 1 && w2.cards.length <= 3 && w2.cards.every((c) => c.opts === 2 && c.btns === 2 && c.late && c.needed)
          && w2.decTitle === (kk ? "Әкімнің шешімі керек" : "Нужно решение акима"), w2.cards);
      check(`${tag}: решения — список с линиями 1 px, без плашек; «Выбрать» — ghost (CLEAN_PASS п. 5)`,
        w2.ghost && w2.decBorders.every(([b, noShadow, clear], i) => noShadow && clear && b === (i ? "1px" : "0px")), w2.decBorders);
      check(`${tag}: «Пульс района» — не больше 3 строк сразу, остальное в «${kk ? "Тағы" : "Ещё"} N»`,
        w2.pulseVisible >= 1 && w2.pulseVisible <= 3 && w2.pulseVisible + w2.pulseMore <= 5
          && (w2.pulseMore === 0 || w2.pulseMoreSummary.startsWith(kk ? "Тағы" : "Ещё")), { v: w2.pulseVisible, more: w2.pulseMore, s: w2.pulseMoreSummary });
      check(`${tag}: у каждой тревоги есть причина (без «сигма», «аномалия»)`,
        w2.pulseRows.every(([t, r]) => t.length > 5 && r.length > 5 && !/сигм|аномал|z-/i.test(t + r)), w2.pulseRows.slice(0, 2));
      check(`${tag}: «Подробнее» об «Исправлено» — служба сообщила · жители проверили · вернули`,
        kk ? /^Қызмет хабарлады \d+ · тұрғындар тексерді \d+ · қайтарылды \d+$/.test(w2.split.trim())
           : /^Служба сообщила \d+ · жители проверили \d+ · вернули \d+$/.test(w2.split.trim()), w2.split);
      check(`${tag}: «Подробнее» о «Просрочено» — самое долгое место и срок`, kk ? /^Ең ұзақ кешіккені: .+ · \d+ күнге кешікті$/.test(w2.overdue.trim())
        : /^Дольше всех: .+ · Просрочено на \d+ д(ень|ня|ней)$/.test(w2.overdue.trim()), w2.overdue);
      check(`${tag}: у горячих мест — уточнение жителей, а не только категория`,
        w2.hotSubs.filter((t) => /Сломана детская|Не убран снег|Долго ждать|Яма|Балалар алаңы бұзылған|Қар тазаланбаған|Ұзақ күту|Шұңқыр/.test(t)).length >= 3, w2.hotSubs.slice(0, 4));
      // Дизайн-марафон: мини-графики под числами, мини-карта «Горячих мест», объекты без плашек.
      const dash = await page.evaluate(() => {
        const q = (s) => Array.from(document.querySelectorAll(s));
        const fig = document.querySelector(".akim-hot .akim-minimap");
        const credit = document.querySelector(".akim-hot .akim-minimap__credit");
        return {
          sparks: q(".akim-kpi .akim-spark").map((sv) => ({ hidden: sv.getAttribute("aria-hidden"),
            pts: ((sv.querySelector(".akim-spark__line") || {}).getAttribute ? sv.querySelector(".akim-spark__line").getAttribute("d") : "").split(/[ML]/).filter(Boolean).length,
            h: Math.round(sv.getBoundingClientRect().height) })),
          sparkBottoms: q(".akim-kpi .akim-spark").map((sv) => Math.round(sv.getBoundingClientRect().bottom)),
          map: fig ? { hidden: fig.getAttribute("aria-hidden"), districts: fig.querySelectorAll(".akim-minimap__district").length,
            dots: fig.querySelectorAll(".akim-minimap__dot").length, w: Math.round((fig.querySelector("svg") || fig).getBoundingClientRect().width) } : null,
          credit: credit && credit.getClientRects().length ? credit.textContent : "",
          objTags: q(".akim-objects .bk-tag").length,
          lateWords: q(".akim-objects .akim-obj__late").length,
        };
      });
      check(`${tag}: под каждым числом — мини-график за 14 дней (только для глаза), графики в ряду на одной линии`,
        dash.sparks.length === 4 && dash.sparks.every((x) => x.hidden === "true" && x.pts === 14 && x.h >= 20)
          && (width < 480 ? new Set(dash.sparkBottoms.slice(0, 2)).size === 1 && new Set(dash.sparkBottoms.slice(2)).size === 1
                          : new Set(dash.sparkBottoms).size === 1), dash.sparks.concat([dash.sparkBottoms]));
      check(`${tag}: мини-карта «Горячих мест» — районы и точки мест, подпись © OpenStreetMap`,
        !!dash.map && dash.map.hidden === "true" && dash.map.districts >= 6 && dash.map.dots >= 5 && dash.map.w >= 80 && dash.credit === "© OpenStreetMap", dash.map);
      check(`${tag}: «Объекты с отставанием» — отставание словами, без плашек`, dash.objTags === 0 && dash.lateWords >= 1, dash);
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
  empty.decisions = { available: true, items: [], count: 0, demo: false, source: "complaints" };
  empty.pulse = { available: true, items: [], base_weeks: 4 };
  empty.overdue = { count: 0, places: 0, items: [], top: 5 };
  empty.kpi.verification_available = false;
  Object.assign(empty.objects, { late: [], stale: [], late_count: 0, stale_count: 0 });
  Object.assign(empty.proposals, { top: [], new_count: 0, open_count: 0 });
  empty.text = { ru: "Сегодня новых обращений нет. Сроки исправления не нарушены. Объектов с отставанием нет.",
                 kk: "Бүгін жаңа өтініш жоқ. Мерзімінде түзетілмеген өтініш жоқ. Кестеден қалып жатқан нысан жоқ." };
  empty.text_parts = { ru: [{ role: "new", text: "Сегодня новых обращений нет." }], kk: [{ role: "new", text: "Бүгін жаңа өтініш жоқ." }] };
  {
    // CLEAN_PASS §3 R08 п. 6: пустые блоки не показываем; ниже чисел пусто всё — одно состояние «пусто» ui-kit.
    const { ctx, page } = await stateCase("состояние: пусто — числа и одно состояние «Сегодня новых обращений нет»",
      (route) => route.fulfill({ json: empty }), "ok",
      ["Сегодня новых обращений нет", "Выберите другую дату или район"],
      "akim-state-empty");
    const lp = await layoutProblems(page);
    check("состояние: пусто — нет пустых белых блоков и прокрутки", lp.hscroll <= 0);
    const quiet = await page.evaluate(() => ({
      blocks: Array.from(document.querySelectorAll("#akim .akim-card")).map((e) => e.className),
      empties: document.querySelectorAll("#akim .bk-empty").length, kpis: document.querySelectorAll("#akim .akim-kpi").length,
      text: document.querySelector("#akim").innerText }));
    check("состояние: пусто — блоков-заглушек нет («Резких всплесков нет», «Пока пусто», «идут по графику»), одно «пусто», 4 числа",
      quiet.blocks.length === 0 && quiet.empties === 1 && quiet.kpis === 4
        && !/Резких всплесков нет|Пока пусто|идут по графику|Новых предложений нет|нерешённых жалоб нет/.test(quiet.text), quiet);
    await ctx.close();
  }
  {
    const noHeat = JSON.parse(JSON.stringify(realSummary));
    for (const k of ["hot", "topics", "districts"]) noHeat[k] = { available: false, reason: "heat_unavailable" };
    noHeat.main_problem = null;
    (await stateCase("состояние: карта жалоб не отвечает — блоки честно говорят об этом",
      (route) => route.fulfill({ json: noHeat }), "ok", ["Карта жалоб пока не отвечает"], null)).ctx.close();
    const noComplaints = JSON.parse(JSON.stringify(noHeat));
    noComplaints.complaints_available = false;
    noComplaints.text_parts = { ru: [{ role: "new", text: "Данные об обращениях пока не подключены." }], kk: [{ role: "new", text: "Өтініштер туралы дерек әлі қосылмаған." }] };
    const nc = await stateCase("состояние: жалобы не подключены — вместо нулей прямой текст в сводке",
      (route) => route.fulfill({ json: noComplaints }), "ok", ["Данные об обращениях пока не подключены"], null);
    check("состояние: жалобы не подключены — нет чисел с нулями и блока-заглушки (CLEAN_PASS п. 6)",
      (await nc.page.$$(".akim-kpi, .akim-kpi-more, .akim-no-complaints")).length === 0);
    await nc.ctx.close();
  }
  {
    // B-018 (R10), LOCAL_B2 №4: у настоящих объектов R06 нет title_kk — в ҚАЗ показываем вид объекта по-казахски,
    // а не русское название; в РУС — само название.
    const noKk = JSON.parse(JSON.stringify(realSummary));
    const ruTitle = "Ремонт дороги по ул. Пример";
    const objs = [{ id: "o-real-1", kind: "roadworks", title_ru: ruTitle, title_kk: ruTitle, title_kk_missing: true,
      district: "nura", stage: "construction", planned_end: "2026-11-01", forecast_end: "2026-11-20", delay_days: 19,
      stale: false, updated_at: null, days_since_update: 2, has_place: false, demo: false }];
    Object.assign(noKk.objects, { available: true, late: objs, stale: [], late_count: 1, stale_count: 0, total: 1, demo: false });
    noKk.proposals.top = [{ id: "p-real-1", kind: "square", title_ru: "Сквер у дома 5", title_kk: "Сквер у дома 5",
      title_kk_missing: true, votes_up: 3, votes_down: 1, is_new: true, demo: false }];
    for (const [lang, want, notWant] of [["kk", ["Жол жөндеу", "Гүлзар"], [ruTitle, "Сквер у дома 5"]], ["ru", [ruTitle, "Сквер у дома 5"], ["Жол жөндеу"]]]) {
      const { ctx, page } = await open(browser, { width: 1366, height: 768, lang, route: (route) => route.fulfill({ json: noKk }) });
      await waitState(page, "ok");
      const text = await page.evaluate(() => document.querySelector(".akim-objects").innerText + "\n" + document.querySelector(".akim-proposals").innerText);
      check(`${lang}: объект и предложение без казахского названия — ${lang === "kk" ? "вид по-казахски" : "русское название"}`,
        want.every((t) => text.includes(t)) && notWant.every((t) => !text.includes(t)), text.slice(0, 200));
      await ctx.close();
    }
  }

  {
    // П3: одна кнопка штаба — у тревоги с идущим штабом среди трёх видимых (после «ИИ-разбора» первой может стать тревога
    // без штаба — «ЖКХ: тепло и вода»), иначе — у первой тревоги со ссылкой. Тревога об одном месте ведёт на карту.
    const alarm = (category, crisis, extra) => ({ kind: "spike_city", category, district: null, value: 40, base: 4, ratio: 10, weeks: 4,
      score: 400, districts: [{ district: "nura", value: 30, ratio: 9, ru: "Нура", kk: "Нұра" }], target: null,
      category_ru: category === "utilities" ? "ЖКХ: тепло и вода" : "Снег и гололёд", category_kk: category === "utilities" ? "ТКШ: жылу мен су" : "Қар және көктайғақ",
      district_ru: null, district_kk: null, ...(crisis ? { crisis } : {}), ...(extra || {}) });
    const fresh = { link: "/#agencies/crisis/new/heat_outage", incident: null, kind: "heat_outage" };
    const running = { link: "/#agencies/crisis/inc-7", incident: "inc-7", kind: "blizzard" };
    const place = { ...((realSummary.pulse.items || []).find((x) => x.kind === "new_hot" && x.target) || { kind: "new_hot", category: "yards",
      district: "esil", value: 5, score: 7, target: { kind: "area", id: "yard-1", label_ru: "Двор", label_kk: "Аула" },
      category_ru: "Дворы и площадки", category_kk: "Аулалар мен алаңдар", district_ru: "Есиль", district_kk: "Есіл" }) };
    delete place.crisis;
    const cases = [
      ["первая — новый штаб, вторая — идущий → кнопка у второй, в идущий штаб", [alarm("utilities", fresh), alarm("snow_ice", running), place], 1, running.link],
      ["идущего штаба нет → кнопка у первой тревоги со ссылкой", [alarm("utilities", fresh), place, alarm("snow_ice", null)], 0, fresh.link],
      ["идущий штаб только под «Ещё» → кнопка у первой видимой", [alarm("utilities", fresh), place, place, alarm("snow_ice", running)], 0, fresh.link],
    ];
    for (const [name, items, at, href] of cases) {
      const s = JSON.parse(JSON.stringify(realSummary));
      s.pulse = { available: true, items: JSON.parse(JSON.stringify(items)), base_weeks: 4 };
      const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru", route: (route) => route.fulfill({ json: s }) });
      await waitState(page, "ok");
      const got = await page.evaluate(() => [...document.querySelectorAll(".akim-pulse__item")].map((li, i) =>
        [i, (li.querySelector(".akim-pulse__crisis") || {}).getAttribute ? li.querySelector(".akim-pulse__crisis").getAttribute("href") : null]).filter((x) => x[1]));
      check(`пульс: ${name}`, got.length === 1 && got[0][0] === at && got[0][1] === href, got);
      await ctx.close();
    }
  }

  {
    // Реестр объектов пуст (район без работ) или все идут по графику — блока нет (CLEAN_PASS п. 6), не «идут по графику».
    const none = JSON.parse(JSON.stringify(realSummary));
    Object.assign(none.objects, { available: true, late: [], stale: [], late_count: 0, stale_count: 0, total: 0 });
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru", route: (route) => route.fulfill({ json: none }) });
    await waitState(page, "ok");
    const t = await page.evaluate(() => ({ block: !!document.querySelector(".akim-objects"), text: document.querySelector("#akim").innerText }));
    check("объекты: пустой реестр — блока нет, нет «идут по графику»", !t.block && !t.text.includes("идут по графику"), t.block);
    await ctx.close();
  }

  {
    // Горячее место без подписи (новая цель) — вид места словами, а не пустая строка.
    const noLabel = JSON.parse(JSON.stringify(realSummary));
    noLabel.hot.items[0].target.label_ru = null;
    noLabel.hot.items[0].target.label_kk = null;
    noLabel.hot.items[0].target.kind = "segment";
    for (const [lang, word] of [["ru", "Участок улицы"], ["kk", "Көше бөлігі"]]) {
      const { ctx, page } = await open(browser, { width: 1366, height: 768, lang, route: (route) => route.fulfill({ json: noLabel }) });
      await waitState(page, "ok");
      const t = (await page.textContent(".akim-hot__item .bk-list__title")).trim();
      check(`${lang}: горячее место без подписи — «${word}», а не пусто`, t === word, t);
      await ctx.close();
    }
  }

  {
    // R11 (ночь 6, п. 4): объект с местом на карте — ссылка /#object=<id> и событие birge:open-object;
    // объект без места (мероприятие «без точного места», демо-фикстура) — обычная строка.
    const withPlace = JSON.parse(JSON.stringify(realSummary));
    const base = { kind: "roadworks", title_ru: "Ремонт тротуара", title_kk: "Тротуарды жөндеу", title_kk_missing: false,
      district: "nura", stage: "construction", planned_end: "2026-11-01", forecast_end: "2026-11-20", delay_days: 19,
      stale: false, updated_at: null, days_since_update: 2, demo: true };
    const objs = [{ ...base, id: "obj-place-1", has_place: true }, { ...base, id: "obj-noplace-2", title_ru: "Мероприятие без места", has_place: false, delay_days: 6 }];
    Object.assign(withPlace.objects, { available: true, late: objs, stale: [], late_count: 2, stale_count: 0, total: 2 });
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru", route: (route) => route.fulfill({ json: withPlace }) });
    await waitState(page, "ok");
    const byDefault = await page.$$(".akim-objects a.akim-obj--link");
    check("объекты: по умолчанию (objectHref не задан) строки не ссылки", byDefault.length === 0, byDefault.length);
    // Включаем переход, как это сделает оболочка R01: mount(…, { objectHref: "/#object={id}" }).
    await page.evaluate(() => {
      const el = document.getElementById("akim");
      el.birgeAkim.destroy();
      window.BirgeAkim.mount(el, { objectHref: "/#object={id}", syncUrl: false });
    });
    await waitState(page, "ok");
    await page.waitForSelector(".akim-objects .akim-obj");
    const links = await page.$$eval(".akim-objects a.akim-obj--link", (els) => els.map((a) => a.getAttribute("href")));
    const rows = await page.$$eval(".akim-objects .akim-obj", (els) => els.length);
    await page.evaluate(() => {
      window.__obj = null;
      document.addEventListener("birge:open-object", (e) => { window.__obj = e.detail; e.preventDefault(); });
    });
    const urlBefore = page.url();
    await page.click(".akim-objects a.akim-obj--link");
    const opened = await page.evaluate(() => window.__obj);
    check("объекты: с местом — ссылка на карту и событие, без места — обычная строка",
      links.length === 1 && links[0] === "/#object=obj-place-1" && rows === 2 && opened && opened.id === "obj-place-1" && page.url() === urlBefore,
      { links, rows, opened });
    await ctx.close();
  }
  for (const lang of ["ru", "kk"]) {
    // R11 (ночь 5): на телефоне длинные названия тем («Жаяу жүргіншілер жолы») — в одну строку, полоса под ними.
    const { ctx, page } = await open(browser, { width: 375, height: 812, lang });
    await waitState(page, "ok");
    const tall = await page.$$eval(".akim-topics .bk-bar__label, .akim-districts .bk-bar__label", (els) =>
      els.filter((e) => e.getBoundingClientRect().height > 30).map((e) => e.textContent.trim()));
    check(`375-${lang}: подписи тем и районов в одну строку`, tall.length === 0, tall);
    await ctx.close();
  }

  // ───────────── 3б. Тихое обновление ─────────────
  {
    // Второй ответ сервера отличается (+1 новое обращение); третий — нет связи. Экран не мигает скелетоном,
    // фокус остаётся на той же строке «Горячих мест», при ошибке старые числа остаются.
    let call = 0;
    const changed = JSON.parse(JSON.stringify(realSummary));
    changed.kpi.new_day.value += 1;
    const { ctx, page } = await open(browser, {
      width: 1366, height: 768, lang: "ru",
      route: async (route) => {
        call++;
        if (call === 1) return route.continue();
        if (call === 2) return route.fulfill({ json: changed });
        return route.abort("internetdisconnected");
      },
    });
    await waitState(page, "ok");
    const before = await page.textContent(".akim-kpi .bk-kpi__value");
    await page.focus(".akim-hot__item >> nth=2");
    const key = await page.evaluate(() => document.activeElement.getAttribute("data-key"));
    let sawLoading = false;
    await page.exposeFunction("__akimState", (st) => { if (st === "loading") sawLoading = true; });
    await page.evaluate(() => new MutationObserver(() => window.__akimState(document.getElementById("akim").dataset.state))
      .observe(document.getElementById("akim"), { attributes: true, attributeFilter: ["data-state"] }));
    await page.evaluate(() => document.getElementById("akim").birgeAkim.refresh());
    await page.waitForFunction((b) => document.querySelector(".akim-kpi .bk-kpi__value").textContent !== b, before, { timeout: 10000 });
    const after = await page.textContent(".akim-kpi .bk-kpi__value");
    const keyAfter = await page.evaluate(() => document.activeElement && document.activeElement.getAttribute("data-key"));
    check("тихое обновление: новые числа без скелетона, фокус на той же строке",
      Number(after.replace(/\D/g, "")) === Number(before.replace(/\D/g, "")) + 1 && !sawLoading && keyAfter === key, { before, after, key, keyAfter, sawLoading });
    await page.evaluate(() => document.getElementById("akim").birgeAkim.refresh());
    await page.waitForTimeout(800);
    const st = await page.evaluate(() => document.getElementById("akim").dataset.state);
    check("тихое обновление: нет связи — числа остаются, ошибкой экран не сменяется",
      st === "ok" && (await page.textContent(".akim-kpi .bk-kpi__value")) === after, { st });
    await ctx.close();
  }

  // ───────────── 3б. Дизайн-марафон: стеклянная полоса раздела и «уменьшить движение» ─────────────
  for (const [width, height, lang] of [[1366, 768, "ru"], [375, 812, "kk"]]) {
    const { ctx, page } = await open(browser, { width, height, lang });
    await waitState(page, "ok");
    await page.waitForTimeout(400);
    const before = await page.evaluate(() => document.getElementById("akim").hasAttribute("data-scrolled"));
    await page.evaluate(() => window.scrollTo(0, 1200));
    await page.waitForTimeout(500);
    const bar = await page.evaluate(() => {
      const b = document.querySelector(".akim__bar-btn"), r = b.getBoundingClientRect();
      return { on: document.getElementById("akim").hasAttribute("data-scrolled"), op: getComputedStyle(b).opacity, top: Math.round(r.top),
               h: Math.round(r.height), tab: b.tabIndex, hidden: b.parentElement.getAttribute("aria-hidden"), text: b.textContent };
    });
    if (width === 375) await shot(page, `akim-bar-${width}-${lang}`);
    await page.click(".akim__bar-btn");
    await page.waitForTimeout(900);
    const back = await page.evaluate(() => ({ y: Math.round(window.scrollY), on: document.getElementById("akim").hasAttribute("data-scrolled") }));
    check(`${width}-${lang}: компактная полоса «${lang === "kk" ? "Күн қорытындысы" : "Картина дня"} · дата» появляется после прокрутки, нажатие — к началу`,
      !before && bar.on && bar.op === "1" && bar.top >= 0 && bar.top <= 20 && bar.h >= 44 && bar.tab === -1 && bar.hidden === "true"
        && bar.text.startsWith(lang === "kk" ? "Күн қорытындысы · " : "Картина дня · ") && back.y < 400 && !back.on, { before, bar, back });
    await ctx.close();
  }
  {
    // Правило Linear 4: быстрый ответ (80 мс) — без мигания скелетом; правило 2: ↓ / J / K по «Горячим местам».
    // Сводку сначала прогреваем: холодный расчёт на стенде (кэш 30 с) — 100–160 мс сверх 80 мс задержки, и скелет
    // появлялся бы честно — проверка же про быстрый ответ.
    await (await fetch(BASE + "/api/civic/v2/akim/summary")).text();
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru",
      route: async (route) => { await new Promise((r) => setTimeout(r, 80)); await route.continue(); } });
    let sawSkel = false;
    for (let i = 0; i < 15; i++) { if (await page.$(".akim-skel, .akim-loading")) sawSkel = true; await page.waitForTimeout(10); }
    await waitState(page, "ok");
    await page.focus(".akim-hot__item >> nth=0");
    await page.keyboard.press("ArrowDown");
    const k1 = await page.evaluate(() => Array.from(document.querySelectorAll(".akim-hot__item")).indexOf(document.activeElement));
    await page.keyboard.press("j");
    const k2 = await page.evaluate(() => Array.from(document.querySelectorAll(".akim-hot__item")).indexOf(document.activeElement));
    await page.keyboard.press("k");
    const k3 = await page.evaluate(() => Array.from(document.querySelectorAll(".akim-hot__item")).indexOf(document.activeElement));
    check("быстрый ответ — без скелета (Linear 4); ↓ / J / K по «Горячим местам» (Linear 2)", !sawSkel && k1 === 1 && k2 === 2 && k3 === 1, { sawSkel, k1, k2, k3 });
    // Правило 5: наведение на место — событие birge:hover-target {target, on, from: "akim"} (карта R07 подсвечивает значок)
    await page.evaluate(() => { window.__hv = []; document.addEventListener("birge:hover-target", (e) => window.__hv.push([e.detail.target && e.detail.target.id, e.detail.on, e.detail.from])); });
    await page.mouse.move(5, 5);
    await page.hover(".akim-hot__item >> nth=0");
    await page.mouse.move(5, 5);
    const hv = await page.evaluate(() => ({ ev: window.__hv, id: document.querySelector(".akim-hot__item").getAttribute("data-key") }));
    check("«Горячие места»: наведение — birge:hover-target on/off (from akim) для карты R07 (Linear 5)",
      hv.ev.some((e) => e[1] === true && e[2] === "akim") && hv.ev.some((e) => e[1] === false && e[2] === "akim"), hv);
    await ctx.close();
  }
  {
    // Смена района при показанных числах: без мигания скелетом — прежние приглушены, полоса загрузки, потом новые.
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru" });
    await waitState(page, "ok");
    await page.route(API, async (route) => { await new Promise((r) => setTimeout(r, 900)); await route.continue(); });
    await page.selectOption("#akim-district", "nura");
    await page.waitForTimeout(250);
    const mid = await page.evaluate(() => ({ state: document.getElementById("akim").dataset.state, pending: document.getElementById("akim").hasAttribute("data-pending"),
      kpis: document.querySelectorAll(".akim-kpi .bk-kpi__value").length, skel: document.querySelectorAll(".akim-skel").length,
      op: getComputedStyle(document.querySelector(".akim__body")).opacity }));
    await page.screenshot({ path: path.join(OUT, "akim-pending-1366-ru.png") });
    await waitState(page, "ok");
    const end = await page.evaluate(() => ({ pending: document.getElementById("akim").hasAttribute("data-pending"), meta: document.querySelector(".akim__meta").textContent }));
    check("смена района: без мигания — прежние числа приглушены, без скелета, затем новые", mid.state === "loading" && mid.pending && mid.kpis === 4
      && mid.skel === 0 && parseFloat(mid.op) < 0.6 && !end.pending && /Нура/.test(end.meta), { mid, end });
    await ctx.close();
  }
  {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.addInitScript(() => { try { localStorage.setItem("birge.lang", "ru"); } catch (e) { /* */ } });
    await page.goto(PAGE + "?lang=ru");
    await waitState(page, "ok");
    const anim = await page.evaluate(() => ({
      spark: getComputedStyle(document.querySelector(".akim-spark__line")).animationName,
      enter: Array.from(document.querySelectorAll(".akim__body > *")).map((e) => getComputedStyle(e).animationName).filter((n) => n !== "none").length,
    }));
    check("prefers-reduced-motion: графики и блоки без анимации", anim.spark === "none" && anim.enter === 0, anim);
    await ctx.close();
  }

  // ───────────── 3в. «Выбрать» вариант (волна 2 п. 5) ─────────────
  {
    // Сотрудник (стенд отдаёт CSRF в /api/civic/v1/session): выбор сохраняется на сервере и виден после перезагрузки.
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru" });
    await waitState(page, "ok");
    const card = page.locator(".akim-decision").first();
    const id = await card.getAttribute("data-key");
    const btn = card.locator(".akim-decision__choose").first();
    const label = await btn.getAttribute("aria-label");
    const n = /Вариант 2/.test(label) ? 2 : 1;
    let posted = null;
    page.on("request", (r) => { if (r.method() === "POST" && r.url().includes("/akim/decisions/")) posted = { url: r.url(), body: r.postData(), csrf: r.headers()["x-csrf-token"] }; });
    await btn.click();
    // На стенде выбор мог остаться от прошлого прогона — ждём именно «Выбран вариант n».
    await page.waitForFunction(([k, m]) => ((document.querySelector(`[data-key="${k}"] .akim-decision__chosen`) || {}).textContent || "").includes("вариант " + m), [id, n]);
    const chosen = await page.textContent(`[data-key="${id}"] .akim-decision__chosen`);
    await page.reload();
    await waitState(page, "ok");
    const after = await page.textContent(`[data-key="${id}"] .akim-decision__chosen`).catch(() => "");
    check("«Выбрать»: POST с вариантом и CSRF, «Выбран вариант N» остаётся после перезагрузки",
      posted && JSON.parse(posted.body).option === n && posted.csrf && chosen.includes(`Выбран вариант ${n}`) && after.includes(`Выбран вариант ${n}`),
      { posted, chosen, after });
    await shot(page, "akim-1366-ru-chosen");
    await ctx.close();
  }
  {
    // Житель или вход истёк: сервер ответил 403 — понятный текст, выбор не показан как сделанный.
    const { ctx, page } = await open(browser, { width: 375, height: 812, lang: "kk" });
    await page.route("**/api/civic/v2/akim/decisions/**", (route) => route.fulfill({ status: 403, json: { error: "forbidden" } }));
    await waitState(page, "ok");
    const card = page.locator(".akim-decision").last();
    await card.locator(".akim-decision__choose").first().click();
    await page.waitForFunction(() => Array.from(document.querySelectorAll(".akim-decision__status")).some((e) => e.textContent));
    const msg = await page.$$eval(".akim-decision__status", (els) => els.map((e) => e.textContent).filter(Boolean).join(" "));
    check("«Выбрать»: 403 — «Нұсқаны тек әкімдік қызметкері таңдай алады», выбор не отмечен",
      msg.includes("тек әкімдік қызметкері") && (await card.locator(".akim-decision__chosen").count()) <= 1, msg);
    await ctx.close();
  }

  // ───────────── 4. Печать ─────────────
  {
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru" });
    await waitState(page, "ok");
    await page.evaluate(() => window.dispatchEvent(new Event("beforeprint"))); // как Ctrl+P или кнопка «Распечатать»
    check("печать: перед печатью модуль помечает свою ветку страницы", await page.evaluate(() =>
      document.documentElement.classList.contains("akim-printing") && document.body.classList.contains("akim-print-path")));
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
    await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
    check("печать: после печати метки сняты", await page.evaluate(() =>
      !document.documentElement.classList.contains("akim-printing") && !document.querySelector(".akim-print-path")));
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
