/*
 * R08 · браузерная проверка Ситуационного центра (раунд 15, Playwright, Chromium).
 *
 *   python3 tests/civic/R08/demo_server.py --wave2-demo &        # http://127.0.0.1:8508 (стенд: запросы — сотрудника)
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/board_check.cjs [base_url] [папка_кадров]
 *
 * Проверяет (VISUAL_BRIEF §1 п. 4 и §4, UX_BRIEF, CONTRACT §9):
 *  - 1920×1080 и 1366×768: без прокрутки, ни один элемент не выходит за экран, ни одной строки, обрезанной по высоте;
 *  - каждый блок (слайд) по ← →: тело слайда помещается, нет ключей перевода и технических слов;
 *  - ҚАЗ: другой заголовок, нет ключей, текст не выходит за экран;
 *  - автосмена: через 15 с — следующий блок; наведение и пробел — пауза; клавиатура Tab — видна рамка фокуса;
 *  - 1024×768 и 375×812: без горизонтальной прокрутки, на телефоне все блоки подряд;
 *  - состояния: 403 «только сотрудникам» со ссылкой на вход, 503 «ещё не подключён», нет связи → ошибка и «Повторить»,
 *    нет связи после удачной загрузки → числа остаются, пометка «Нет связи — данные на …», шрифт ≥ 13 px;
 *  - prefers-reduced-motion: полоса блока без анимации;
 *  - числа совпадают с ответом akim/board (то же, что «Картина дня»).
 * Итог — board_check.json в папке кадров; код выхода 1, если есть FAIL.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8508").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-15-results/R08/screens");
const PAGE = BASE + "/civic/board/";
const API = "**/api/civic/v2/akim/board*";
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail == null ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && !ok ? " — " + JSON.stringify(detail).slice(0, 400) : ""));
}
const TECH = /ребро|граф\b|геометри|сценари|payload|undefined|NaN|\bnull\b|\btarget\b|osm-|incident|SLA\b/i;
const KEYLIKE = /\b(board|akim|common|district|status|service)\.[a-z_]+(\.[a-z_0-9]+)*\b/;

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name + ".jpg"), type: "jpeg", quality: 86 });
}

async function layoutProblems(page) {
  return page.evaluate(() => {
    const W = innerWidth, H = innerHeight, out = [];
    const se = document.scrollingElement;
    if (se.scrollHeight > H + 1) out.push("page scroll y " + se.scrollHeight);
    if (se.scrollWidth > W + 1) out.push("page scroll x " + se.scrollWidth);
    for (const el of document.querySelectorAll(".sc *")) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const st = getComputedStyle(el);
      if (st.visibility === "hidden" || el.closest("[hidden]")) continue;
      if (r.right > W + 1 || r.bottom > H + 1 || r.left < -1) { out.push("off-screen " + (el.className.baseVal ?? el.className) + " " + Math.round(r.right) + "×" + Math.round(r.bottom)); break; }
    }
    // Строки, обрезанные по высоте внутри блока (подгонка должна убирать строку целиком).
    for (const box of document.querySelectorAll(".sc-card, .sc-slide__body")) {
      const b = box.getBoundingClientRect();
      for (const row of box.querySelectorAll(".sc-row, .sc-trow, .sc-alarm, .sc-chip")) {
        const r = row.getBoundingClientRect();
        if (r.height && r.top < b.bottom - 2 && r.bottom > b.bottom + 2) { out.push("cut row in " + box.className + ": " + row.textContent.slice(0, 40)); break; }
      }
    }
    return out;
  });
}
async function textProblems(page) {
  const text = await page.evaluate(() => document.querySelector(".sc").innerText);
  const out = [];
  const tech = text.match(TECH);
  if (tech) out.push("tech word: " + tech[0]);
  const key = text.match(KEYLIKE);
  if (key) out.push("raw key: " + key[0]);
  return out;
}
async function minFont(page) {
  return page.evaluate(() => {
    let min = 99, where = "";
    for (const el of document.querySelectorAll(".sc *")) {
      if (!el.childNodes.length || ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
      const r = el.getBoundingClientRect();
      if (!r.width) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < min) { min = fs; where = el.className; }
    }
    return { min, where };
  });
}

async function openBoard(browser, viewport, opts = {}) {
  const ctx = await browser.newContext({ viewport, reducedMotion: opts.reducedMotion || "no-preference" });
  if (opts.lang) await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) {} }, opts.lang);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  if (opts.clock) await page.clock.install();
  if (opts.route) await page.route(API, opts.route);
  await page.goto(PAGE + (opts.query || ""), { waitUntil: "domcontentloaded" });
  return { ctx, page, errors };
}

