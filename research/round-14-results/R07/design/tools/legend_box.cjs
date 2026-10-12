// круг 7: поля, радиусы и левый край текста у строки легенды R01 и подробной легенды R07 (под «?»)
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const BASE = process.argv[2] || "http://127.0.0.1:8614/";
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, isMobile: w < 500, hasTouch: w < 500 });
    await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", "ru"); } catch (e) {} });
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
    await p.waitForTimeout(2000);
    await p.evaluate(() => document.querySelector(".civic-explore-registry")?.remove());   // плашка R01 (M.10-1) мешает нажать «?»
    await p.evaluate(() => document.querySelector(".birge-legend-q")?.click());
    await p.waitForTimeout(1200);
    const info = await p.evaluate(() => {
      const box = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
        const txt = [...el.querySelectorAll("*")].find((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
        const tr = txt ? txt.getBoundingClientRect() : null;
        return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), pad: cs.padding, radius: cs.borderRadius, textLeft: tr ? Math.round(tr.x - r.x) : null, fs: txt ? getComputedStyle(txt).fontSize : null }; };
      const line = document.querySelector(".birge-legend") || document.querySelector("#birge-legend");
      const detail = document.querySelector(".r07-maplegend");
      return { line: box(line), detail: box(detail), detailOpen: !!detail && !detail.hidden && detail.getClientRects().length > 0 };
    });
    console.log(w, JSON.stringify(info));
    await ctx.close();
  }
  await b.close();
})();
