/*
 * R08 · сводка «Сегодня в Астане» (web/civic/akim/today.js) против эталона research/round-14/design/REFERENCE.html,
 * вариант A, «Главная акимата» (.sum). Стенд: python tests/civic/R08/demo_server.py --kit-dir <R11> --wave2-demo
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/today_check.cjs http://127.0.0.1:8508 [папка_кадров]
 *
 * Проверяет 1366/375 × ru/kk: размеры как в эталоне (карточка 388 × ~325, поля 16/18, заголовок 15/600, плитки 22/600 +
 * подпись 12, строка места 54 с плашкой 34×26 и названием 14/500, «Все горячие места» 14/500), числа и места = ответ
 * /akim/summary (новые, в работе, просрочено, 3 первых горячих места); × и Esc закрывают; строка — событие
 * birge:open-target, наведение — birge:hover-target, «Все горячие места» — birge:open-hot-list; ↑↓/J K по местам;
 * быстрый ответ — без скелета, долгий — скелет через 150 мс; ошибка — строка и «Повторить»; зоны нажатия ≥ 44;
 * без прокрутки вбок и без ключей вместо слов. Итог — today_check.json.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8508").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-14-results/R08/reference/today");
const PAGE = BASE + "/civic/akim/today.html";
const API = "**/api/civic/v2/akim/summary*";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: ok ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail != null ? " — " + JSON.stringify(detail).slice(0, 400) : ""));
}
async function open(browser, { w, h, lang, route }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  const logs = [];
  page.on("console", (m) => (m.type() === "warning" || m.type() === "error") && !/Failed to load resource/.test(m.text()) && logs.push(m.text()));
  page.on("pageerror", (e) => logs.push(e.message));
  if (route) await page.route(API, route);
  await page.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) { /* */ } }, lang);
  await page.goto(PAGE + "?lang=" + lang);
  return { ctx, page, logs };
}

