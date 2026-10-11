/*
 * R08 · браузерная проверка экрана «Службы» (волна мелочей п. 7): web/civic/akim/services.html.
 *
 *   python tests/civic/R08/demo_server.py --kit-dir <папка R11> &
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/services_check.cjs [base_url] [папка_скриншотов]
 *
 * 1366×768 и 375×812, ru/kk: нет горизонтальной прокрутки, ключей перевода и предупреждений, зоны нажатия ≥ 44 px,
 * одна главная кнопка; смена службы у уточнения → «Сохранить» (PUT + CSRF) → «Сохранено», после перезагрузки
 * видно «изменено акиматом»; 403 — понятный текст. Итог — services_check.json; код выхода 1, если есть FAIL.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8508").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-14-results/R08/screens");
const PAGE = BASE + "/civic/akim/services.html";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: ok ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail != null ? " — " + JSON.stringify(detail) : ""));
}
const KEYLIKE = /\b(services|service|subtopic|common|cat)\.[a-z_]+\b/;

(async () => {
  const browser = await chromium.launch();
  for (const [w, hh] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${w}-${lang}`;
      const page = await browser.newPage({ viewport: { width: w, height: hh } });
      const logs = [];
      page.on("console", (m) => ["warning", "error"].includes(m.type()) && logs.push(m.text()));
      page.on("pageerror", (e) => logs.push(e.message));
      await page.goto(PAGE + "?lang=" + lang);
      await page.waitForSelector(".svc[data-state=ok]");
      await page.click(".svc__details >> nth=0");
      await page.screenshot({ path: path.join(OUT, `services-${tag}.png`) });
      const info = await page.evaluate(() => ({
        hscroll: document.documentElement.scrollWidth - innerWidth,
        text: document.body.innerText,
        cats: document.querySelectorAll(".svc__cat").length,
        primary: document.querySelectorAll(".bk-btn--primary").length,
        tiny: Array.from(document.querySelectorAll(".svc select, .svc button, .svc summary"))
          .filter((e) => e.getClientRects().length && e.getBoundingClientRect().height < 44).map((e) => e.className || e.tagName),
        labels: Array.from(document.querySelectorAll(".svc select")).every((s) => document.querySelector(`label[for="${s.id}"]`)),
      }));
      check(`${tag}: нет горизонтальной прокрутки`, info.hscroll <= 0, info.hscroll);
      check(`${tag}: 12 категорий, у каждого поля есть подпись`, info.cats === 12 && info.labels, info.cats);
      check(`${tag}: одна главная кнопка`, info.primary === 1, info.primary);
      check(`${tag}: нет ключей перевода и предупреждений`, !KEYLIKE.test(info.text) && logs.length === 0, [(info.text.match(KEYLIKE) || [])[0], logs]);
      check(`${tag}: зоны нажатия ≥ 44 px`, info.tiny.length === 0, info.tiny);
      check(`${tag}: названия служб — из словаря R11`, lang === "kk" ? info.text.includes("Жол қызметі") : info.text.includes("Дорожная служба"));
      await page.close();
    }
  }
  {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await page.goto(PAGE + "?lang=ru");
    await page.waitForSelector(".svc[data-state=ok]");
    await page.click(".svc__details >> nth=0");
    let put = null;
    page.on("request", (r) => r.method() === "PUT" && (put = { body: r.postData(), csrf: r.headers()["x-csrf-token"] }));
    await page.selectOption("#svc-roads-marking", "road");
    await page.click(".svc__save");
    await page.waitForFunction(() => document.querySelector(".svc__status").textContent === "Сохранено");
    await page.reload();
    await page.waitForSelector(".svc[data-state=ok]");
    await page.click(".svc__details >> nth=0");
    const value = await page.$eval("#svc-roads-marking", (s) => s.value);
    const edited = await page.$$eval(".svc__subs .svc__edited", (els) => els.length);
    check("сохранение: PUT только изменённой строки с CSRF, после перезагрузки — новая служба и «изменено акиматом»",
      put && JSON.parse(put.body).rules["roads/marking"] === "road" && Object.keys(JSON.parse(put.body).rules).length === 1 && put.csrf && value === "road" && edited >= 1,
      { put, value, edited });
    await page.screenshot({ path: path.join(OUT, "services-1366-ru-saved.png") });
    // вернуть как было: «Служба светофоров и разметки»
    await page.selectOption("#svc-roads-marking", "traffic");
    await page.click(".svc__save");
    await page.waitForFunction(() => document.querySelector(".svc__status").textContent === "Сохранено");
    await page.close();
  }
  {
    const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
    await page.route("**/api/civic/v2/akim/routing", (route) =>
      route.request().method() === "PUT" ? route.fulfill({ status: 403, json: { error: "forbidden" } }) : route.continue());
    await page.goto(PAGE + "?lang=kk");
    await page.waitForSelector(".svc[data-state=ok]");
    await page.selectOption("#svc-yards", "akimat");
    await page.click(".svc__save");
    await page.waitForFunction(() => document.querySelector(".svc__status").textContent.length > 0);
    const msg = await page.textContent(".svc__status");
    check("403: «Кестені тек әкімдік қызметкері өзгерте алады»", msg.includes("тек әкімдік қызметкері"), msg);
    await page.close();
  }
  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "services_check.json"), JSON.stringify({ base: BASE, total: results.length, failed, results }, null, 1));
  console.log(`\n${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
