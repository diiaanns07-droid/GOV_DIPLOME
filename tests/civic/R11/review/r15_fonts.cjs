/*
 * R11 · сколько размеров шрифта на экране (VISUAL_BRIEF §4 п. 3: «не больше 3 размеров шрифта на экране»).
 *
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r15_fonts.cjs <BASE> <OUT.json> <файл-пароля> [--widths 1366,375] [--lang ru]
 *
 * Разделы — как у r15_screens.cjs. На каждый экран: размеры шрифта видимого текста в области экрана (без шапки оболочки),
 * сколько знаков каждым размером и какие классы его дают. Размер, которым набрано меньше 3 % знаков экрана, — «редкий»:
 * обычно это лишний шаг шкалы (14 рядом с 13, 16 рядом с 15). Ничего не нажимает, данные не меняет.
 */
"use strict";
const fs = require("fs");
const { chromium } = require("playwright");

const [BASE, OUT, PWFILE] = process.argv.slice(2);
if (!BASE || !OUT || !PWFILE) { console.error("node r15_fonts.cjs <BASE> <OUT.json> <файл-пароля> [--widths 1366,375] [--lang ru]"); process.exit(2); }
const args = process.argv.slice(5);
const WIDTHS = (args.includes("--widths") ? args[args.indexOf("--widths") + 1] : "1366,375").split(",").map(Number);
const LANG = args.includes("--lang") ? args[args.indexOf("--lang") + 1] : "ru";
// --css файл.css — вставить стиль поверх сборки (проверить правку роли до её поставки); --only yard,together — только эти разделы
const CSS = args.includes("--css") ? fs.readFileSync(args[args.indexOf("--css") + 1], "utf8") : "";
const ONLY = args.includes("--only") ? args[args.indexOf("--only") + 1].split(",") : null;
const PASSWORD = fs.readFileSync(PWFILE, "utf8").trim();
const ROUTES = {
  resident: ["map", "mine", "yard", "together", "meetings", "ideas", "crisis"],
  akimat: ["day", "inbox", "agencies", "agencies/joint", "agencies/handoffs", "agencies/calendar", "agencies/crisis",
    "together", "meetings", "analyst"],
};

(async () => {
  const browser = await chromium.launch();
  const report = { base: BASE, when: new Date().toISOString(), lang: LANG, screens: {} };
  for (const w of WIDTHS) for (const mode of ["resident", "akimat"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w <= 480 ? 812 : 768 }, deviceScaleFactor: 1, locale: LANG === "kk" ? "kk-KZ" : "ru-RU" });
    await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); localStorage.setItem("birge.i18n.lang", l); } catch (e) { /* приватный режим */ } }, [mode, LANG]);
    const page = await ctx.newPage();
    await page.goto(BASE + "/");
    if (mode === "akimat") {
      await page.evaluate(async (pw) => { await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "operator", password: pw }) }); }, PASSWORD);
    }
    for (const route of ROUTES[mode]) {
      if (ONLY && !ONLY.includes(route)) continue;
      await page.goto(BASE + "/#" + route);
      await page.waitForTimeout(2500);
      if (CSS) { await page.addStyleTag({ content: CSS }); await page.waitForTimeout(200); }
      const res = await page.evaluate(() => {
        const scope = [...document.querySelectorAll("#birge-screen:not([hidden]), #birge-day:not([hidden]), #birge-alert, .bk-notify")];
        if (!scope.length) scope.push(document.querySelector("#civic-root") || document.body);
        const sizes = {};
        const seen = new Set();
        for (const root of scope) for (const e of root.querySelectorAll("*")) {
          if (seen.has(e) || e.closest("svg, canvas, .maplibregl-map, [aria-hidden=true], .bk-sr-only, #birge-header")) continue; seen.add(e);
          if (!e.getClientRects().length) continue;
          const cs = getComputedStyle(e);
          if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) continue;
          const r = e.getBoundingClientRect();
          if (r.width <= 2 || r.height <= 2 || r.bottom < 0 || r.top > innerHeight * 2) continue;  // до двух экранов вниз
          const own = [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.nodeValue).join("").replace(/\s+/g, " ").trim();
          if (!own) continue;
          const px = Math.round(parseFloat(cs.fontSize) * 2) / 2;
          const cls = ((e.className && e.className.toString().split(/\s+/)[0]) || e.tagName.toLowerCase()).slice(0, 32);
          const s = sizes[px] || (sizes[px] = { chars: 0, classes: {} });
          s.chars += own.length; s.classes[cls] = (s.classes[cls] || 0) + own.length;
        }
        return sizes;
      });
      const total = Object.values(res).reduce((a, s) => a + s.chars, 0) || 1;
      const list = Object.entries(res).map(([px, s]) => ({ px: +px, chars: s.chars, share: +(s.chars / total).toFixed(3),
        classes: Object.entries(s.classes).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([c, n]) => c + " " + n) })).sort((a, b) => b.px - a.px);
      const tag = `${w}-${mode}-${route.replace("/", "_")}`;
      report.screens[tag] = { sizes: list.length, rare: list.filter((x) => x.share < 0.03).map((x) => x.px), list };
      console.log(`${tag}: ${list.length} размеров — ` + list.map((x) => `${x.px}px ${Math.round(x.share * 100)}%`).join(", "));
    }
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(report, null, 1));
})().catch((e) => { console.error(e); process.exit(2); });
