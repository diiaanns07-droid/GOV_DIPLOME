// R07 · круг 6: шаги R10 linear_check для R07 (J/K, ↓, строки 44 px, список ↔ карта) на сборке R01 FINAL-4, где
// «Горячие места» открываются из сводки («Все горячие места») — список сначала открывается, как это сделает ведущий.
//   node linear_r07_probe.cjs [port=8615]
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const port = process.argv[2] || "8615";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 } });
  await ctx.addInitScript(() => { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", "ru"); });
  const page = await ctx.newPage();
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await page.goto("http://127.0.0.1:" + port + "/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});
  await sleep(2500);
  const out = {};
  const visRows = () => page.evaluate(() => [...document.querySelectorAll(".r07-item")].filter((e) => e.getBoundingClientRect().height > 0).length);
  out.rowsBefore = await visRows();
  // как ведущий: ссылка «Все горячие места» в сводке R08 (иначе — R01 BirgeRef.openList)
  const link = page.getByText(/^Все горячие места$/).first();
  if (await link.isVisible().catch(() => false)) { await link.click(); out.opened = "link"; }
  else { await page.evaluate(() => window.BirgeRef.openList(null)); out.opened = "BirgeRef.openList"; }
  await sleep(1200);
  out.rowsAfter = await visRows();
  const key = () => page.evaluate(() => (document.activeElement && document.activeElement.dataset.key) || null);
  await page.locator(".r07-item").first().focus(); await sleep(200);
  const k0 = await key(); await page.keyboard.press("j"); await sleep(250);
  const k1 = await key(); await page.keyboard.press("k"); await sleep(250);
  const k2 = await key(); await page.keyboard.press("ArrowDown"); await sleep(250);
  const k3 = await key();
  out.jk = { k0, k1, k2, k3, pass: Boolean(k1 && k1 !== k0 && k2 === k0), down: Boolean(k3 && k3 !== k0) };
  const hs = await page.evaluate(() => [...document.querySelectorAll(".r07-item")].filter((e) => e.getBoundingClientRect().height > 0).map((e) => Math.round(e.getBoundingClientRect().height)));
  const med = hs.slice().sort((a, b) => a - b)[Math.floor(hs.length / 2)];
  out.rows = { median: med, heights: hs.slice(0, 8), pass: med >= 40 && med <= 48 };
  // список ↔ карта: наведение на строку подсвечивает значок того же места
  const k = await page.evaluate(() => { const r = [...document.querySelectorAll(".r07-item[data-key]")].find((e) => e.getBoundingClientRect().height > 0 &&
    document.querySelector('.r07-badge[data-key="' + e.dataset.key + '"]')); return r ? r.dataset.key : null; });
  if (k) {
    const bcls = () => page.evaluate((kk) => document.querySelector('.r07-badge[data-key="' + kk + '"]')?.className || null, k);
    const before = await bcls();
    await page.locator('.r07-item[data-key="' + k + '"]').hover(); await sleep(300);
    const after = await bcls();
    out.sync = { key: k, before, after, pass: before !== after };
  } else out.sync = { key: null, note: "нет строки со значком на карте в этом виде" };
  console.log(JSON.stringify(out));
  await b.close();
})();
