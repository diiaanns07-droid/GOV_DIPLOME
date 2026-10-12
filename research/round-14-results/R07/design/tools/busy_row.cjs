// круг 4: строка «открывается» после нажатия на место на обзоре районов (кадр панели сразу после клика + DOM по кадрам)
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const OUT = process.argv[2], W = Number(process.argv[3] || 1366), H = Number(process.argv[4] || 768), LANG = process.argv[5] || "ru";
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const reduce of [false, true]) {
    const ctx = await b.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2, isMobile: W < 500, hasTouch: W < 500, reducedMotion: reduce ? "reduce" : "no-preference" });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) {} }, LANG);
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    // замедлить ответ цели, чтобы кадр поймал состояние «открывается» (на ноутбуке оно длится ~1 с)
    await p.route(/\/heat\/target/, async (r) => { await new Promise((x) => setTimeout(x, 30000)); r.continue().catch(() => {}); });
    await p.goto("http://127.0.0.1:8614/", { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
    await p.waitForTimeout(2500);
    const mode0 = await p.evaluate(() => window.CivicShell.heat.state().mode);
    await p.evaluate(() => {
      window.__log = []; const t0 = performance.now();
      const snap = () => { const busy = document.querySelectorAll(".r07-item--busy").length; const v = document.querySelector(".r07-card") ? "card" : "list";
        const k = busy + v; if (k !== window.__k) { window.__k = k; window.__log.push([Math.round(performance.now() - t0), busy, v]); } };
      new MutationObserver(snap).observe(document.getElementById("birge-heat-root"), { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
      snap();
      document.querySelector(".r07-hot .r07-item").click();
    });
    await p.waitForTimeout(1200);
    const box = await p.locator("#birge-heat-root").boundingBox();
    await p.screenshot({ path: `${OUT}/busyshot-${W}-${LANG}${reduce ? "-reduce" : ""}.jpg`, type: "jpeg", quality: 85, clip: { x: box.x - 8, y: box.y, width: box.width + 16, height: Math.min(380, H - box.y) } });
    await p.waitForTimeout(1500);
    await p.waitForTimeout(500);
    const log = await p.evaluate(() => window.__log);
    console.log(W, LANG, reduce ? "reduce" : "motion", "mode0", mode0, JSON.stringify(log), "busy-left", await p.evaluate(() => document.querySelectorAll(".r07-item--busy").length));
    await ctx.close();
  }
  await b.close();
})();
