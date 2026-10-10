/*
 * R08 · «Картина дня» внутри сборки R01 (оболочка Birge): экран и переход «горячее место → карточка цели».
 *
 *   (сервер сборки R01 с CIVIC_DEMO=1, база init + seed-demo + seed-r14-demo, см. RUN.txt R01)
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/shell_check.cjs [http://127.0.0.1:8611] [папка_скриншотов]
 *
 * Проверяет на 1366×768 и 375×812, ru и kk: раздел «Картина дня» открывается из шапки, экран R08 смонтирован
 * (4 числа, сводка), в ҚАЗ нет русских названий объектов и предложений (R10 B-018), нет ключей перевода;
 * клик по первому горячему месту открывает карту (раздел «Карта») с карточкой этой цели, число людей в карточке =
 * числу в списке, период 7 дней. Итог — shell_check.json; код выхода 1, если есть FAIL.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8611").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-14-results/R08/screens/shell");
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: ok ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (ok || detail == null ? "" : " — " + JSON.stringify(detail).slice(0, 300)));
}
const KEYLIKE = /\b(akim|common|district|cat|status|stage|object|heat|shell|dates)\.[a-z_]+(\.[a-z_0-9]+)*\b/;

(async () => {
  const api = await (await fetch(BASE + "/api/civic/v2/akim/summary")).json();
  const browser = await chromium.launch();
  for (const [width, height] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${width}-${lang}`;
      const ctx = await browser.newContext({ viewport: { width, height } });
      await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) {} }, lang);
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      // «Failed to load resource» — внешняя подложка OpenFreeMap без интернета (облако): это не ошибка кода.
      page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
      await page.goto(BASE + "/");
      await page.waitForFunction(() => window.BirgeShell && window.BirgeAkim, null, { timeout: 30000 });
      await page.evaluate(() => window.BirgeShell.setSection("day"));
      await page.waitForSelector("#birge-day-root[data-state=ok]", { timeout: 20000 });
      await page.waitForTimeout(600);
      await page.screenshot({ path: path.join(OUT, `shell-day-${tag}.png`) });
      const text = await page.evaluate(() => document.getElementById("birge-day-root").innerText);
      const nums = await page.$$eval("#birge-day-root .akim-kpi .bk-kpi__value", (els) => els.length);
      check(`${tag}: «Картина дня» смонтирована в оболочке (4 числа, сводка)`, nums === 4 && text.includes(api.text[lang].slice(0, 20)), { nums });
      check(`${tag}: нет ключей перевода`, !KEYLIKE.test(text), (text.match(KEYLIKE) || [])[0]);
      if (lang === "kk") {
        const ruOnly = [...(api.objects.late || []), ...(api.objects.stale || []), ...(api.proposals.top || [])]
          .filter((o) => o.title_ru && o.title_kk !== o.title_ru).map((o) => o.title_ru).filter((t) => text.includes(t));
        check(`${tag}: в ҚАЗ нет русских названий объектов и предложений (B-018)`, ruOnly.length === 0, ruOnly);
      }
      const hscroll = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      check(`${tag}: нет горизонтальной прокрутки`, hscroll <= 0, hscroll);
      // Горячее место → карта с карточкой цели.
      const first = api.hot.items[0];
      await page.click("#birge-day-root .akim-hot__item");
      await page.waitForFunction(() => document.body.dataset.birgeSection === "map", null, { timeout: 10000 }).catch(() => {});
      const section = await page.evaluate(() => document.body.dataset.birgeSection);
      let card = null;
      try {
        await page.waitForSelector(".r07-card__title", { timeout: 10000 });
        card = await page.evaluate(() => ({
          title: document.querySelector(".r07-card__title").textContent.trim(),
          reported: (document.querySelector(".r07-card__reported") || {}).textContent || "",
        }));
      } catch (e) { /* карточки нет */ }
      const name = first.target["label_" + lang] || first.target.label_ru;
      check(`${tag}: горячее место → карта с карточкой цели`, section === "map" && card && card.title === name, { section, card, name });
      check(`${tag}: в карточке то же число людей и 7 дней`, card && new RegExp("(^|\\D)" + first.count + "(\\D|$)").test(card.reported) && /7/.test(card.reported), card);
      await page.screenshot({ path: path.join(OUT, `shell-target-${tag}.png`) });
      check(`${tag}: без ошибок JS`, errors.length === 0, errors.slice(0, 3));
      await ctx.close();
    }
  }
  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "shell_check.json"), JSON.stringify({ base: BASE, total: results.length, failed, results }, null, 1));
  console.log(`\n${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
