/*
 * R11 · «Картина дня» R08 в сборке R01 целиком: прокрутка контейнера #birge-day кадрами по высоте экрана,
 * 375/1366 × kk/ru; в консоль — высота и элементы, вылезающие за правый край.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/day_scroll_shots.cjs http://127.0.0.1:<порт>/ <папка>
 */
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const [w, h] of [[375, 812], [1366, 768]]) for (const lang of ["kk", "ru"]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h } });
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.addInitScript((l) => { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", "akimat"); }, lang);
    await p.goto(process.argv[2]);
    await p.waitForFunction(() => window.CivicShell && window.CivicShell.heat && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 }); await p.waitForTimeout(1000);
    await p.evaluate(() => document.querySelector("#birge-header [data-section=day]").click());
    await p.waitForSelector("#birge-day .akim-hot__item", { timeout: 15000 }); await p.waitForTimeout(1200);
    const sh = await p.evaluate(() => { const r = document.getElementById("birge-day"); return { sh: r.scrollHeight, ch: r.clientHeight }; });
    let i = 0;
    for (let y = 0; y < sh.sh && i < 12; y += sh.ch - 60, i++) {
      await p.evaluate((y) => { document.getElementById("birge-day").scrollTop = y; }, y);
      await p.waitForTimeout(250);
      await p.screenshot({ path: `${process.argv[3]}/day-${w}-${lang}-${String(i).padStart(2, "0")}.png` });
    }
    const wide = await p.evaluate(() => [...document.querySelectorAll("#birge-day *")].filter((x) => { const r = x.getBoundingClientRect(); return r.width && r.right > innerWidth + 1; }).map((x) => x.className).slice(0, 5));
    console.log(w, lang, JSON.stringify(sh), i, "кадров", JSON.stringify(wide));
    await ctx.close();
  }
  await b.close();
})();
