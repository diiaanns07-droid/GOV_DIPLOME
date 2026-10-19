// R07 · круг 5 эталона A: замер рамок значков (≥ 44 × 44, кружок по центру), ссылки «Распечатать QR» и полосы вкладок.
//   node tap_probe.cjs  (стенд сборки на http://127.0.0.1:8614/)
const { chromium } = require("/opt/node-tools/node_modules/playwright");
(async () => {
  const b = await chromium.launch();
  for (const [w,h] of [[1366,768],[375,812]]) {
    const ctx = await b.newContext({ viewport:{width:w,height:h}, isMobile:w<500, hasTouch:w<500 });
    await ctx.addInitScript(() => { localStorage.setItem("birge.mode","akimat"); localStorage.setItem("birge.lang","ru"); });
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
    await p.goto("http://127.0.0.1:8614/", { waitUntil:"domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(()=>{});
    await p.waitForTimeout(2500);
    // открыть исправленное место (как в states.cjs card-reported)
    const items = await p.evaluate(() => fetch("/api/civic/v2/heat?days=30").then(r=>r.json()).then(j=>j.items||[]).catch(()=>[]));
    const it = items.find(i => i.state==="fixed" && i.target && i.target.kind==="object");
    const ok = it ? it.target.label_ru : false;
    if (it) await p.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), it.target);
    await p.waitForTimeout(2500);
    const r = await p.evaluate(() => {
      const rect = e => { const b = e.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height)]; };
      const badges = [...document.querySelectorAll(".r07-badge")].filter(e => e.offsetParent || e.getClientRects().length).map(e => ({lv:e.dataset.level, mini:e.classList.contains("r07-badge--mini"), r:rect(e)}));
      const narrow = badges.filter(x => x.r[0] < 44 || x.r[1] < 44);
      const qr = document.querySelector("a.r07-qr"); const tabs = document.querySelector(".r07-tabs");
      const dot = document.querySelector('.r07-badge[data-level="fixed"] .r07-badge__dot'), btn = dot && dot.closest(".r07-badge");
      let off = null; if (dot) { const a = dot.getBoundingClientRect(), c = btn.getBoundingClientRect(); off = [Math.round((a.left+a.right)/2 - (c.left+c.right)/2), Math.round((a.top+a.bottom)/2-(c.top+c.bottom)/2)]; }
      return { n: badges.length, narrow: narrow.slice(0,5), fixedSizes: badges.filter(x=>x.lv==="fixed").map(x=>x.r).slice(0,4), qr: qr && rect(qr), tabs: tabs && rect(tabs), dotOffset: off };
    });
    console.log(w, JSON.stringify(ok), JSON.stringify(r));
    await ctx.close();
  }
  await b.close();
})();
