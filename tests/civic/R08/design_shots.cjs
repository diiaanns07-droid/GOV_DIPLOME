/*
 * R08 · дизайн-марафон: кадры экранов R08 в сборке R01 во всех состояниях — для «до/после» по чек-листу
 * research/round-14/DESIGN_MARATHON.md.
 *
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/design_shots.cjs http://127.0.0.1:8640 <папка> [префикс]
 *
 * Кадры: <префикс>-<экран>-<состояние>-<ширина>-<язык>.png
 *   «Картина дня» (#day, акимат): ok — первый экран и лист целиком (-full), loading, empty, error;
 *   «Рядом» (#nearby, житель): ok, error; «Службы» («Ещё → Службы», акимат): ok.
 * Лист целиком снимается, растянув #birge-day / #birge-screen на высоту содержимого (только для кадра).
 * Сеть наружу закрыта: карта — локальная подложка сборки или запасной фон.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8640").replace(/\/$/, "");
const OUT = process.argv[3] || "design-shots";
const PRE = process.argv[4] || "shot";
const ONLY = (process.env.R08_SHOTS || "").split(",").filter(Boolean); // например R08_SHOTS=day-ok,nearby-ok
fs.mkdirSync(OUT, { recursive: true });

async function open(browser, { w, h, lang, mode, hash, route }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  if (route) await page.route(route.url, route.handler);
  await page.addInitScript(([l, m]) => {
    try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); } catch (e) { /* */ }
  }, [lang, mode]);
  await page.goto(BASE + "/" + hash);
  return { ctx, page };
}
async function full(page, sheet, file) {
  await page.evaluate((sel) => {
    const s = document.querySelector(sel);
    s.dataset.r08Shot = s.getAttribute("style") || "";
    const hgt = s.scrollHeight;
    s.style.cssText += `;position:absolute;bottom:auto;height:${hgt}px;max-height:none;overflow:visible`;
    document.documentElement.style.height = "auto";
    document.body.style.height = hgt + 200 + "px";
  }, sheet);
  await page.waitForTimeout(300);
  await page.screenshot({ path: file, fullPage: true });
  await page.evaluate((sel) => {
    const s = document.querySelector(sel);
    s.setAttribute("style", s.dataset.r08Shot);
    document.documentElement.style.height = "";
    document.body.style.height = "";
  }, sheet);
}
const want = (k) => !ONLY.length || ONLY.includes(k);

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  let summary = null;
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${w}-${lang}`;
      // «Картина дня» — ok
      if (want("day-ok")) {
        const { ctx, page } = await open(browser, { w, h, lang, mode: "akimat", hash: "#day" });
        await page.waitForSelector("#birge-day-root.akim[data-state=ok]", { timeout: 60000 });
        if (!summary) summary = await page.evaluate(async () => (await fetch("/api/civic/v2/akim/summary")).json());
        await page.waitForTimeout(900);
        await page.screenshot({ path: path.join(OUT, `${PRE}-day-ok-${tag}.png`) });
        await full(page, "#birge-day", path.join(OUT, `${PRE}-day-ok-${tag}-full.png`));
        await ctx.close();
      }
      // «Картина дня» — загрузка (ответ задержан)
      if (want("day-loading")) {
        const { ctx, page } = await open(browser, { w, h, lang, mode: "akimat", hash: "#day",
          route: { url: "**/api/civic/v2/akim/summary**", handler: () => { /* не отвечаем — видна загрузка */ } } });
        await page.waitForSelector("#birge-day-root.akim[data-state=loading]", { timeout: 60000 });
        await page.waitForTimeout(600);
        await page.screenshot({ path: path.join(OUT, `${PRE}-day-loading-${tag}.png`) });
        await ctx.close();
      }
      // «Картина дня» — ошибка сети
      if (want("day-error")) {
        const { ctx, page } = await open(browser, { w, h, lang, mode: "akimat", hash: "#day",
          route: { url: "**/api/civic/v2/akim/summary**", handler: (r) => r.abort() } });
        await page.waitForSelector("#birge-day-root.akim[data-state=error]", { timeout: 60000 });
        await page.waitForTimeout(400);
        await page.screenshot({ path: path.join(OUT, `${PRE}-day-error-${tag}.png`) });
        await ctx.close();
      }
      // «Картина дня» — тихий день (всё пусто)
      if (want("day-empty") && summary) {
        const e = JSON.parse(JSON.stringify(summary));
        for (const k of ["new_day", "new_week", "in_progress", "overdue", "fixed_week"])
          if (e.kpi[k]) Object.assign(e.kpi[k], { value: 0, prev: 0, abs: 0, rel: 0, trend: "flat", series: e.kpi[k].series ? e.kpi[k].series.map(() => 0) : undefined });
        e.kpi.in_progress.waiting = 0;
        e.hot.items = []; e.topics.items = []; e.topics.total = 0;
        (e.districts.items || []).forEach((d) => Object.assign(d, { value: 0, prev: 0, abs: 0, trend: "flat" }));
        e.main_problem = null; e.empty = true;
        e.decisions = { available: true, items: [], count: 0, demo: false };
        e.pulse = { available: true, items: [], base_weeks: 4 };
        e.overdue = { count: 0, places: 0, items: [], top: 5 };
        Object.assign(e.objects, { late: [], stale: [], late_count: 0, stale_count: 0 });
        Object.assign(e.proposals, { top: [], new_count: 0, open_count: 0 });
        e.text_parts = { ru: [{ role: "new", text: "Сегодня новых обращений нет." }], kk: [{ role: "new", text: "Бүгін жаңа өтініш жоқ." }] };
        const { ctx, page } = await open(browser, { w, h, lang, mode: "akimat", hash: "#day",
          route: { url: "**/api/civic/v2/akim/summary**", handler: (r) => r.fulfill({ json: e }) } });
        await page.waitForSelector("#birge-day-root.akim[data-state=ok]", { timeout: 60000 });
        await page.waitForTimeout(600);
        await page.screenshot({ path: path.join(OUT, `${PRE}-day-empty-${tag}.png`) });
        await ctx.close();
      }
      // «Рядом» — ok и ошибка
      if (want("nearby-ok")) {
        const { ctx, page } = await open(browser, { w, h, lang, mode: "resident", hash: "#nearby" });
        await page.waitForSelector("#birge-screen-root.nb[data-state=ok]", { timeout: 60000 });
        await page.waitForTimeout(600);
        await page.screenshot({ path: path.join(OUT, `${PRE}-nearby-ok-${tag}.png`) });
        await full(page, "#birge-screen", path.join(OUT, `${PRE}-nearby-ok-${tag}-full.png`));
        await ctx.close();
      }
      if (want("nearby-error")) {
        const { ctx, page } = await open(browser, { w, h, lang, mode: "resident", hash: "#nearby",
          route: { url: "**/api/civic/v2/nearby?**", handler: (r) => r.abort() } });
        await page.waitForSelector("#birge-screen-root.nb[data-state=error]", { timeout: 60000 });
        await page.waitForTimeout(400);
        await page.screenshot({ path: path.join(OUT, `${PRE}-nearby-error-${tag}.png`) });
        await ctx.close();
      }
      // «Службы» — ok (через «Ещё»)
      if (want("services-ok")) {
        const { ctx, page } = await open(browser, { w, h, lang, mode: "akimat", hash: "" });
        await page.waitForSelector("#birge-header", { timeout: 60000 });
        await page.waitForTimeout(1500);
        const moreBtn = await page.$('.birge-nav [data-section="more"]');
        if (moreBtn && (await moreBtn.isVisible())) {
          await moreBtn.click();
          await page.click('.birge-more-menu [data-section="services"]');
        } else {
          await page.evaluate(() => { location.hash = "#services"; });
        }
        await page.waitForSelector("#birge-screen-root.svc[data-state=ok]", { timeout: 30000 }).catch(() => null);
        await page.waitForTimeout(600);
        await page.screenshot({ path: path.join(OUT, `${PRE}-services-ok-${tag}.png`) });
        await ctx.close();
      }
      console.log("готово", tag);
    }
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
