// круг 5: карточка акимата — «Что пишут жители» пока грузится (скелет на месте, без скачка), раскрытый «Жалобы по дням»
// переживает перерисовку, открытые блоки не «моргают» при перерисовке.   node texts_probe.cjs <out> [base] [w] [lang]
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const OUT = process.argv[2], BASE = process.argv[3] || "http://127.0.0.1:8614/", W = Number(process.argv[4] || 1366), LANG = process.argv[5] || "ru";
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await b.newContext({ viewport: { width: W, height: W < 500 ? 812 : 768 }, deviceScaleFactor: 2, isMobile: W < 500, hasTouch: W < 500 });
  await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) {} }, LANG);
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 160)));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  let hold = true;
  await p.route(/\/heat\/target/, async (r) => { while (hold) await new Promise((x) => setTimeout(x, 100)); r.continue().catch(() => {}); });
  await p.goto(BASE, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
  await p.evaluate(() => map.jumpTo({ center: [71.4045, 51.1285], zoom: 14.6 }));
  await p.waitForFunction(() => window.CivicShell.heat.state().mode === "targets" && document.querySelector(".r07-hot .r07-item"), null, { timeout: 30000 });
  await p.waitForTimeout(1500);
  await p.evaluate(() => document.querySelector(".r07-hot .r07-item").click());
  await p.waitForSelector(".r07-card", { timeout: 15000 });
  await p.waitForTimeout(600);
  const rect = async () => p.evaluate(() => { const r = document.querySelector("#birge-heat-root").getBoundingClientRect(); return { x: r.x - 8, y: r.y, width: r.width + 16, height: Math.min(560, innerHeight - r.y) }; });
  const before = await p.evaluate(() => ({ skel: !!document.querySelector(".r07-texts--loading .r07-texts__skel"), chartTop: Math.round(document.querySelector(".r07-chart, .r07-qr, .r07-footnote")?.getBoundingClientRect().top || 0) }));
  await p.screenshot({ path: `${OUT}/texts-loading-${W}-${LANG}.jpg`, type: "jpeg", quality: 85, clip: await rect() });
  hold = false;
  await p.waitForSelector(".r07-texts .r07-quotes, .r07-texts .r07-note", { timeout: 15000 });
  await p.waitForTimeout(800);
  const after = await p.evaluate(() => ({ skel: !!document.querySelector(".r07-texts__skel"), quotes: document.querySelectorAll(".r07-quotes li").length, chartTop: Math.round(document.querySelector(".r07-chart, .r07-qr, .r07-footnote")?.getBoundingClientRect().top || 0) }));
  await p.screenshot({ path: `${OUT}/texts-ready-${W}-${LANG}.jpg`, type: "jpeg", quality: 85, clip: await rect() });
  // раскрыть «Жалобы по дням» и перерисовать карточку (как при новой жалобе) — блок остаётся раскрытым, цитаты не «моргают»
  const chart = await p.$(".r07-chart > summary");
  if (chart) { await chart.click(); await p.waitForTimeout(500); }
  const anim1 = await p.evaluate(() => document.querySelector(".r07-chart")?.getAnimations({ subtree: true }).length ?? null);
  await p.evaluate(() => window.dispatchEvent(new CustomEvent("birge:complaint", { detail: { type: "status" } })));
  await p.waitForTimeout(150);
  const re = await p.evaluate(() => ({ chartOpen: document.querySelector(".r07-chart")?.open ?? null,
    textsAnims: document.querySelector(".r07-texts")?.getAnimations({ subtree: true }).filter((a) => a.animationName === "r07-enter").length ?? null }));
  await p.waitForTimeout(1500);
  const re2 = await p.evaluate(() => ({ chartOpen: document.querySelector(".r07-chart")?.open ?? null }));
  console.log(W, LANG, JSON.stringify({ before, after, hasChart: !!chart, anim1, re, re2, errs }));
  await b.close();
})();
