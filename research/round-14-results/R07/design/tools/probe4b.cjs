// круг 4: по кадрам (rAF) — пустеет ли панель R07 в DOM во время перелёта после клика по горячему месту
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const Q = process.argv[2] || "";
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 } });
  await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", "ru"); } catch (e) {} });
  const p = await ctx.newPage();
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.goto("http://127.0.0.1:8614/" + Q, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
  await p.waitForTimeout(2500);
  await p.evaluate(() => {
    window.__log = []; const t0 = performance.now();
    const root = document.getElementById("birge-heat-root");
    const tick = () => {
      const kids = root ? root.children.length : -1;
      let minOp = 1, e = root; while (e && e !== document.documentElement) { minOp = Math.min(minOp, Number(getComputedStyle(e).opacity)); e = e.parentElement; }
      const first = root && root.firstElementChild; const fr = first ? first.getBoundingClientRect() : null;
      const view = document.querySelector(".r07-card") ? "card" : document.querySelector(".r07-hot") ? "hot" : document.querySelector(".r07-skeleton") ? "skel" : "other";
      window.__log.push([Math.round(performance.now() - t0), kids, minOp, view, fr ? Math.round(fr.y) : null, Math.round(map.getZoom() * 10) / 10]);
      if (performance.now() - t0 < 6000) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  await p.click(".r07-hot .r07-item");
  await p.waitForTimeout(7000);
  const log = await p.evaluate(() => window.__log);
  let prev = "";
  for (const r of log) { const k = JSON.stringify(r.slice(1, 5)); if (k !== prev) { console.log(JSON.stringify(r)); prev = k; } }
  console.log("frames", log.length);
  await b.close();
})();
