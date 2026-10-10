/*
 * R11 · UX-разбор карты R12: скриншоты стенда R12 на 1366 и 375 + замеры (шрифт < 14 px, кнопки < 48 px,
 * горизонтальная прокрутка). Стенд и данные — из ветки R12 (запускается их serve.mjs), этот скрипт только смотрит.
 *   (в worktree R12) python3 -B tests/civic/R12/map/make_streets_fixture.py && node tests/civic/R12/map/serve.mjs 8771 &
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r12_map_shots.cjs http://127.0.0.1:8771 <папка-скриншотов>
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const [base, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const STREETS = "/tests/civic/R12/map/fixtures/.generated/streets_demo_area.json";

async function measure(page) {
  return page.evaluate(() => {
    const vis = (el) => { const b = el.getBoundingClientRect(); const s = getComputedStyle(el); return b.width > 0 && b.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
    const small = {}, low = [];
    document.querySelectorAll("#civic-public *").forEach((el) => {
      if (!vis(el)) return;
      const own = Array.from(el.childNodes).some((c) => c.nodeType === 3 && c.textContent.trim());
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (own && fs < 14) { const k = fs + "px"; (small[k] = small[k] || []).push(el.textContent.trim().slice(0, 40)); }
      if (el.matches("button,a[href],[role=button]")) {
        const b = el.getBoundingClientRect();
        if (b.height < 47.5 || b.width < 40) low.push(Math.round(b.width) + "×" + Math.round(b.height) + " " + (el.textContent.trim() || el.getAttribute("aria-label") || "").slice(0, 30));
      }
    });
    Object.keys(small).forEach((k) => (small[k] = [...new Set(small[k])].slice(0, 6)));
    return { scroll: document.documentElement.scrollWidth - innerWidth, small, low: [...new Set(low)].slice(0, 25) };
  });
}

(async () => {
  const browser = await chromium.launch();
  const report = {};
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    const qs = new URLSearchParams({ today: "2026-10-10", basemap: "offline", fit: "0", persist: "0",
      objects: "/data/civic/astana/demo_synthetic.json", streets: STREETS, snapped: "/web/civic/map/demo_snapped.json" });
    await page.goto(base + "/tests/civic/R12/map/stand/?" + qs);
    await page.waitForFunction(() => window.__stand && window.__stand.instance && window.__stand.instance.getState().list === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(out, `r12-map-${w}-start.png`) });
    report[w + "-start"] = await measure(page);
    const feats = await page.evaluate(async () => (await window.__stand.map.getSource("civic-r03-objects").getData()).features.map((f) => ({ id: f.properties.cid, type: f.geometry.type, snapped: f.properties.snapped, approx: f.properties.approx || f.properties.approximate })));
    report.features = feats;
    const line = feats.find((f) => f.type === "LineString" && f.snapped) || feats[0];
    await page.evaluate((id) => window.__stand.instance.selectObject(id), line.id);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(out, `r12-map-${w}-line-card.png`) });
    report[w + "-card"] = await measure(page);
    // Крупный план линии и наклон 60° (проверка: линия не режет дома, стоит на месте при наклоне)
    await page.evaluate(() => window.__stand.map.jumpTo({ center: [71.4289, 51.1716], zoom: 16.2, pitch: 0, bearing: 0 }));
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(out, `r12-map-${w}-line-z16.png`) });
    await page.evaluate(() => window.__stand.map.jumpTo({ pitch: 60, bearing: -20 }));
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(out, `r12-map-${w}-line-z16-pitch60.png`) });
    const approx = (await page.evaluate(() => window.__stand.instance.getState().count)) && feats.find((f) => f.approx);
    if (approx) {
      await page.evaluate((id) => window.__stand.instance.selectObject(id), approx.id);
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(out, `r12-map-${w}-approx-card.png`) });
    }
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(out, "r12-measure.json"), JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1).slice(0, 4000));
})().catch((e) => { console.error(e); process.exit(1); });
