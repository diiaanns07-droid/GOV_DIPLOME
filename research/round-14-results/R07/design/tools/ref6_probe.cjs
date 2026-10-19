// R07 · круг 6 эталона A: сборка R01 FINAL-4 (вид ref — карточка слева). Замер × «Горячих мест» (opts.closable), места
// карточки и списка, кадры «стало» 1366 / 375 ru.
//   node ref6_probe.cjs [port=8615] [out=.] [lang=ru|kk]
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const port = process.argv[2] || "8615", out = process.argv[3] || ".", lang = process.argv[4] || "ru";
(async () => {
  const b = await chromium.launch();
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, isMobile: w < 500, hasTouch: w < 500 });
    await ctx.addInitScript((l) => { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); }, lang);
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.goto("http://127.0.0.1:" + port + "/", { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});
    await p.waitForTimeout(2500);
    const rect = (sel) => p.evaluate((s) => { const e = document.querySelector(s); if (!e || !e.getClientRects().length) return null;
      const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
      return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), vis: cs.display !== "none" && cs.visibility !== "hidden" }; }, sel);
    const layout = await p.evaluate(() => ({ layout: document.body.dataset.birgeLayout, left: document.body.dataset.birgeLeft }));
    // «Горячие места» — как из сводки «Все горячие места» (R01 BirgeRef.openList)
    await p.evaluate(() => window.BirgeRef && window.BirgeRef.openList && window.BirgeRef.openList(null));
    await p.waitForTimeout(1500);
    const list = { left: await p.evaluate(() => document.body.dataset.birgeLeft), panel: await rect("#civic-panel"), hot: await rect(".r07-hot"),
      x: await rect(".r07-lhd .r07-x"), xClass: await p.evaluate(() => document.querySelector(".r07-lhd .r07-x")?.className || null),
      firstRow: await rect(".r07-item") };
    await p.screenshot({ path: `${out}/stalo6-list-${w}-${lang}.jpg`, type: "jpeg", quality: 82 });
    // Карточка места — «Хан Шатыр», как в эталоне (иначе первое место списка)
    const items = await p.evaluate(() => fetch("/api/civic/v2/heat?days=30").then((r) => r.json()).then((j) => (j.data || j).items || []).catch(() => []));
    const it = items.find((i) => /Хан Шатыр/.test((i.target && i.target.label_ru) || "")) || items[0];
    if (it) await p.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), it.target);
    await p.waitForTimeout(2500);
    const card = { left: await p.evaluate(() => document.body.dataset.birgeLeft), panel: await rect("#civic-panel"), card: await rect(".r07-card"),
      title: await rect(".r07-card h2, .r07-card .r07-h"), tabs: await rect(".r07-tabs"), x: await rect(".r07-card .r07-x"),
      sel: await rect(".r07-badge--selected .r07-badge__dot"), label: it && it.target.label_ru };
    await p.screenshot({ path: `${out}/stalo6-card-${w}-${lang}.jpg`, type: "jpeg", quality: 82 });
    console.log(w, JSON.stringify({ layout, list, card }));
    await ctx.close();
  }
  await b.close();
})();
