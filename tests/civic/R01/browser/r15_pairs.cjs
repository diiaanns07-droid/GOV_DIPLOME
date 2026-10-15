// R01 round 15: «было | стало» — the same views of two running builds (e.g. FINAL-4.1 and the current build) for the
// build log and the diploma. Both stands must already run (they need different code trees); the script only shoots.
//   node tests/civic/R01/browser/r15_pairs.cjs <out_dir> <url_before> <url_after> [label_before] [label_after]
// Writes <out_dir>/before_<view>.jpg, after_<view>.jpg and pairs.json; scripts/merge (python, PIL) glue them side by side.
// Views: akimat and resident home at 1366 / 1024 / 375 (ru and kk), «Ещё» of the akimat at 1366, «Картина дня» at 1366.
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");

const [OUT, BEFORE, AFTER] = [path.resolve(process.argv[2] || "r15-pairs-out"), process.argv[3], process.argv[4]];
const LABELS = [process.argv[5] || "было", process.argv[6] || "стало"];
const VIEWS = [
  { id: "1366_ru_akimat", w: 1366, h: 768, mode: "akimat", lang: "ru" },
  { id: "1366_kk_akimat", w: 1366, h: 768, mode: "akimat", lang: "kk" },
  { id: "1366_ru_resident", w: 1366, h: 768, mode: "resident", lang: "ru" },
  { id: "1024_ru_akimat", w: 1024, h: 768, mode: "akimat", lang: "ru" },
  { id: "1024_kk_resident", w: 1024, h: 768, mode: "resident", lang: "kk" },
  { id: "375_ru_resident", w: 375, h: 812, mode: "resident", lang: "ru" },
  { id: "375_kk_akimat", w: 375, h: 812, mode: "akimat", lang: "kk" },
  { id: "1366_ru_akimat_more", w: 1366, h: 768, mode: "akimat", lang: "ru", more: true },
  { id: "1366_ru_akimat_day", w: 1366, h: 768, mode: "akimat", lang: "ru", section: "day" },
];

async function shoot(browser, base, view, file) {
  const mobile = view.w < 761;
  const ctx = await browser.newContext({ viewport: { width: view.w, height: view.h }, isMobile: mobile, hasTouch: mobile });
  await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) { /* без хранилища */ } }, [view.mode, view.lang]);
  const page = await ctx.newPage();
  await page.goto(base);
  await page.waitForFunction(() => window.BirgeShell && document.querySelector("#birge-header") && typeof mapReady !== "undefined" && mapReady,
    null, { timeout: 45000 }).catch(() => null);
  await page.waitForFunction(() => [...document.querySelectorAll(".maplibregl-marker")].some((e) => e.getBoundingClientRect().width > 0),
    null, { timeout: 20000 }).catch(() => null);
  await page.waitForTimeout(1500);
  if (view.section) { await page.evaluate((s) => window.BirgeShell.setSection(s), view.section); await page.waitForTimeout(2500); }
  if (view.more) { await page.click("#birge-header .birge-nav [data-section=more]").catch(() => null); await page.waitForTimeout(500); }
  await page.screenshot({ path: file, type: "jpeg", quality: 80 });
  await ctx.close();
}

async function main() {
  if (!BEFORE || !AFTER) { console.error("usage: r15_pairs.cjs <out> <url_before> <url_after> [label_before] [label_after]"); process.exit(2); }
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const done = [];
  try {
    for (const view of VIEWS) {
      await shoot(browser, BEFORE, view, path.join(OUT, `before_${view.id}.jpg`));
      await shoot(browser, AFTER, view, path.join(OUT, `after_${view.id}.jpg`));
      done.push(view.id);
    }
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(OUT, "pairs.json"), JSON.stringify({ labels: LABELS, before: BEFORE, after: AFTER, views: done }, null, 1));
  console.log(JSON.stringify({ pairs: done.length }));
}
main().catch((e) => { console.error(e); process.exit(2); });
