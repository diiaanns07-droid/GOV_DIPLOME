// круг 4: что лежит поверх строки легенды на телефоне (уведомление «Реестр пуст…»)
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const OUT = process.argv[2], DB_NOTE = process.argv[3] || "";
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const [w, h] of [[375, 812], [1366, 768]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, isMobile: w < 500, hasTouch: w < 500 });
    await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", "ru"); } catch (e) {} });
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.goto("http://127.0.0.1:8614/", { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
    await p.waitForTimeout(2500);
    const info = await p.evaluate(() => {
      const q = document.querySelector(".birge-legend-q");
      const out = { q: null, notice: [] };
      if (q) { const r = q.getBoundingClientRect(); const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
        out.q = { box: [r.x, r.y, r.width, r.height].map(Math.round), topEl: top ? (top.id ? "#" + top.id : "") + "." + String(top.className).split(" ").join(".") : null, topText: top ? top.textContent.trim().slice(0, 60) : "" }; }
      for (const e of document.querySelectorAll("body *")) {
        if (e.children.length > 3) continue;
        const t = (e.textContent || "").trim();
        if (/^Реестр пуст/.test(t)) { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
          out.notice.push({ el: (e.id ? "#" + e.id : "") + "." + String(e.className).split(" ").join("."), box: [r.x, r.y, r.width, r.height].map(Math.round), right: Math.round(r.right), z: cs.zIndex, pos: cs.position }); }
      }
      return out;
    });
    console.log(w, JSON.stringify(info));
    await ctx.close();
  }
  await b.close();
})();