(async () => {
  const browser = await chromium.launch();
  const api = await (await fetch(BASE + "/api/civic/v2/akim/board")).json();

  // ── большой экран, ru и kk, все блоки ──
  for (const [w, h] of [[1920, 1080], [1366, 768]]) {
    for (const lang of ["ru", "kk"]) {
      const { ctx, page, errors } = await openBoard(browser, { width: w, height: h }, { lang });
      await page.waitForSelector(".sc[data-state='ready']", { timeout: 20000 });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(300);
      const tag = `${w}-${lang}`;
      const title = await page.textContent(".sc-title");
      check(`${tag}: заголовок на своём языке`, lang === "ru" ? /Ситуационный центр/.test(title) : /Жағдаяттық орталық/.test(title), title);
      check(`${tag}: без прокрутки и выхода за экран`, (await layoutProblems(page)).length === 0, await layoutProblems(page));
      check(`${tag}: нет ключей и технических слов`, (await textProblems(page)).length === 0, await textProblems(page));
      const font = await minFont(page);
      check(`${tag}: шрифт не меньше 13 px`, font.min >= 13, font);
      if (lang === "ru") {
        const kpi = await page.$$eval(".sc-kpi__value", (els) => els.map((e) => e.textContent.replace(/\s/g, "")));
        const want = ["new_day", "in_progress", "overdue", "fixed_week"].map((k) => String(api.kpi[k].value));
        check(`${tag}: 4 числа = ответ akim/board`, JSON.stringify(kpi) === JSON.stringify(want), { kpi, want });
      }
      await shot(page, `board-${tag}`);
      const n = (api.slides || []).length;
      const seen = [];
      for (let i = 0; i < n; i++) {
        const id = await page.getAttribute(".sc-slide", "data-slide");
        seen.push(id);
        const bodyFits = await page.evaluate(() => { const b = document.querySelector(".sc-slide__body"); return b.scrollHeight <= b.clientHeight + 1; });
        const probs = (await layoutProblems(page)).concat(await textProblems(page));
        check(`${tag}: блок «${id}» помещается и без ключей`, bodyFits && probs.length === 0, { bodyFits, probs });
        if (w === 1366 || i === 0) await shot(page, `board-${tag}-${String(i + 1).padStart(2, "0")}-${id}`);
        await page.keyboard.press("ArrowRight");
        await page.waitForTimeout(260);
      }
      check(`${tag}: ← → проходят все блоки по кругу`, seen.join() === (api.slides || []).join() &&
        (await page.getAttribute(".sc-slide", "data-slide")) === api.slides[0], { seen, slides: api.slides });
      check(`${tag}: без ошибок в консоли`, errors.length === 0, errors);
      await ctx.close();
    }
  }

  // ── автосмена, пауза, клавиатура ──
  {
    const { ctx, page } = await openBoard(browser, { width: 1366, height: 768 }, { clock: true });
    await page.waitForSelector(".sc[data-state='ready']", { timeout: 20000 });
    const first = await page.getAttribute(".sc-slide", "data-slide");
    await page.clock.runFor(15500);
    const second = await page.getAttribute(".sc-slide", "data-slide");
    check("автосмена: через 15 с — следующий блок", first !== second && second === api.slides[1], { first, second });
    await page.hover(".sc-stage");
    check("наведение — пауза", (await page.getAttribute(".sc", "data-paused")) === "yes");
    await page.clock.runFor(31000);
    check("на паузе блок не меняется", (await page.getAttribute(".sc-slide", "data-slide")) === second);
    await page.mouse.move(5, 5);
    check("мышь ушла — снова идёт", (await page.getAttribute(".sc", "data-paused")) === "no");
    await page.keyboard.press(" ");
    check("пробел — пауза", (await page.getAttribute(".sc", "data-paused")) === "yes" &&
      (await page.getAttribute(".sc-pause", "aria-pressed")) === "true");
    await page.keyboard.press(" ");
    check("пробел ещё раз — дальше", (await page.getAttribute(".sc", "data-paused")) === "no");
    // Tab: рамка фокуса видна
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    const focus = await page.evaluate(() => { const el = document.activeElement; const s = getComputedStyle(el); return { tag: el.tagName, outline: s.outlineStyle, w: s.outlineWidth }; });
    check("Tab: видна рамка фокуса", focus.outline !== "none" && parseFloat(focus.w) >= 2, focus);
    // Вкладка-сегмент с клавиатуры останавливает показ и ведёт на блок
    await page.focus(".sc-tab:nth-child(3)");
    await page.keyboard.press("Enter");
    check("сегмент: Enter открывает блок, фокус — пауза", (await page.getAttribute(".sc-slide", "data-slide")) === api.slides[2] &&
      (await page.getAttribute(".sc", "data-paused")) === "yes");
    await ctx.close();
  }

  // ── 1024 и телефон ──
  for (const [w, h, lang] of [[1024, 768, "ru"], [375, 812, "ru"], [375, 812, "kk"]]) {
    const { ctx, page, errors } = await openBoard(browser, { width: w, height: h }, { lang });
    await page.waitForSelector(".sc[data-state='ready']", { timeout: 20000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);
    const sx = await page.evaluate(() => document.scrollingElement.scrollWidth <= innerWidth + 1);
    check(`${w}-${lang}: без горизонтальной прокрутки`, sx);
    check(`${w}-${lang}: нет ключей и технических слов`, (await textProblems(page)).length === 0, await textProblems(page));
    if (w === 1024) check(`${w}: без прокрутки и выхода за экран`, (await layoutProblems(page)).length === 0, await layoutProblems(page));
    if (w === 375) {
      const blocks = await page.$$eval(".sc-all .sc-slide", (els) => els.map((e) => e.getAttribute("data-slide")));
      check(`375-${lang}: все блоки подряд`, blocks.join() === (api.slides || []).join(), blocks);
      await page.screenshot({ path: path.join(OUT, `board-375-${lang}-full.jpg`), type: "jpeg", quality: 82, fullPage: true });
    }
    await shot(page, `board-${w}-${lang}`);
    check(`${w}-${lang}: без ошибок в консоли`, errors.length === 0, errors);
    await ctx.close();
  }

  // ── состояния ──
  const states = [
    ["403", (r) => r.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ error: "forbidden" }) }), /сотрудникам акимата/, "a.sc-btn--primary"],
    ["503", (r) => r.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "module_not_ready" }) }), /ещё не подключён/, "a.sc-btn"],
    ["offline", (r) => r.abort(), /Не удалось загрузить/, "button.sc-btn--primary"],
  ];
  for (const [name, route, text, action] of states) {
    const { ctx, page } = await openBoard(browser, { width: 1366, height: 768 }, { route });
    await page.waitForSelector(`.sc[data-state='${name === "403" ? "forbidden" : name === "503" ? "not_ready" : "error"}']`, { timeout: 20000 });
    const body = await page.textContent(".sc-state");
    check(`состояние ${name}: понятный текст и действие`, text.test(body) && !!(await page.$(".sc-state " + action)), body);
    await shot(page, `board-state-${name}`);
    await ctx.close();
  }
  {
    // Удачная загрузка, потом нет связи: числа остаются, пометка «Нет связи — данные на …»
    let fail = false;
    const { ctx, page } = await openBoard(browser, { width: 1366, height: 768 }, {
      route: (r) => (fail ? r.abort() : r.continue()) });
    await page.waitForSelector(".sc[data-state='ready']", { timeout: 20000 });
    fail = true;
    await page.evaluate(() => window.__board.refresh());
    await page.waitForFunction(() => document.querySelector(".sc").getAttribute("data-stale") === "yes", null, { timeout: 10000 });
    const kpiLeft = await page.$$eval(".sc-kpi__value", (els) => els.length);
    const label = await page.textContent(".sc-updated");
    check("нет связи после загрузки: числа на месте и «Нет связи — данные на …»", kpiLeft === 4 && /Нет связи/.test(label), label);
    await shot(page, "board-state-stale");
    await ctx.close();
  }
  {
    const { ctx, page } = await openBoard(browser, { width: 1366, height: 768 }, { reducedMotion: "reduce" });
    await page.waitForSelector(".sc[data-state='ready']", { timeout: 20000 });
    const anim = await page.$eval(".sc-tab[aria-selected='true'] .sc-tab__bar", (el) => getComputedStyle(el).animationName);
    check("prefers-reduced-motion: полоса блока без анимации", anim === "none", anim);
    await ctx.close();
  }

  await browser.close();
  const fails = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "board_check.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(),
    pass: results.length - fails, fail: fails, results }, null, 1));
  console.log(`\nИтог: ${results.length - fails} PASS, ${fails} FAIL`);
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
