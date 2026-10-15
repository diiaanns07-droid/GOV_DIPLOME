/*
 * R08 · браузерная проверка «Картины недели» (раунд 15, Playwright, Chromium).
 *
 *   python3 tests/civic/R08/demo_server.py --wave2-demo &        # http://127.0.0.1:8508 (стенд: запросы — сотрудника)
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/week_check.cjs [base_url] [папка_кадров]
 *
 * Проверяет: лист открывается на ru и kk, нет ключей перевода и технических слов, 4 числа = ответ akim/week, 7 дней
 * на графике (будущие дни идущей недели — пустые), «Последние 7 дней / Неделей раньше» меняет неделю и адрес, нажата
 * кнопка своего окна (с датой из «Картины дня» — ни одна), печать — 1–2 листа A4
 * (ru, kk, прошлая неделя), 403 — «для сотрудников» и «← Картина дня», нет связи — «Повторить», на телефоне без
 * горизонтальной прокрутки, в «Картине дня» есть ссылка «Картина недели» с районом. Итог — week_check.json.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8508").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-15-results/R08/screens");
const PAGE = BASE + "/civic/akim/week.html";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail == null ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && !ok ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
}
const TECH = /undefined|NaN|\bnull\b|payload|\btarget\b|osm-|SLA\b/i;
const KEYLIKE = /\b(week|akim|common|district|status|service)\.[a-z_]+(\.[a-z_0-9]+)*\b/;

function pdfPages(file) {
  return (fs.readFileSync(file).toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
}
const todayAstana = () => new Date(Date.now() + 5 * 3600 * 1000).toISOString().slice(0, 10);
function shiftDay(iso, days) {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
const pressed = (page) => page.$$eval(".wk-weeks button", (els) => els.map((e) => e.getAttribute("aria-pressed")));

async function open(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1366, height: 900 } });
  if (opts.lang) await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) {} }, opts.lang);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  if (opts.route) await page.route("**/api/civic/v2/akim/week*", opts.route);
  await page.goto(PAGE + (opts.query || ""), { waitUntil: "domcontentloaded" });
  return { ctx, page, errors };
}

