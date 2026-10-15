// R01 round 15: «первый значок ≤ 3 с» for the build acceptance — time from navigation to the first heat-map badge
// (.maplibregl-marker) visible inside the viewport, akimat at 1366 and resident at 375, fresh browser context each run.
// The stand must already run (the build with the demo world, as run-city.bat): the script only measures.
//   node tests/civic/R01/browser/r15_first_badge.cjs <url> [runs=3]
// Prints {"runs":[…],"median_1366":ms,"median_375":ms}; exit 1 if a median is over 3000 ms or a badge never showed.
"use strict";
const { chromium } = require("playwright");

const LIMIT_MS = 3000;

async function main() {
  const base = process.argv[2], runs = Number(process.argv[3] || 3);
  if (!base) { console.error("usage: r15_first_badge.cjs <url> [runs=3]"); process.exit(2); }
  const browser = await chromium.launch();
  const out = [];
  try {
    for (let i = 0; i < runs; i++) for (const [w, h, mode] of [[1366, 768, "akimat"], [375, 812, "resident"]]) {
      const mobile = w < 761;
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile });
      await ctx.addInitScript((m) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", "ru"); } catch (e) { /* без хранилища */ } }, mode);
      const page = await ctx.newPage();
      const t0 = Date.now();
      await page.goto(base, { waitUntil: "commit" });
      const ok = await page.waitForFunction(() => [...document.querySelectorAll(".maplibregl-marker")].some((e) => {
        const r = e.getBoundingClientRect(); return r.width > 0 && r.top >= 0 && r.top < innerHeight; }), null, { timeout: 30000, polling: 50 })
        .then(() => true, () => false);
      out.push({ w, mode, ms: ok ? Date.now() - t0 : null });
      await ctx.close();
    }
  } finally { await browser.close(); }
  const median = (w) => { const v = out.filter((x) => x.w === w).map((x) => x.ms); if (v.includes(null)) return null;
    v.sort((a, b) => a - b); return v[Math.floor(v.length / 2)]; };
  const res = { runs: out, median_1366: median(1366), median_375: median(375), limit_ms: LIMIT_MS };
  console.log(JSON.stringify(res));
  process.exit([res.median_1366, res.median_375].every((m) => m !== null && m <= LIMIT_MS) ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(2); });
