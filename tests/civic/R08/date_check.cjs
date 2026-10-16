/*
 * R08 · поле даты «Картины дня» на сборке R01 в англоязычном окружении (поправка П3, кадр координатора 03).
 *
 *   CIVIC_STAND_PASSWORD=… NODE_PATH=$(npm root -g) node tests/civic/R08/date_check.cjs [base_url] [папка]
 *
 * <input type=date> Chromium рисует по языку системы, а не страницы: в облаке (ролик R10, кадры координатора) поле
 * показывало «10/16/2026». Поверх поля R08 выводит дату «дд.мм.гггг» из его значения; в фокусе — само поле (правка
 * с клавиатуры, календарь браузера). Браузер запускается с LANG=en_US — как облачный ролик. Проверяет 1366 / 1024 / 375
 * × ru / kk × обычный вид и ?show=1: дата поверх совпадает со значением поля и лежит внутри поля левее значка календаря,
 * текст самого поля прозрачный; в фокусе наложение скрыто; ошибок страницы нет. Итог — date_check.json в папке.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8660").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-15-results/R08/screens/world/date-p3");
const USER = process.env.CIVIC_STAND_USER || "operator";
const PASSWORD = process.env.CIVIC_STAND_PASSWORD || "";
const SHOTS = new Set(["1366-ru", "1024-kk-show", "375-kk"]); // кадры только для части видов — остальное проверяется числами
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail == null ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && !ok ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
}
function finish() {
  const pass = results.filter((r) => r.status === "PASS").length;
  const fail = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "date_check.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(), lang_env: "en_US.UTF-8", pass, fail, results }, null, 1));
  console.log(`\nИтог: ${pass} PASS, ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
}

(async () => {
  if (!PASSWORD) {
    results.push({ name: "поле даты после входа", status: "NOT_RUN", detail: "нет CIVIC_STAND_PASSWORD" });
    return finish();
  }
  const browser = await chromium.launch({ env: { ...process.env, LANG: "en_US.UTF-8", LC_ALL: "en_US.UTF-8" } });
  const login = await browser.newContext();
  const r = await login.request.post(BASE + "/api/civic/v1/session/login", { headers: { Origin: BASE }, data: { username: USER, password: PASSWORD } });
  check("вход сотрудника", r.ok(), r.status());
  const state = await login.storageState();
  await login.close();

  for (const [w, hgt] of [[1366, 768], [1024, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      for (const show of ["", "?show=1"]) {
        const tag = `${w} ${lang}${show ? " ?show=1" : ""}`;
        const name = `${w}-${lang}${show ? "-show" : ""}`;
        const ctx = await browser.newContext({ viewport: { width: w, height: hgt }, storageState: state, locale: "en-US", deviceScaleFactor: w === 375 ? 2 : 1 });
        await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) {} }, lang);
        const page = await ctx.newPage();
        const errors = [];
        page.on("pageerror", (e) => errors.push(String(e)));
        await page.goto(BASE + "/" + show + "#day", { waitUntil: "domcontentloaded" });
        await page.waitForSelector("#akim-date", { timeout: 30000 });
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(600);
        const st = await page.evaluate(() => {
          const i = document.querySelector("#akim-date");
          const t = document.querySelector(".akim__date-text");
          const ib = i.getBoundingClientRect();
          const tb = t ? t.getBoundingClientRect() : null;
          return {
            value: i.value,
            text: t ? t.textContent : null,
            shown: !!t && getComputedStyle(t).display !== "none",
            input_color: getComputedStyle(i).color,
            // внутри поля и левее значка календаря (24 px справа)
            inside: !!tb && tb.left >= ib.left && tb.right <= ib.right - 24 && tb.top >= ib.top && tb.bottom <= ib.bottom,
          };
        });
        const want = st.value ? st.value.slice(8, 10) + "." + st.value.slice(5, 7) + "." + st.value.slice(0, 4) : "?";
        check(`${tag}: дата поверх поля — «${want}», внутри поля, текст поля прозрачный`,
          st.shown && st.inside && st.text === want && /rgba\(0, 0, 0, 0\)|transparent/.test(st.input_color), st);
        const box = await page.$(".akim__controls");
        if (box && SHOTS.has(name)) await box.screenshot({ path: path.join(OUT, `date-${name}.png`) });
        await page.focus("#akim-date");
        await page.waitForTimeout(150);
        const f = await page.evaluate(() => ({
          shown: getComputedStyle(document.querySelector(".akim__date-text")).display !== "none",
          input_color: getComputedStyle(document.querySelector("#akim-date")).color,
        }));
        check(`${tag}: в фокусе — само поле, наложение скрыто`, !f.shown && !/rgba\(0, 0, 0, 0\)/.test(f.input_color), f);
        if (box && name === "1366-ru") await box.screenshot({ path: path.join(OUT, `date-${name}-focus.png`) });
        check(`${tag}: без ошибок страницы`, errors.length === 0, errors);
        await ctx.close();
      }
    }
  }
  await browser.close();
  finish();
})().catch((e) => {
  check("запуск", false, String(e && e.stack || e));
  finish();
});
