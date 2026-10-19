const { chromium } = require("/opt/node-tools/node_modules/playwright");
const OUT = process.argv[2];
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 }, recordVideo: { dir: OUT, size: { width: 1366, height: 768 } } });
  await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", "ru"); } catch (e) {} });
  const p = await ctx.newPage();
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.goto("http://127.0.0.1:8614/", { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
  await p.waitForTimeout(2500);
  await p.click(".r07-hot .r07-item");                     // карточка въезжает, карта перелетает
  await p.waitForTimeout(3000);
  await p.click(".r07-card [data-back]");                  // назад к списку
  await p.waitForTimeout(1500);
  await p.click(".birge-legend-q"); await p.waitForTimeout(1500);   // легенда на стекле
  await p.click(".birge-legend-q"); await p.waitForTimeout(800);
  await p.evaluate(() => window.CivicShell.heat.pulse && window.CivicShell.heat.pulse((window.CivicShell.heat.badges()[0] || {}).key));
  await p.waitForTimeout(2500);
  await ctx.close();
  await b.close();
})();
