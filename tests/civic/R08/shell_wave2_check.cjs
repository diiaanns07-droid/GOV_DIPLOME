/*
 * R08 · волна 2 внутри оболочки R01 (меню по виду, разделы #day, #nearby, «Ещё → Службы»; R01 INTEGRATION §11).
 *
 *   Сборка R01 (claude/sharp-dijkstra-0t87gl ≥ a96f6e3) + R08 + патч research/round-14-results/R08/r01_wave2_r08.patch,
 *   база: init + seed-demo + seed-r14-demo + create-editor <логин> (пароль — через --password-stdin), CIVIC_DEMO=1.
 *   NODE_PATH=$(npm root -g) R08_STAFF_USER=<логин> R08_STAFF_PASS=<пароль> \
 *     node tests/civic/R08/shell_wave2_check.cjs http://127.0.0.1:8615 [папка_скриншотов]
 *
 * Проверяет: «Картина дня» в оболочке — блоки «Нужно решение акима» и «Пульс района», «Выбрать» после входа
 * сотрудника (CSRF оболочки) сохраняется; без входа — понятный отказ; «Ещё» акимата → «Службы» (registerScreen),
 * сохранение таблицы сотрудником; у жителя в меню «Рядом» → экран BirgeNearby (заголовок h2, вкладки, баннер,
 * подписка на район); 1366/375 × ru/kk без горизонтальной прокрутки и без ошибок JS. Итог — shell_wave2_check.json.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8615").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-14-results/R08/screens/shell_wave2");
const USER = process.env.R08_STAFF_USER || "";
const PASS = process.env.R08_STAFF_PASS || "";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: ok ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail != null ? " — " + JSON.stringify(detail).slice(0, 400) : ""));
}

async function open(browser, { w, h, lang, mode, hash }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && errors.push(m.text()));
  await page.addInitScript(([l, m]) => {
    try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); } catch (e) { /* */ }
  }, [lang, mode]);
  await page.goto(BASE + "/" + (hash || ""));
  return { ctx, page, errors };
}
async function login(page) {
  return page.evaluate(async ([u, p]) => {
    const r = await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" },
      credentials: "same-origin", body: JSON.stringify({ username: u, password: p }) });
    return r.status;
  }, [USER, PASS]);
}

