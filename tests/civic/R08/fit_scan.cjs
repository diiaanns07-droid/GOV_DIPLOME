/*
 * R08 · скан порогов VISUAL_BRIEF §4 на сборке R01 (после входа сотрудника): текст не мельче 13 px (решение владельца
 * 12 окт, R10 B-112), контраст текста ≥ 4,5:1 (крупный ≥ 3:1), зоны нажатия ≥ 44 px, нет текста, обрезанного
 * многоточием (казахский не обрезан). Экраны R08: Ситуационный центр, «Картина недели», «Картина дня» и сводка
 * «Сегодня в Астане» в оболочке (вид акимата).
 *
 *   CIVIC_STAND_PASSWORD=… NODE_PATH=$(npm root -g) node tests/civic/R08/fit_scan.cjs [base_url]
 *
 * Контраст — к фону самого элемента и его предков, наложенных по порядку на белый (лист оболочки — плотное стекло над
 * светлой картой; у Ситуационного центра фон страницы тёмный и непрозрачный). Итог —
 * research/round-15-results/R08/screens/world/fit_scan.json; код выхода 1, если что-то нашлось
 * (знак «B» в шапке листа — не текст, не считается).
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const SCREENS = [
  { url: "/civic/board/index.html", w: 1366, h: 768, lang: "kk", root: "body", ready: ".sc[data-state='ready']" },
  { url: "/civic/board/index.html", w: 1920, h: 1080, lang: "ru", root: "body", ready: ".sc[data-state='ready']" },
  { url: "/civic/akim/week.html", w: 1366, h: 900, lang: "kk", root: "body", ready: ".wk[data-state='ok']" },
  { url: "/civic/akim/week.html", w: 375, h: 812, lang: "ru", root: "body", ready: ".wk[data-state='ok']" },
  { url: "/#day", w: 1366, h: 900, lang: "ru", mode: "akimat", root: "#birge-day-root", ready: "#birge-day-root .akim-kpi" },
  { url: "/#day", w: 375, h: 812, lang: "kk", mode: "akimat", root: "#birge-day-root", ready: "#birge-day-root .akim-kpi" },
  { url: "/", w: 1366, h: 768, lang: "kk", mode: "akimat", root: "#birge-today", ready: "#birge-today .akim-today__kpi" },
];

(async () => {
  const B = (process.argv[2] || "http://127.0.0.1:8660").replace(/\/$/, "");
  const report = [];
  const browser = await chromium.launch();
  const login = await browser.newContext();
  await login.request.post(B + "/api/civic/v1/session/login", { headers: { Origin: B }, data: { username: "operator", password: process.env.CIVIC_STAND_PASSWORD } });
  const state = await login.storageState(); await login.close();
  for (const s of SCREENS) {
    const ctx = await browser.newContext({ viewport: { width: s.w, height: s.h }, storageState: state });
    await ctx.addInitScript((o) => {
      try { localStorage.setItem("birge.lang", o.lang); if (o.mode) localStorage.setItem("birge.mode", o.mode); } catch (e) { /* без хранилища */ }
    }, { lang: s.lang, mode: s.mode || null });
    const page = await ctx.newPage();
    await page.goto(B + s.url, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(s.ready, { timeout: 40000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(900);
    const res = await page.evaluate((rootSel) => {
      const parse = (c) => {
        const m = String(c).match(/rgba?\(([^)]+)\)/);
        if (!m) return [255, 255, 255, 0];
        const p = m[1].split(",").map(Number);
        return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
      };
      const over = (a, b) => [0, 1, 2].map((i) => a[i] * a[3] + b[i] * (1 - a[3])).concat([1]);
      const lum = (c) => {
        const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
        return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
      };
      const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
      const small = [], tiny = [], clipped = [], low = [];
      const root = document.querySelector(rootSel);
      for (const el of root.querySelectorAll("*")) {
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.display === "none" || el.closest(".bk-sr-only, [hidden]")) continue;
        const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
        const label = (typeof el.className === "string" ? el.className : "") + ":" + el.textContent.trim().slice(0, 20);
        const fsz = parseFloat(cs.fontSize);
        if (own && fsz < 13 && !el.closest("svg")) small.push(label + ":" + cs.fontSize);
        if ((el.tagName === "BUTTON" || el.tagName === "A" || el.tagName === "SELECT") && (r.height < 44 || r.width < 44)) {
          tiny.push((typeof el.className === "string" ? el.className : "") + ":" + Math.round(r.width) + "x" + Math.round(r.height) + ":" + el.textContent.trim().slice(0, 16));
        }
        if (own && cs.textOverflow === "ellipsis" && el.scrollWidth > el.clientWidth) clipped.push(el.textContent.trim().slice(0, 30));
        if (own && !el.closest("svg") && +cs.opacity > 0) {
          const chain = [];
          for (let p = el; p; p = p.parentElement) chain.push(parse(getComputedStyle(p).backgroundColor));
          let bg = [255, 255, 255, 1];
          for (const c of chain.reverse()) if (c[3] > 0) bg = over(c, bg);
          const k = ratio(over(parse(cs.color), bg), bg);
          const big = fsz >= 24 || (fsz >= 18.66 && +cs.fontWeight >= 700);
          if (k < (big ? 3 : 4.5)) low.push(label + ":" + k.toFixed(2));
        }
      }
      return { small: small.slice(0, 8), tiny: tiny.slice(0, 10), clipped: clipped.slice(0, 8), low: low.slice(0, 8) };
    }, s.root);
    res.small = res.small.filter((x) => !x.startsWith("wk-brand__mark"));
    res.low = res.low.filter((x) => !x.startsWith("wk-brand__mark"));
    report.push({ page: s.url, root: s.root, size: s.w + "x" + s.h, lang: s.lang, ...res });
    const bad = res.small.length || res.tiny.length || res.clipped.length || res.low.length;
    console.log((bad ? "FAIL " : "PASS ") + s.url + " " + s.w + " " + s.lang + " " + JSON.stringify(res));
    await ctx.close();
  }
  await browser.close();
  const bad = report.filter((r) => r.small.length || r.tiny.length || r.clipped.length || r.low.length).length;
  const out = path.join(__dirname, "../../../research/round-15-results/R08/screens/world/fit_scan.json");
  fs.writeFileSync(out, JSON.stringify({ base: B, at: new Date().toISOString(), pass: report.length - bad, fail: bad, report }, null, 1));
  console.log(`\nИтог: ${report.length - bad} PASS, ${bad} FAIL`);
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
