/*
 * R11 · дизайн по эталону (research/round-14/design/REFERENCE.html, вариант A): те же 4 экрана сборки, что в эталоне —
 * «Главная акимата», «Выбран объект», «Проекты и идеи» (1366×768) и «Житель, телефон» (375×812), ru.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/ref_compare.cjs http://127.0.0.1:<порт>/ <папка> <метка>
 * Кадры: <папка>/<метка>-home.png, -obj.png, -proj.png, -phone.png. Эталон снимает ref_frames.cjs (1:1, без масштаба).
 */
"use strict";
const path = require("path"), fs = require("fs");
const { chromium } = require("playwright");
const [BASE = "http://127.0.0.1:8801/", OUT = "ref", TAG = "build"] = process.argv.slice(2);
const ready = (p) => p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});

async function open(browser, w, h, mode) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript((m) => { try { localStorage.setItem("birge.lang", "ru"); localStorage.setItem("birge.mode", m); } catch (e) {} }, mode);
  const p = await ctx.newPage();
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.goto(BASE, { waitUntil: "domcontentloaded" });
  await ready(p); await p.waitForTimeout(1500);
  await p.addStyleTag({ content: "#map-status { visibility: hidden !important; }" });
  return { ctx, p };
}
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let { ctx, p } = await open(browser, 1366, 768, "akimat");
  await p.screenshot({ path: path.join(OUT, `${TAG}-home.png`) });
  const opened = await p.evaluate(() => {
    const items = [...document.querySelectorAll(".r07-item[data-key], [data-key].r07-hot__item, .r07-hot [data-key]")];
    const it = items.find((e) => /Хан Шатыр/.test(e.textContent)) || items[0];
    if (it) { it.click(); return true; } return false;
  });
  if (opened) { await p.waitForTimeout(2500); await p.screenshot({ path: path.join(OUT, `${TAG}-obj.png`) }); }
  await p.keyboard.press("Escape"); await p.waitForTimeout(500);
  await p.evaluate(() => window.BirgeShell.setSection("projects")); await p.waitForTimeout(3000);
  await p.screenshot({ path: path.join(OUT, `${TAG}-proj.png`) });
  await ctx.close();
  ({ ctx, p } = await open(browser, 375, 812, "resident"));
  await p.screenshot({ path: path.join(OUT, `${TAG}-phone.png`) });
  await ctx.close();
  await browser.close();
  console.log("кадры:", fs.readdirSync(OUT).filter((f) => f.startsWith(TAG + "-")).join(", "));
})();