(async () => {
  const browser = await chromium.launch();
  // 1. «Картина дня» у акимата: новые блоки и «Выбрать»
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${w}-${lang}`;
      const { ctx, page, errors } = await open(browser, { w, h, lang, mode: "akimat", hash: "#day" });
      await page.waitForSelector("#birge-day-root.akim[data-state=ok]", { timeout: 60000 });
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(OUT, `day-${tag}.png`) });
      const info = await page.evaluate(() => ({
        hscroll: document.documentElement.scrollWidth - innerWidth,
        dec: document.querySelectorAll("#birge-day-root .akim-decision").length,
        decTitleTag: (document.querySelector("#akim-decisions-title") || {}).tagName,
        pulse: !!document.querySelector("#birge-day-root .akim-pulse"),
        h1: document.querySelectorAll("#birge-day-root h1").length,  // у модуля в оболочке — h2 (h1 — у оболочки)
      }));
      check(`${tag}: «Картина дня» в оболочке — решения и пульс, заголовки модуля h2, без прокрутки вбок`,
        info.dec >= 1 && info.dec <= 3 && info.decTitleTag === "H2" && info.pulse && info.h1 === 0 && info.hscroll <= 0, info);
      check(`${tag}: без ошибок JS`, errors.length === 0, errors.slice(0, 3));
      await ctx.close();
    }
  }
  {
    const { ctx, page } = await open(browser, { w: 1366, h: 768, lang: "ru", mode: "akimat", hash: "#day" });
    await page.waitForSelector("#birge-day-root.akim[data-state=ok]", { timeout: 60000 });
    // без входа — отказ словами
    await page.click(".akim-decision__choose >> nth=0");
    await page.waitForFunction(() => Array.from(document.querySelectorAll(".akim-decision__status")).some((e) => e.textContent));
    const denied = await page.$$eval(".akim-decision__status", (els) => els.map((e) => e.textContent).join(" "));
    check("«Выбрать» без входа сотрудника — «только сотрудник акимата»", denied.includes("только сотрудник"), denied);
    if (USER && PASS) {
      const st = await login(page);
      await page.reload();
      await page.waitForSelector("#birge-day-root.akim[data-state=ok]", { timeout: 60000 });
      await page.waitForFunction(() => window.CivicShell && window.CivicShell.csrfToken && window.CivicShell.csrfToken(), null, { timeout: 15000 }).catch(() => {});
      const key = await page.getAttribute(".akim-decision >> nth=0", "data-key");
      await page.click(`[data-key="${key}"] .akim-decision__choose >> nth=0`);
      await page.waitForSelector(`[data-key="${key}"] .akim-decision__chosen`, { timeout: 10000 }).catch(() => {});
      await page.reload();
      await page.waitForSelector("#birge-day-root.akim[data-state=ok]", { timeout: 60000 });
      const chosen = await page.$eval(`[data-key="${key}"]`, (e) => (e.querySelector(".akim-decision__chosen") || {}).textContent || "");
      check("«Выбрать» после входа сотрудника — сохранено на сервере (CSRF оболочки)", st === 200 && /Выбран вариант \d/.test(chosen), { st, chosen });
      await page.screenshot({ path: path.join(OUT, "day-1366-ru-chosen.png") });
      // «Ещё» → «Службы»
      await page.goto(BASE + "/#more");
      await page.waitForSelector('[data-section="services"]', { timeout: 15000 });
      await page.click('[data-section="services"]');
      await page.waitForSelector("#birge-screen-root.svc[data-state=ok]", { timeout: 15000 });
      await page.click(".svc__details >> nth=0");
      const before = await page.$eval("#svc-roads-speed-bump", (e) => e.value);
      await page.selectOption("#svc-roads-speed-bump", before === "traffic" ? "road" : "traffic");
      await page.click(".svc__save");
      await page.waitForFunction(() => /Сохранено/.test(document.querySelector(".svc__status").textContent), null, { timeout: 10000 }).catch(() => {});
      const status = await page.textContent(".svc__status");
      check("«Ещё» → «Службы» у акимата: экран в оболочке, сохранение сотрудником", status.includes("Сохранено"), status);
      await page.screenshot({ path: path.join(OUT, "services-1366-ru.png") });
      await page.click(".svc__details >> nth=0");  // после сохранения экран перерисован — раскрыть снова
      await page.selectOption("#svc-roads-speed-bump", before);  // вернуть как было
      await page.click(".svc__save");
      await page.waitForTimeout(500);
    } else {
      check("вход сотрудника: задайте R08_STAFF_USER и R08_STAFF_PASS", false, "NOT_RUN — нет логина");
    }
    await ctx.close();
  }
  // 2. Житель: «Рядом»
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${w}-${lang}`;
      const { ctx, page, errors } = await open(browser, { w, h, lang, mode: "resident", hash: "#nearby" });
      await page.waitForSelector("#birge-screen-root.nb[data-state=ok]", { timeout: 60000 });
      await page.screenshot({ path: path.join(OUT, `nearby-${tag}.png`) });
      const info = await page.evaluate(() => ({
        hscroll: document.documentElement.scrollWidth - innerWidth,
        title: (document.querySelector("#birge-screen-root .nb__title") || {}).tagName,
        tabs: document.querySelectorAll("#birge-screen-root .nb-tabs > button").length,
        banners: document.querySelectorAll("#birge-screen-root .nb-banner").length,
        primary: document.querySelectorAll("#birge-screen-root .bk-btn--primary").length,
        nav: Array.from(document.querySelectorAll("[data-section]")).map((b) => b.getAttribute("data-section")),
      }));
      check(`${tag}: житель → «Рядом» в оболочке (h2, 4 вкладки, баннер ≤ 2, одна главная кнопка, без прокрутки вбок)`,
        info.title === "H2" && info.tabs === 4 && info.banners >= 1 && info.banners <= 2 && info.primary === 1 && info.hscroll <= 0, info);
      check(`${tag}: без ошибок JS`, errors.length === 0, errors.slice(0, 3));
      if (w === 1366 && lang === "ru") {
        await page.click('#birge-screen-root [data-key="follow"]');
        await page.waitForSelector("#birge-screen-root .nb-follow__done", { timeout: 10000 }).catch(() => {});
        check("«Следить за районом» в оболочке — подписка сохранена", !!(await page.$("#birge-screen-root .nb-follow__done")));
        await page.click('#birge-screen-root [data-key="follow"]');
      }
      await ctx.close();
    }
  }
  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "shell_wave2_check.json"), JSON.stringify({ base: BASE, total: results.length, failed, results }, null, 1));
  console.log(`\n${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
