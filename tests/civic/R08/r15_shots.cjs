/*
 * R08 · раунд 15 · кадры «Картины дня» 2.0 и «Картины недели» для R14 и «книги экранов» R11 (Playwright, Chromium).
 *
 *   python tests/civic/R08/demo_server.py --wave2-demo &            # http://127.0.0.1:8508 (соседи — фикстуры R08)
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/r15_shots.cjs [base_url] [папка_кадров]
 *
 * «Картина дня»: 1366×768, 1024×768, 375×812 × ru / kk — первый экран и блок раунда 15 (три карточки + прогноз),
 * проверка: нет горизонтальной прокрутки, у тревоги кризиса — «Открыть кризисный штаб», 3 карточки со ссылками на
 * разделы (#agencies, #together, #meetings), на телефоне новые блоки — после «Пульса». «Картина недели»: экран 1366
 * и печать A4 ru / kk — ровно 2 листа. Итог — r15_shots.json; код выхода 1, если есть FAIL.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8508").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-15-results/R08/screens");
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail == null ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && !ok ? " — " + JSON.stringify(detail).slice(0, 500) : ""));
}

(async () => {
  const browser = await chromium.launch();
  for (const [w, hgt] of [[1366, 768], [1024, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `day-${w}-${lang}`;
      const ctx = await browser.newContext({ viewport: { width: w, height: hgt }, deviceScaleFactor: 1 });
      const page = await ctx.newPage();
      await page.goto(BASE + "/civic/akim/?lang=" + lang, { waitUntil: "networkidle" });
      await page.waitForSelector('#akim[data-state="ok"]', { timeout: 20000 });
      await page.waitForTimeout(500);
      const info = await page.evaluate(() => {
        const r = (s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; };
        return {
          hscroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          crisis: Array.from(document.querySelectorAll(".akim-pulse__crisis")).map((a) => a.getAttribute("href")),
          cards: Array.from(document.querySelectorAll(".akim-r15-card")).map((c) => [c.getAttribute("data-block"), c.querySelector(".akim-r15-card__open").getAttribute("href")]),
          pulseBottom: (r(".akim-pulse") || {}).bottom, r15Top: (r(".akim-r15") || {}).top,
          week: (document.querySelector(".akim__week") || {}).href || null,
        };
      });
      check(`${tag}: без горизонтальной прокрутки`, info.hscroll <= 0, info.hscroll);
      check(`${tag}: у тревоги про снег — «Открыть кризисный штаб» (#agencies/crisis=…)`, info.crisis.length >= 1 && info.crisis.every((x) => /#agencies\/crisis=/.test(x)), info.crisis);
      check(`${tag}: три карточки «Ведомства · Жители вместе · Встречи» → разделы`,
        info.cards.map((c) => c[0]).join() === "agencies,together,meetings" && info.cards.every((c) => /^\/#(agencies|together|meetings)/.test(c[1])), info.cards);
      check(`${tag}: новые блоки — после «Пульса»`, info.r15Top != null && info.pulseBottom != null && info.r15Top >= info.pulseBottom - 1, info);
      await page.screenshot({ path: path.join(OUT, `${tag}-first.jpg`), type: "jpeg", quality: 82 });
      const box = await page.$(".akim-r15");
      if (box) {
        await box.scrollIntoViewIfNeeded();
        await page.waitForTimeout(150);
        await page.screenshot({ path: path.join(OUT, `${tag}-r15.jpg`), type: "jpeg", quality: 82 });
      }
      await ctx.close();
    }
  }
  // «Картина недели»: экран и печать
  for (const lang of ["ru", "kk"]) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.goto(BASE + "/civic/akim/week.html?lang=" + lang, { waitUntil: "networkidle" });
    await page.waitForSelector('#week[data-state="ok"]', { timeout: 20000 });
    await page.waitForTimeout(400);
    const sheets = await page.evaluate(() => document.querySelectorAll(".wk-sheet").length);
    check(`week-${lang}: два листа на экране`, sheets === 2, sheets);
    await page.screenshot({ path: path.join(OUT, `week-1366-${lang}.jpg`), type: "jpeg", quality: 82, fullPage: true });
    await page.emulateMedia({ media: "print" });
    const pdf = await page.pdf({ format: "A4", printBackground: true, preferCSSPageSize: true });
    const pages = (pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
    fs.writeFileSync(path.join(OUT, `week-a4-${lang}.pdf`), pdf);
    check(`week-${lang}: печать — ровно 2 листа A4`, pages === 2, pages);
    await ctx.close();
  }
  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "r15_shots.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(), passed: results.length - failed, failed, results }, null, 2));
  console.log(`\n${results.length - failed} PASS · ${failed} FAIL`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
