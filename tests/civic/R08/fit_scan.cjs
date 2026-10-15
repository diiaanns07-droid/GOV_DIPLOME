/*
 * R08 · скан порогов VISUAL_BRIEF §4 на сборке (Ситуационный центр и «Картина недели», после входа сотрудника):
 * текст не мельче 13 px, зоны нажатия ≥ 44 px, нет текста, обрезанного многоточием (казахский не обрезан).
 *
 *   CIVIC_STAND_PASSWORD=… NODE_PATH=$(npm root -g) node tests/civic/R08/fit_scan.cjs [base_url]
 *
 * Итог — research/round-15-results/R08/screens/world/fit_scan.json; код выхода 1, если что-то нашлось
 * (знак «B» в шапке листа — не текст, не считается).
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
(async () => {
  const B = (process.argv[2] || "http://127.0.0.1:8660").replace(/\/$/, "");
  const report = [];
  const browser = await chromium.launch();
  const login = await browser.newContext();
  await login.request.post(B + "/api/civic/v1/session/login", { headers: { Origin: B }, data: { username: "operator", password: process.env.CIVIC_STAND_PASSWORD } });
  const state = await login.storageState(); await login.close();
  for (const [url, w, h, lang] of [["/civic/board/index.html", 1366, 768, "kk"], ["/civic/board/index.html", 1920, 1080, "ru"], ["/civic/akim/week.html", 1366, 900, "kk"], ["/civic/akim/week.html", 375, 812, "ru"]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, storageState: state });
    await ctx.addInitScript((l) => { localStorage.setItem("birge.lang", l); }, lang);
    const page = await ctx.newPage();
    await page.goto(B + url, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-state='ready'], [data-state='ok']", { timeout: 20000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(800);
    const res = await page.evaluate(() => {
      const small = [], tiny = [], clipped = [];
      for (const el of document.querySelectorAll("body *")) {
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.display === "none") continue;
        const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
        if (own && parseFloat(cs.fontSize) < 13 && !el.closest("svg")) small.push(el.className + ":" + cs.fontSize + ":" + el.textContent.trim().slice(0, 20));
        if ((el.tagName === "BUTTON" || el.tagName === "A" || el.tagName === "SELECT") && (r.height < 44 || r.width < 44)) tiny.push(el.className + ":" + Math.round(r.width) + "x" + Math.round(r.height) + ":" + el.textContent.trim().slice(0, 16));
        if (own && cs.textOverflow === "ellipsis" && el.scrollWidth > el.clientWidth + 1) clipped.push(el.textContent.trim().slice(0, 30));
      }
      return { small: small.slice(0, 8), tiny: tiny.slice(0, 10), clipped: clipped.slice(0, 8) };
    });
    res.small = res.small.filter((x) => !x.startsWith("wk-brand__mark"));
    report.push({ page: url, size: w + "x" + h, lang, ...res });
    console.log((res.small.length || res.tiny.length || res.clipped.length ? "FAIL " : "PASS ") + url + " " + w + " " + lang + " " + JSON.stringify(res));
    await ctx.close();
  }
  await browser.close();
  const bad = report.filter((r) => r.small.length || r.tiny.length || r.clipped.length).length;
  const out = path.join(__dirname, "../../../research/round-15-results/R08/screens/world/fit_scan.json");
  fs.writeFileSync(out, JSON.stringify({ base: B, at: new Date().toISOString(), pass: report.length - bad, fail: bad, report }, null, 1));
  console.log(`\nИтог: ${report.length - bad} PASS, ${bad} FAIL`);
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
