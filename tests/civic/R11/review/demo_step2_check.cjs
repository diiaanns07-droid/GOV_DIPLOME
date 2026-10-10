/*
 * R11 · шаги 1–2 DEMO_SCRIPT у жителя: «Мәселе туралы хабарлау» → нажать у остановки «Хан Шатыр» → «Осы жерде ме?» →
 * текст «Аялдамада жарық жоқ, вечером на остановке темно» → «Жіберу» → шаг ④ «Бұл туралы N адам хабарлаған» и «Мен де».
 * 375 kk и 1366 ru; кадры metoo-*.png в <папка>. Создаёт обращение в базе стенда (только тестовой).
 *   NODE_PATH="/opt/node22/lib/node_modules" node tests/civic/R11/review/demo_step2_check.cjs http://127.0.0.1:<порт>/ <папка>
 */
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const [w, h, lang] of [[375, 812, "kk"], [1366, 768, "ru"]]) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.addInitScript((l) => { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", "resident"); }, lang);
    await p.goto(process.argv[2]);
    await p.waitForFunction(() => window.CivicShell && window.CivicShell.heat && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 }); await p.waitForTimeout(1200);
    const anchor = await p.evaluate(async () => { const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=16")).json(); const it = (d.data || d).items.find((x) => /Хан Шатыр/.test(x.target.label_ru || "")); return it && it.anchor; });
    if (!(await p.isVisible(".bc-fab"))) await p.keyboard.press("Escape");
    await p.click(".bc-fab"); await p.waitForSelector(".bc-panel[data-step='2']"); await p.waitForTimeout(500);
    const xy = await p.evaluate((a) => {
      map.jumpTo({ center: a, zoom: 17 });
      const c = map.getCanvas().getBoundingClientRect(), r = map.project(a);
      const want = innerWidth < 1024 ? { x: innerWidth / 2, y: 240 } : { x: 400, y: 380 };   // свободная часть карты
      map.panBy([r.x + c.left - want.x, r.y + c.top - want.y], { animate: false });
      const r2 = map.project(a); return { x: c.left + r2.x, y: c.top + r2.y };
    }, anchor);
    await p.waitForTimeout(600); await p.mouse.click(xy.x, xy.y); await p.waitForTimeout(1500);
    const opts = await p.$$eval(".bc-option__label", (xs) => xs.map((x) => x.textContent.trim()).slice(0, 4));
    const khan = await p.$("xpath=//button[contains(@class,'bc-option')][.//*[contains(text(),'Хан Шатыр')]]");
    if (khan) await khan.click(); else if (await p.$(".bc-option--first")) await p.click(".bc-option--first");
    await p.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
    await p.fill("#bc-text", "Аялдамада жарық жоқ, вечером на остановке темно"); await p.waitForTimeout(3500);
    await p.click(".bc-send"); await p.waitForTimeout(2500);
    const step = await p.evaluate(() => document.querySelector(".bc-panel") && document.querySelector(".bc-panel").getAttribute("data-step"));
    await p.screenshot({ path: `${process.argv[3]}/metoo-${w}-${lang}.png` });
    const txt = await p.evaluate(() => (document.querySelector(".bc-panel") || {}).innerText || "");
    console.log(w, lang, "варианты:", JSON.stringify(opts), "шаг после «Жіберу»:", step, "|", txt.replace(/\s+/g, " ").slice(0, 260));
    await p.close();
  }
  await b.close();
})();
