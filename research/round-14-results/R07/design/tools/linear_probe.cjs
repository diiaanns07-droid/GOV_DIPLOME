// Эталон A + Linear (R07): список ↔ карта, клавиатура, смена статуса из строки, подсказки, J/K, вкладки карточки.
//   node linear_probe.cjs <out> [base]
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const OUT = process.argv[2], BASE = process.argv[3] || "http://127.0.0.1:8614/";
const res = {};
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 } });
  await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", "ru"); } catch (e) {} });
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 200)));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.goto(BASE, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
  await p.evaluate(() => map.jumpTo({ center: [71.4045, 51.1285], zoom: 14.6 }));
  await p.waitForFunction(() => window.CivicShell.heat.state().mode === "targets" && document.querySelector(".r07-hot .r07-item"), null, { timeout: 30000 });
  await p.waitForTimeout(2000);
  // 1) наведение на строку → значок подсвечен, кнопка статуса видна
  const rows = p.locator(".r07-hot .r07-list .r07-item");
  const n = await rows.count();
  let hoverIdx = -1;
  for (let i = 0; i < n && hoverIdx < 0; i++) {
    const key = await rows.nth(i).getAttribute("data-key");
    const has = await p.evaluate((k) => !!document.querySelector('.r07-badge[data-key="' + CSS.escape(k) + '"]:not([hidden])'), key);
    if (has) hoverIdx = i;
  }
  if (hoverIdx >= 0) {
    await rows.nth(hoverIdx).hover();
    await p.waitForTimeout(300);
    res.rowHover = await p.evaluate((i) => { const r = document.querySelectorAll(".r07-hot .r07-list .r07-item")[i]; const k = r.dataset.key;
      const bd = document.querySelector('.r07-badge[data-key="' + CSS.escape(k) + '"]'); const q = document.querySelector("[data-quick]");
      return { key: k, badgeHot: !!bd && bd.classList.contains("r07-badge--hot"), rowHot: r.classList.contains("r07-item--hot"), quick: q ? { hidden: q.hidden, label: q.getAttribute("aria-label"), act: q.dataset.quick } : null }; }, hoverIdx);
    await p.screenshot({ path: OUT + "/hover-row.jpg", type: "jpeg", quality: 82 });
  } else res.rowHover = "нет строки со значком на карте";
  // 2) наведение на значок → строка подсвечена
  const bk = await p.evaluate(() => { const rows = [...document.querySelectorAll(".r07-hot .r07-list .r07-item")].map((r) => r.dataset.key);
    const b = [...document.querySelectorAll(".r07-badge[data-key]")].find((e) => !e.hidden && rows.includes(e.dataset.key) && e.getBoundingClientRect().left < 900);
    if (!b) return null; const r = b.getBoundingClientRect(); return { key: b.dataset.key, x: r.left + 12, y: r.top + r.height / 2 }; });
  if (bk) { await p.mouse.move(10, 400); await p.waitForTimeout(200); await p.mouse.move(bk.x, bk.y); await p.waitForTimeout(300);
    res.badgeHover = await p.evaluate((k) => { const r = document.querySelector('.r07-item[data-key="' + CSS.escape(k) + '"]'); return { key: k, rowHot: !!r && r.classList.contains("r07-item--hot") }; }, bk.key); }
  // 3) клавиатура по строкам
  await p.mouse.move(10, 400);
  await rows.first().focus();
  const idx = async () => p.evaluate(() => document.activeElement && document.activeElement.dataset.idx);
  const seq = [await idx()];
  for (const k of ["ArrowDown", "j", "j", "k", "End", "Home"]) { await p.keyboard.press(k); seq.push(await idx()); }
  res.keys = seq;
  res.quickOnFocus = await p.evaluate(() => { const q = document.querySelector("[data-quick]"); return q ? !q.hidden : null; });
  // 4) подсказки и J/K
  res.suggest = await p.evaluate(() => window.CivicShell.heat.suggest("хан", 3).map((x) => x.label + " · " + x.count));
  res.suggestMid = await p.evaluate(() => window.CivicShell.heat.suggest("шатыр", 3).map((x) => x.label));
  const s1 = await p.evaluate(() => window.CivicShell.heat.stepHot(1)); await p.waitForTimeout(1500);
  const s2 = await p.evaluate(() => window.CivicShell.heat.stepHot(1)); await p.waitForTimeout(1500);
  res.stepHot = { s1, s2, selected: await p.evaluate(() => window.CivicShell.heat.state().selected), card: await p.evaluate(() => !!document.querySelector(".r07-card")) };
  // 5) вкладки
  await p.click('.r07-tab[data-tab="reports"]').catch(() => {});
  await p.waitForTimeout(400);
  res.tabReports = await p.evaluate(() => ({ visible: !document.getElementById("r07-tp-reports")?.hidden, quotes: document.querySelectorAll("#r07-tp-reports .r07-quotes li").length }));
  await p.screenshot({ path: OUT + "/tab-reports.jpg", type: "jpeg", quality: 82 });
  await p.keyboard.press("ArrowRight"); await p.waitForTimeout(300);
  res.tabHistory = await p.evaluate(() => ({ active: document.querySelector('.r07-tab[aria-selected="true"]')?.dataset.tab, focus: document.activeElement?.dataset.tab }));
  await p.screenshot({ path: OUT + "/tab-history.jpg", type: "jpeg", quality: 82 });
  // перерисовка (событие) — вкладка остаётся
  await p.evaluate(() => window.dispatchEvent(new CustomEvent("birge:complaint", { detail: { type: "status" } }))); await p.waitForTimeout(1500);
  res.tabAfterRerender = await p.evaluate(() => document.querySelector('.r07-tab[aria-selected="true"]')?.dataset.tab);
  res.close = await p.evaluate(() => window.CivicShell.heat.close());
  res.cardAfterClose = await p.evaluate(() => !!document.querySelector(".r07-card"));
  res.errs = errs;
  console.log(JSON.stringify(res, null, 1));
  await b.close();
})();
