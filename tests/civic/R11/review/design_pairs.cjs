/*
 * R11 · дизайн-марафон: кадры «до/после» для правок ui-kit (одни и те же состояния, одинаковые размеры).
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/design_pairs.cjs http://127.0.0.1:<порт>/ <папка> <метка: before|after>
 * Состояния: легенда-строка с «?» (1366, ru — вырезка), «Рядом» — отключение (375, kk), «Обращения» без входа (375, kk),
 * мастер жалобы шаг 3 (375, ru), карта акимата (1366 ru, 375 kk), «Картина дня» (375 kk).
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const [BASE = "http://127.0.0.1:8752/", OUT = "design", TAG = "after"] = process.argv.slice(2);

const ready = (p) => p.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
  && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).then(() => p.waitForTimeout(1200));

async function open(browser, w, h, lang, mode) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript(([l, m]) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); } catch (e) {} }, [lang, mode]);
  const p = await ctx.newPage();
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.goto(BASE, { waitUntil: "domcontentloaded" });
  await ready(p).catch(() => {});
  // плашка о запасном фоне карты гаснет сама — для одинаковых кадров убираем сразу
  await p.addStyleTag({ content: "#map-status { visibility: hidden !important; }" });
  return { ctx, p };
}
const shot = (p, name, clip) => p.screenshot({ path: path.join(OUT, `${name}-${TAG}.png`), clip });
const section = (p, id) => p.evaluate((sid) => window.BirgeShell.setSection(sid), id).then(() => p.waitForTimeout(2600));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let { ctx, p } = await open(browser, 1366, 768, "ru", "akimat");
  await shot(p, "map-akimat-1366-ru");
  const lg = await p.$(".birge-legend-line, .bk-legend--line");
  if (lg) { const b = await lg.boundingBox(); await shot(p, "legend-1366-ru", { x: Math.max(0, b.x - 12), y: Math.max(0, b.y - 12), width: b.width + 24, height: b.height + 24 }); }
  await ctx.close();
  ({ ctx, p } = await open(browser, 375, 812, "kk", "akimat"));
  await shot(p, "map-akimat-375-kk");
  await section(p, "day"); await shot(p, "day-375-kk");
  await p.evaluate(() => window.BirgeShell.setSection("map")); await p.waitForTimeout(600);
  await section(p, "inbox"); await shot(p, "inbox-login-375-kk");
  await ctx.close();
  ({ ctx, p } = await open(browser, 375, 812, "kk", "resident"));
  await section(p, "nearby"); await shot(p, "nearby-375-kk");
  await ctx.close();
  ({ ctx, p } = await open(browser, 375, 812, "ru", "resident"));
  const fab = await p.$(".bc-fab");
  if (fab) {
    await fab.click(); await p.waitForTimeout(1500);
    // шаг 1 категория → шаг 2 место → шаг 3 текст: идём кнопками мастера, как житель
    for (let i = 0; i < 2; i++) {
      const pick = await p.$(".bc-panel [data-step] .bk-option, .bc-panel .bk-option, .bc-panel [role=radio]");
      if (pick) { await pick.click().catch(() => {}); await p.waitForTimeout(500); }
      const next = await p.$(".bc-panel .bk-btn--primary");
      if (next) { await next.click().catch(() => {}); await p.waitForTimeout(1200); }
    }
    await shot(p, "wizard-375-ru");
  }
  await ctx.close();
  await browser.close();
  console.log("кадры:", fs.readdirSync(OUT).filter((f) => f.endsWith(`-${TAG}.png`)).join(", "));
})();
