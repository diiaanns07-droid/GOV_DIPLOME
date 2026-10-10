/*
 * R11 · остатки непереведённого: видимые (и не перекрытые) строки с кириллицей, одинаковые в ru и kk,
 * на экранах сборки R01 (акимат, житель, «Картина дня», мастер жалобы шаг ②, «Мои обращения») × 1366/375.
 * Имена в «ёлочках» не считаются.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/ru_kk_same.cjs http://127.0.0.1:<порт>/ > out.json
 *   FULL=1 … — вся страница, включая то, что ниже прокрутки панелей (без проверки перекрытия и границ экрана).
 */
const { chromium } = require("playwright");
const FULL = !!process.env.FULL;
const texts = (p) => p.evaluate((FULL) => {
  const out = new Set(); const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) { const t = n.textContent.replace(/\s+/g, " ").trim(); if (!/[А-Яа-яЁё]{3}/.test(t)) continue;
    const e = n.parentElement; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    if (!r.width || !r.height || cs.visibility === "hidden") continue;
    if (FULL) { out.add(t); continue; }
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const top = document.elementFromPoint(Math.min(innerWidth - 1, Math.max(0, r.left + 4)), Math.min(innerHeight - 1, Math.max(0, r.top + r.height / 2)));
    if (top && !e.contains(top) && !top.contains(e)) continue; // перекрыто
    out.add(t); }
  return [...out]; }, FULL);
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const res = {};
  for (const [name, mode, section] of [["akimat", "akimat", null], ["resident", "resident", null], ["day", "akimat", "day"],
    ["wizard", "resident", "wizard"], ["mine", "resident", "mine"]]) {
    for (const w of [1366, 375]) {
      const got = {};
      for (const lang of ["ru", "kk"]) {
        const ctx = await b.newContext({ viewport: w === 1366 ? { width: 1366, height: 768 } : { width: 375, height: 812 } });
        const p = await ctx.newPage();
        await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
        await p.addInitScript(([l, m]) => { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); }, [lang, mode]);
        await p.goto(process.argv[2]);
        await p.waitForFunction(() => window.CivicShell && window.CivicShell.heat && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 }).catch(() => {});
        await p.waitForTimeout(2500);
        if (section === "day") { await p.evaluate(() => document.querySelector("#birge-header [data-section=day]").click()); await p.waitForTimeout(2500); }
        if (section === "wizard") { // мастер жалобы, шаг ②: «Где проблема?» до выбора места
          if (!(await p.isVisible(".bc-fab"))) await p.keyboard.press("Escape");
          await p.click(".bc-fab").catch(() => {}); await p.waitForTimeout(1500);
        }
        if (section === "mine") { await p.evaluate(() => { const b = document.querySelector("#birge-header [data-action=mine]"); if (b) b.click(); }); await p.waitForTimeout(1800); }
        got[lang] = await texts(p); await ctx.close();
      }
      const kk = new Set(got.kk);
      res[`${name}-${w}`] = got.ru.filter((t) => kk.has(t) && !/^[«"].*[»"]$/.test(t));
    }
  }
  console.log(JSON.stringify(res, null, 1));
  await b.close();
})();
