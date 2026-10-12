/*
 * R11 · стекло (GLASS.md): запасной непрозрачный вид работает.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/glass_fallback_check.cjs <url>
 * Обычно у .bk-glass / .bk-glass--control — полупрозрачный белый и backdrop-filter; при системной настройке
 * «уменьшить прозрачность» (эмуляция prefers-reduced-transparency через CDP) и с классом html.bk-glass-off —
 * непрозрачный белый rgb(255,255,255) без backdrop-filter.
 */
"use strict";
const { chromium } = require("playwright");
const URL = process.argv[2] || "http://127.0.0.1:8766/civic/ui-kit/prototypes/glass.html";
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1366, height: 768 } });
  const cdp = await p.context().newCDPSession(p);
  const state = () => p.evaluate(() => [...document.querySelectorAll(".bk-glass, .bk-glass--control")].filter((e) => e.getClientRects().length)
    .map((e) => { const c = getComputedStyle(e); return { bg: c.backgroundColor, bf: c.backdropFilter || c.webkitBackdropFilter || "none" }; }));
  let bad = 0;
  const check = (name, list, opaque) => {
    const wrong = list.filter((x) => opaque ? !(x.bg === "rgb(255, 255, 255)" && x.bf === "none") : (x.bf === "none" || !/rgba\(255, 255, 255, 0\.\d+\)/.test(x.bg)));
    console.log(`${wrong.length ? "FAIL" : "PASS"} ${name}: элементов ${list.length}, не так — ${wrong.length}`); bad += wrong.length || (list.length ? 0 : 1);
  };
  await p.goto(URL, { waitUntil: "networkidle" }); await p.waitForTimeout(800);
  check("стекло по умолчанию", await state(), false);
  await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] });
  await p.waitForTimeout(200);
  check("prefers-reduced-transparency: reduce → белый", await state(), true);
  await cdp.send("Emulation.setEmulatedMedia", { features: [] });
  await p.evaluate(() => document.documentElement.classList.add("bk-glass-off")); await p.waitForTimeout(200);
  check("html.bk-glass-off → белый", await state(), true);
  await b.close();
  process.exit(bad ? 1 : 0);
})();
