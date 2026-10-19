// Кадр «как будет» для сравнения с эталоном A: на сборке R01 только для снимка панель ставится на место карточки эталона
// (слева под поиском, 388 px, стекло 86 %) — INTEGRATION R.6. Код сборки не меняется.   node ref_compose.cjs <out> [base] [lang]
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const OUT = process.argv[2], BASE = process.argv[3] || "http://127.0.0.1:8614/", LANG = process.argv[4] || "ru";
const CSS = `
body.civic-mode .civic-panel { left: 20px !important; right: auto !important; top: 84px !important; bottom: auto !important; width: 388px !important;
  height: auto !important; max-height: calc(100% - 104px) !important; border-radius: 18px !important; background: rgba(255,255,255,.86) !important;
  -webkit-backdrop-filter: blur(24px) saturate(180%) !important; backdrop-filter: blur(24px) saturate(180%) !important; border: 1px solid rgba(255,255,255,.7) !important;
  box-shadow: 0 1px 0 rgba(255,255,255,.75) inset, 0 12px 32px rgba(16,24,20,.14), 0 0 0 .5px rgba(16,24,20,.10) !important; }
body.civic-mode .civic-scroll { padding: 0 !important; }
.civic-scroll .r07-root { --r07-gutter: 18px !important; --r07-top: 18px !important; --r07-bleed: 0px !important; }
.civic-explore-registry { display: none !important; }`;
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 } });
  await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) {} }, LANG);
  const p = await ctx.newPage();
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.goto(BASE, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
  await p.addStyleTag({ content: CSS });
  // отступы карты под карточку слева (как сделает оболочка): fitPadding — у R01; здесь — только снимок
  const items = await p.evaluate(async () => ((d) => (d.data || d).items || [])(await (await fetch("/api/civic/v2/heat?days=30&zoom=14")).json()));
  const it = items.find((x) => /Хан Шатыр/.test(x.target.label_ru || ""));
  await p.evaluate(() => map.jumpTo({ center: [71.4045, 51.1285], zoom: 14.6 }));
  await p.waitForTimeout(2500);
  await p.screenshot({ path: `${OUT}/stalo-list-1366-${LANG}.jpg`, type: "jpeg", quality: 85 });
  await p.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), it.target);
  await p.waitForTimeout(3000);
  // место — туда же, где оно в эталоне (880, 330): правее карточки слева
  await p.evaluate((a) => { const pt = map.project(a); map.panBy([pt.x - 880, pt.y - 330 + 0], { duration: 0 }); }, it.anchor);
  await p.waitForTimeout(1200);
  await p.screenshot({ path: `${OUT}/stalo-obj-1366-${LANG}.jpg`, type: "jpeg", quality: 85 });
  await b.close();
})();