(async () => {
  const browser = await chromium.launch();
  const api = await (await fetch(BASE + "/api/civic/v2/akim/week")).json();

  for (const lang of ["ru", "kk"]) {
    const { ctx, page, errors } = await open(browser, { lang });
    await page.waitForSelector(".wk[data-state='ok']", { timeout: 20000 });
    await page.evaluate(() => document.fonts.ready);
    const text = await page.evaluate(() => document.querySelector(".wk-sheet").innerText);
    check(`${lang}: заголовок на своём языке`, lang === "ru" ? /Картина недели/.test(text) : /Апта қорытындысы/.test(text));
    check(`${lang}: нет ключей и технических слов`, !KEYLIKE.test(text) && !TECH.test(text), (text.match(KEYLIKE) || text.match(TECH) || [])[0]);
    const kpi = await page.$$eval(".wk-kpi__value", (els) => els.map((e) => e.textContent.replace(/\s/g, "")));
    const want = [api.kpi.new.value, api.kpi.fixed.value, api.kpi.in_progress.value, api.kpi.overdue.value].map(String);
    check(`${lang}: 4 числа = ответ akim/week`, JSON.stringify(kpi) === JSON.stringify(want), { kpi, want });
    const days = await page.$$eval(".wk-chart__day", (els) => els.length);
    const future = await page.$$eval(".wk-chart__future", (els) => els.length);
    const expectFuture = api.week.current ? 7 - api.week.days_counted : 0;
    check(`${lang}: 7 дней, будущие пустые`, days === 7 && future === expectFuture, { days, future, expectFuture });
    await page.screenshot({ path: path.join(OUT, `week-1366-${lang}.jpg`), type: "jpeg", quality: 84, fullPage: true });
    await page.emulateMedia({ media: "print" });
    const pdf = path.join(OUT, `week-${lang}.pdf`);
    await page.pdf({ path: pdf, format: "A4", printBackground: true });
    const pages = pdfPages(pdf);
    check(`${lang}: печать — 1–2 листа A4`, pages >= 1 && pages <= 2, pages);
    check(`${lang}: без ошибок в консоли`, errors.length === 0, errors);
    await ctx.close();
  }

  {
    const { ctx, page } = await open(browser, {});
    await page.waitForSelector(".wk[data-state='ok']", { timeout: 20000 });
    await page.click(".wk-weeks button:nth-child(2)");
    await page.waitForFunction(() => /date=/.test(location.search) && document.querySelector(".wk").getAttribute("data-state") === "ok", null, { timeout: 15000 });
    const title = await page.textContent(".wk-title");
    check("«Прошлая неделя»: другая неделя и дата в адресе", !title.includes(api.week.label_ru) || !api.week.current, title);
    check("«Неделей раньше»: нажата она, а не «Последние 7 дней»", JSON.stringify(await pressed(page)) === "[\"false\",\"true\"]",
      await pressed(page));
    await page.emulateMedia({ media: "print" });
    const pdf = path.join(OUT, "week-ru-past.pdf");
    await page.pdf({ path: pdf, format: "A4", printBackground: true });
    check("прошлая неделя: печать — 1–2 листа A4", pdfPages(pdf) <= 2, pdfPages(pdf));
    await ctx.close();
  }
  {
    // Из «Картины дня» с другим днём (week.html?date=…): окно — 7 дней до этого дня, ни одна кнопка не нажата;
    // «Последние 7 дней» возвращает к сегодняшнему окну и убирает дату из адреса.
    const day = shiftDay(todayAstana(), -3);
    const { ctx, page } = await open(browser, { query: "?date=" + day });
    await page.waitForSelector(".wk[data-state='ok']", { timeout: 20000 });
    check("дата из «Картины дня»: ни «Последние 7 дней», ни «Неделей раньше» не нажаты",
      JSON.stringify(await pressed(page)) === "[\"false\",\"false\"]", { day, pressed: await pressed(page) });
    await page.click(".wk-weeks button:nth-child(1)");
    await page.waitForFunction(() => !/date=/.test(location.search) && document.querySelector(".wk").getAttribute("data-state") === "ok", null, { timeout: 15000 });
    check("«Последние 7 дней»: нажата, дата ушла из адреса", JSON.stringify(await pressed(page)) === "[\"true\",\"false\"]",
      await pressed(page));
    await ctx.close();
  }
  for (const [name, route, re, sel] of [
    ["403", (r) => r.fulfill({ status: 403, contentType: "application/json", body: "{\"error\":\"forbidden\"}" }), /для сотрудников/, "a.bk-btn"],
    ["offline", (r) => r.abort(), /Не удалось загрузить/, "button.bk-btn"],
  ]) {
    const { ctx, page } = await open(browser, { route });
    await page.waitForSelector(`.wk[data-state='${name === "403" ? "forbidden" : "error"}']`, { timeout: 20000 });
    const body = await page.textContent(".wk-sheet");
    check(`состояние ${name}: текст и одно действие`, re.test(body) && !!(await page.$(".wk-sheet " + sel)), body);
    await page.screenshot({ path: path.join(OUT, `week-state-${name}.jpg`), type: "jpeg", quality: 84 });
    await ctx.close();
  }
  {
    const { ctx, page } = await open(browser, { viewport: { width: 375, height: 812 }, lang: "kk" });
    await page.waitForSelector(".wk[data-state='ok']", { timeout: 20000 });
    const sx = await page.evaluate(() => document.scrollingElement.scrollWidth <= innerWidth + 1);
    check("375-kk: без горизонтальной прокрутки", sx);
    await page.screenshot({ path: path.join(OUT, "week-375-kk.jpg"), type: "jpeg", quality: 80, fullPage: true });
    await ctx.close();
  }
  {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(BASE + "/civic/akim/?district=nura", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".akim-week-link", { timeout: 20000 });
    const href = await page.getAttribute(".akim-week-link", "href");
    check("«Картина дня» → «Картина недели» с районом", /week\.html\?district=nura/.test(href), href);
    await ctx.close();
  }
  await browser.close();
  const fails = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "week_check.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(),
    pass: results.length - fails, fail: fails, results }, null, 1));
  console.log(`\nИтог: ${results.length - fails} PASS, ${fails} FAIL`);
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
