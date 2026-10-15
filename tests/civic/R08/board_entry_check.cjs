/*
 * R08 · вход в Ситуационный центр из оболочки Birge R01 (раунд 15, IA_ROUND15 §3, §5.9) — на сборке R01, не на стенде R08.
 *
 *   CIVIC_DEMO=1 CIVIC_DEMO_WORLD=1 python3 app.py --port 8670                 # сборка R01 (+ поставка R08)
 *   CIVIC_STAND_PASSWORD=… NODE_PATH=$(npm root -g) node tests/civic/R08/board_entry_check.cjs [base_url] [папка_кадров]
 *
 * Проверяет: у акимата в «Ещё» есть «Ситуационный центр» (ҚАЗ — «Жағдаяттық орталық») со ссылкой на /civic/board/;
 * нажатие открывает табло; без входа — «Войдите как сотрудник» и одна кнопка; после входа сотрудника — табло с числами;
 * Ctrl+K «Ситуационный центр» → табло; адрес /#board → табло без петли «Назад»; «← В Birge» и Esc на табло → «Картина дня»
 * оболочки. Итог — board_entry.json.
 * Пароль сотрудника — только из переменной окружения (operator, как в RUN.txt R01).
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8670").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-15-results/R08/screens/world");
const USER = process.env.CIVIC_STAND_USER || "operator";
const PASSWORD = process.env.CIVIC_STAND_PASSWORD || "";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail == null ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && !ok ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
}
const LABEL = { ru: "Ситуационный центр", kk: "Жағдаяттық орталық" };

async function shell(browser, lang, state) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, storageState: state });
  await ctx.addInitScript((l) => {
    try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) { /* без хранилища */ }
  }, lang);
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push(String(e)));
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.BirgeShell && document.querySelector("#birge-header .birge-nav [data-section=more]"),
    null, { timeout: 40000 });
  await page.waitForTimeout(600);
  return { ctx, page };
}
const moreItem = (page, label) => page.evaluate((text) => {
  const items = [...document.querySelectorAll("#birge-header .birge-more-menu [role=menuitem]")];
  const it = items.find((i) => i.textContent.trim() === text);
  return { items: items.map((i) => i.textContent.trim()), href: it ? it.getAttribute("href") : null };
}, label);

