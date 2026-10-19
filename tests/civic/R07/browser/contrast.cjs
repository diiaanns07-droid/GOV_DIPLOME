// R07 раунд 15+ (П3, видимые исправления; как R10 B-136 / R11 ec3d0aef): читаемый серый текст панели тепловой карты
// и полосы хроники — не ниже 4,5 : 1 (WCAG AA для 13–14 px). Цвет текста против фонов предков, смешанных поверх белого.
// Запуск: python -m ui.civic_heat.devserver --port 8619 &   python -m ui.civic_heat.devserver --world --port 8617 &   затем
//   NODE_PATH=$(npm root -g) node tests/civic/R07/browser/contrast.cjs [отчёт.json]
const { chromium } = require("playwright");
const fs = require("fs");
const BASE = process.env.R07_BASE || "http://127.0.0.1:8619/civic/heat/demo.html";
const WORLD = process.env.R07_WORLD || "http://127.0.0.1:8617/civic/heat/demo.html";
const OUT = process.argv[2];
const MEASURE = () => {
  const parse = (c) => { const m = /rgba?\(([^)]+)\)/.exec(c || ""); if (!m) return null; const p = m[1].split(",").map((x) => parseFloat(x)); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (top, bot) => ({ r: top.r * top.a + bot.r * (1 - top.a), g: top.g * top.a + bot.g * (1 - top.a), b: top.b * top.a + bot.b * (1 - top.a), a: 1 });
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const bgOf = (el) => {   // фоны предков снизу вверх, смешанные поверх белого (карта под стеклом светлая)
    const stack = [];
    for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) stack.push(c); if (c && c.a >= 1) break; }
    let bg = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = stack.length - 1; i >= 0; i--) bg = over(stack[i], bg);
    return bg;
  };
  const SEL = [".r07-footnote", ".r07-lhd__days", ".r07-gh__n", ".r07-item__meta", ".r07-tag", ".r07-statusline__note", ".r07-tab:not([aria-selected=true])",
    ".r07-merged__count", ".r07-axis", ".r07-topics__sub", ".r07-quote__meta", ".rp-date .rp-title", ".rp-tick span", ".rp-mark--background .rp-mark__label"];
  return SEL.map((sel) => {
    const el = [...document.querySelectorAll(sel)].find((e) => e.getBoundingClientRect().width > 0 && getComputedStyle(e).visibility !== "hidden");
    if (!el) return { sel, found: false };
    const fg = parse(getComputedStyle(el).color), bg = bgOf(el);
    const c = fg.a < 1 ? over(fg, bg) : fg;
    const L1 = lum(c), L2 = lum(bg);
    return { sel, found: true, color: getComputedStyle(el).color, size: getComputedStyle(el).fontSize, text: el.textContent.trim().slice(0, 30),
      ratio: +((Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)).toFixed(2) };
  });
};
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const res = {};
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  await page.goto(`${BASE}?lang=ru&role=akimat&view=nura`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
  await page.waitForTimeout(1200);
  res.list = await page.evaluate(MEASURE);
  // карточка места (вкладки, график, темы, цитаты)
  const b = await page.evaluate(async () => { const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=16")).json(); const it = (d.items || []).filter((x) => x.target.kind !== "district").sort((a, c) => c.count - a.count)[0]; return it && it.target; });
  await page.evaluate((t) => window.__heat.focusTarget(t.kind, t.id), b);
  await page.waitForTimeout(2500);
  res.card = await page.evaluate(MEASURE);
  await page.close();
  const p2 = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  await p2.goto(`${WORLD}?lang=ru&view=city&replay=7&autoplay=0`, { waitUntil: "networkidle" });
  await p2.waitForSelector(".rp", { timeout: 30000 }).catch(() => null);
  await p2.waitForTimeout(2500);
  res.replay = await p2.evaluate(MEASURE);
  await browser.close();
  const rows = [];
  for (const [where, list] of Object.entries(res)) for (const r of list) if (r.found) rows.push({ where, ...r });
  const uniq = new Map(); rows.forEach((r) => { if (!uniq.has(r.sel)) uniq.set(r.sel, r); });
  const out = [...uniq.values()];
  out.forEach((r) => console.log(`${r.ratio >= 4.5 ? "PASS" : "FAIL"} ${r.ratio.toFixed(2)}:1  ${r.size}  ${r.sel}  «${r.text}»  (${r.where})`));
  const low = out.filter((r) => r.ratio < 4.5);
  const problems = out.length < 8 ? ["найдено меньше 8 подписей — проверка ничего бы не нашла: " + out.length] : [];
  console.log(`${out.length - low.length}/${out.length} PASS` + (problems.length ? " · " + problems[0] : ""));
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  process.exit(low.length || problems.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