(async () => {
  const browser = await chromium.launch();
  let api = null;
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${w}-${lang}`;
      const { ctx, page, logs } = await open(browser, { w, h, lang });
      await page.waitForSelector("#today[data-state=ok]", { timeout: 20000 });
      if (!api) api = await page.evaluate(async () => (await fetch("/api/civic/v2/akim/summary")).json());
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(OUT, `today-${tag}.png`) });
      const m = await page.evaluate(() => {
        const card = document.getElementById("today"), r = card.getBoundingClientRect();
        const q = (s) => { const e = card.querySelector(s); if (!e) return null; const c = getComputedStyle(e), b = e.getBoundingClientRect();
          return { fs: c.fontSize, fw: c.fontWeight, h: Math.round(b.height), w: Math.round(b.width), x: Math.round(b.left - r.left), y: Math.round(b.top - r.top) }; };
        const tiny = Array.from(card.querySelectorAll("a, button")).filter((e) => e.getClientRects().length).map((e) => { const b = e.getBoundingClientRect(); return [e.className, Math.round(b.width), Math.round(b.height)]; }).filter(([, bw, bh]) => bh < 44);
        return { card: { w: Math.round(r.width), h: Math.round(r.height), radius: getComputedStyle(card).borderTopLeftRadius, glass: card.classList.contains("bk-glass") },
          title: q(".akim-today__h h2"), kpi: q(".akim-today__kpi"), num: q(".akim-today__kpi b"), label: q(".akim-today__kpi span"), row: q(".akim-today__row"), cnt: q(".akim-today__cnt"),
          name: q(".akim-today__name"), more: q(".akim-today__more"),
          nums: Array.from(card.querySelectorAll(".akim-today__kpi b")).map((e) => e.textContent),
          rows: Array.from(card.querySelectorAll(".akim-today__row")).map((a) => a.getAttribute("data-key")),
          text: card.innerText, tiny, hscroll: document.documentElement.scrollWidth - innerWidth };
      });
      const kk = lang === "kk";
      check(`${tag}: карточка как в эталоне — ${w < 500 ? "во всю ширину" : "388"}, радиус 18, стекло ui-kit`,
        (w < 500 ? m.card.w >= 340 : m.card.w === 388) && m.card.radius === "18px" && m.card.glass
          && (Math.abs(m.card.h - 325) <= 12 || (w < 500 && kk && m.card.h <= 360)), m.card); // kk на 375: подпись плитки в 2 строки
      check(`${tag}: заголовок 15/600 «${kk ? "Бүгін Астанада" : "Сегодня в Астане"}», поля 16/18`,
        m.title && m.title.fs === "15px" && m.title.fw === "600" && m.title.x === 18 && m.title.y === 16 && m.text.startsWith(kk ? "Бүгін Астанада" : "Сегодня в Астане"), m.title);
      check(`${tag}: три плитки — число 22/600, подпись 12, плитка 66 высотой (kk на телефоне — может в 2 строки)`,
        m.num.fs === "22px" && m.num.fw === "600" && m.label.fs === "12px" && (m.kpi.h === 66 || (w < 500 && kk && m.kpi.h <= 86)), [m.kpi, m.num, m.label]);
      const k = api.kpi;
      check(`${tag}: числа = /akim/summary (новые сегодня, в работе, просрочено)`,
        JSON.stringify(m.nums.map((s) => s.replace(/\s/g, ""))) === JSON.stringify([k.new_day.value, k.in_progress.value, k.overdue.value].map(String)), [m.nums, k.new_day.value, k.in_progress.value, k.overdue.value]);
      const want = api.hot.items.slice(0, 3).map((it) => "today:" + it.target.kind + ":" + it.target.id);
      check(`${tag}: три горячих места = первые три /akim/summary hot`, JSON.stringify(m.rows) === JSON.stringify(want), m.rows);
      check(`${tag}: строка места 54, плашка 34×26, название 14/500, «Все горячие места» 14/500`,
        m.row.h === 54 && m.cnt.w === 34 && m.cnt.h === 26 && m.name.fs === "14px" && m.name.fw === "500" && m.more && m.more.fs === "14px" && m.more.fw === "500", [m.row, m.cnt, m.name, m.more]);
      check(`${tag}: зоны нажатия ≥ 44, без прокрутки вбок, без ключей и предупреждений`,
        m.tiny.length === 0 && m.hscroll <= 0 && !/akim\.today\.|common\./.test(m.text) && logs.length === 0, [m.tiny, m.hscroll, logs.slice(0, 2)]);
      if (w === 1366 && lang === "ru") {
        // события и клавиатура
        await page.evaluate(() => {
          window.__ev = [];
          ["birge:open-target", "birge:hover-target", "birge:open-hot-list", "birge:today-close"].forEach((n) =>
            document.addEventListener(n, (e) => { window.__ev.push([n, e.detail && e.detail.target ? e.detail.target.id : null, e.detail && e.detail.on]); if (n !== "birge:hover-target" && n !== "birge:today-close") e.preventDefault(); }));
        });
        await page.hover(".akim-today__row >> nth=0");
        await page.click(".akim-today__row >> nth=1");
        await page.click(".akim-today__more");
        const ev = await page.evaluate(() => ({ ev: window.__ev, hash: location.hash }));
        check("строка: наведение — birge:hover-target, нажатие — birge:open-target (оболочка открывает цель), «Все горячие места» — birge:open-hot-list",
          ev.ev.some((e) => e[0] === "birge:hover-target" && e[2] === true) && ev.ev.some((e) => e[0] === "birge:open-target" && e[1] === api.hot.items[1].target.id)
            && ev.ev.some((e) => e[0] === "birge:open-hot-list") && ev.hash === "", ev);
        await page.focus(".akim-today__row >> nth=0");
        await page.keyboard.press("ArrowDown");
        const a1 = await page.evaluate(() => document.activeElement.getAttribute("data-key"));
        await page.keyboard.press("j");
        const a2 = await page.evaluate(() => document.activeElement.getAttribute("data-key"));
        await page.keyboard.press("k");
        const a3 = await page.evaluate(() => document.activeElement.getAttribute("data-key"));
        check("клавиатура: ↓ и J — следующее место, K — предыдущее", a1 === want[1] && a2 === want[2] && a3 === want[1], [a1, a2, a3]);
        await page.keyboard.press("Escape");
        const closed = await page.evaluate(() => ({ hidden: document.getElementById("today").hidden, ev: window.__ev.some((e) => e[0] === "birge:today-close") }));
        check("Esc закрывает карточку (событие birge:today-close)", closed.hidden && closed.ev, closed);
      }
      await ctx.close();
    }
  }
  // Загрузка: быстрый ответ — без скелета; долгий — скелет через 150 мс. Ошибка — строка и «Повторить».
  {
    const { ctx, page } = await open(browser, { w: 1366, h: 768, lang: "ru", route: async (r) => { await new Promise((x) => setTimeout(x, 80)); await r.continue(); } });
    let sawSkel = false;
    for (let i = 0; i < 12; i++) { if (await page.$("#today .bk-skel")) sawSkel = true; await page.waitForTimeout(10); }
    await page.waitForSelector("#today[data-state=ok]");
    check("быстрый ответ (80 мс) — без мигания скелетом", !sawSkel, sawSkel);
    await ctx.close();
  }
  {
    const { ctx, page } = await open(browser, { w: 1366, h: 768, lang: "ru", route: async (r) => { await new Promise((x) => setTimeout(x, 900)); await r.continue(); } });
    await page.waitForTimeout(400);
    const skel = await page.$$eval("#today .bk-skel", (e) => e.length);
    await page.screenshot({ path: path.join(OUT, "today-loading-1366-ru.png") });
    await page.waitForSelector("#today[data-state=ok]");
    check("долгий ответ — скелет трёх плиток (после 150 мс)", skel >= 3, skel);
    await ctx.close();
  }
  {
    const { ctx, page } = await open(browser, { w: 375, h: 812, lang: "kk", route: (r) => r.abort() });
    await page.waitForSelector("#today[data-state=error]");
    const t = await page.evaluate(() => ({ text: document.querySelector(".akim-today__error").innerText, btn: document.querySelector(".akim-today__retry").getBoundingClientRect().height }));
    await page.screenshot({ path: path.join(OUT, "today-error-375-kk.png") });
    check("ошибка — одна строка «Қорытынды жүктелмеді · Қайталау», кнопка ≥ 44", /Қорытынды жүктелмеді/.test(t.text) && /Қайталау/.test(t.text) && t.btn >= 44, t);
    await ctx.close();
  }
  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "today_check.json"), JSON.stringify({ base: BASE, total: results.length, failed, results }, null, 1));
  console.log(`\n${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