(async () => {
  const browser = await chromium.launch();
  // 1. «Ещё → Ситуационный центр» (ru и kk) и переход без входа.
  for (const lang of ["ru", "kk"]) {
    const { ctx, page } = await shell(browser, lang);
    await page.click("#birge-header .birge-nav [data-section=more]");
    await page.waitForSelector("#birge-header .birge-more-menu [role=menuitem]", { timeout: 8000 });
    const it = await moreItem(page, LABEL[lang]);
    check(`${lang}: «Ещё» акимата — «${LABEL[lang]}» → /civic/board/`, /\/civic\/board\/?$/.test(it.href || ""), it);
    if (lang === "ru" && it.href) {
      await page.screenshot({ path: path.join(OUT, "entry-more-1366-ru.jpg"), type: "jpeg", quality: 84 });
      await page.click(`#birge-header .birge-more-menu [role=menuitem]:has-text("${LABEL.ru}")`);
      await page.waitForURL(/\/civic\/board\//, { timeout: 15000 });
      await page.waitForSelector(".sc[data-state]", { timeout: 20000 });
      const st = await page.getAttribute(".sc", "data-state");
      const actions = await page.$$eval(".sc-state a, .sc-state button", (els) => els.length);
      check("без входа: табло открылось, «Войдите как сотрудник» и одна кнопка", st === "forbidden" && actions === 1, { st, actions });
    }
    check(`${lang}: оболочка без ошибок на странице`, page.errs.length === 0, page.errs);
    await ctx.close();
  }
  if (!PASSWORD) {
    results.push({ name: "проверки после входа", status: "NOT_RUN", detail: "нет CIVIC_STAND_PASSWORD" });
    return finish(browser);
  }
  // 2. Вход сотрудника (сессия R02 через шлюз R01) — табло с числами; Ctrl+K; «← В Birge» и Esc.
  const login = await browser.newContext();
  const r = await login.request.post(BASE + "/api/civic/v1/session/login", { headers: { Origin: BASE }, data: { username: USER, password: PASSWORD } });
  check("вход сотрудника", r.status() === 200, r.status());
  const state = await login.storageState();
  await login.close();
  {
    const { ctx, page } = await shell(browser, "ru", state);
    await page.keyboard.press("Control+k");
    await page.waitForSelector(".birge-palette__input", { state: "visible", timeout: 8000 });
    await page.fill(".birge-palette__input", "Ситуац");
    await page.waitForTimeout(400);
    const list = await page.$$eval(".birge-palette__list > li", (els) => els.map((e) => e.textContent.trim()));
    check("Ctrl+K: «Ситуационный центр» в палитре", list.some((t) => t.includes(LABEL.ru)), list);
    await page.keyboard.press("Enter");
    const went = await page.waitForURL(/\/civic\/board\//, { timeout: 15000 }).then(() => true).catch(() => false);
    check("Ctrl+K → Enter: открылось табло", went, page.url());
    // Дальше — по самой странице табло (палитра не довела — открываем адрес страницы, чтобы проверить остальное).
    if (!went) await page.goto(BASE + "/civic/board/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".sc[data-state='ready']", { timeout: 20000 });
    const kpi = await page.$$eval(".sc-kpi__value", (els) => els.length);
    check("после входа: табло с 4 числами", kpi === 4, kpi);
    await page.click(".sc-back");
    await page.waitForFunction(() => document.body && document.body.dataset.birgeSection === "day", null, { timeout: 20000 })
      .then(() => check("«← В Birge»: «Картина дня» оболочки", true))
      .catch(() => check("«← В Birge»: «Картина дня» оболочки", false, page.url()));
    await page.goto(BASE + "/civic/board/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".sc[data-state='ready']", { timeout: 20000 });
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => document.body && document.body.dataset.birgeSection === "day", null, { timeout: 20000 })
      .then(() => check("Esc на табло: «Картина дня» оболочки", true))
      .catch(() => check("Esc на табло: «Картина дня» оболочки", false, page.url()));
    await ctx.close();
  }
  {
    // Адрес раздела #board (закладка, ссылка роли): табло, а «Назад» со страницы табло не возвращает на тот же адрес.
    const { ctx, page } = await shell(browser, "ru", state);
    await page.goto(BASE + "/#board", { waitUntil: "domcontentloaded" });
    const went = await page.waitForURL(/\/civic\/board\//, { timeout: 20000 }).then(() => true).catch(() => false);
    check("адрес /#board: открылось табло", went, page.url());
    if (went) {
      await page.waitForSelector(".sc[data-state]", { timeout: 20000 });
      await page.goBack({ waitUntil: "domcontentloaded" }).catch(() => null);
      await page.waitForTimeout(2500);
      check("«Назад» с табло: не возвращает на табло снова", !/\/civic\/board\//.test(page.url()), page.url());
    } else {
      results.push({ name: "«Назад» с табло: не возвращает на табло снова", status: "NOT_RUN", detail: "адрес /#board не открыл табло" });
    }
    await ctx.close();
  }
  return finish(browser);
})().catch((e) => { console.error(e); process.exit(2); });

async function finish(browser) {
  await browser.close();
  const fails = results.filter((r) => r.status === "FAIL").length;
  const passed = results.filter((r) => r.status === "PASS").length;
  fs.writeFileSync(path.join(OUT, "board_entry.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(),
    pass: passed, fail: fails, not_run: results.length - passed - fails, results }, null, 1));
  console.log(`\nИтог: ${passed} PASS, ${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}
