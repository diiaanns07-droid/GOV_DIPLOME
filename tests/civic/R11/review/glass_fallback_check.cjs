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
  // Намеренные исключения GLASS.md: нажатая кнопка (aria-pressed / aria-expanded) — сплошной акцент; кнопка-стекло внутри
  // стеклянной строки — плоская прозрачная; стекло внутри стекла (меню в шапке) — сплошное белое в любом режиме.
  const state = () => p.evaluate(() => [...document.querySelectorAll(".bk-glass, .bk-glass--control")].filter((e) => e.getClientRects().length)
    .map((e) => { const c = getComputedStyle(e), outer = e.parentElement && e.parentElement.closest(".bk-glass");
      return { name: (e.id ? "#" + e.id : "") + "." + [...e.classList].slice(0, 2).join("."), bg: c.backgroundColor, bf: c.backdropFilter || c.webkitBackdropFilter || "none",
        pressed: e.matches("[aria-pressed=true], [aria-expanded=true]"), nested: !!outer, control: e.matches(".bk-glass--control") }; }));
  let bad = 0;
  const check = (name, list, opaque) => {
    const ok = (x) => {
      if (x.pressed) return x.bf === "none" || /rgb\(21, 44, 38\)/.test(x.bg);         // сплошной #152c26
      if (x.nested && x.control) return x.bf === "none";                                 // плоская внутри строки
      if (x.nested) return x.bg === "rgb(255, 255, 255)" && x.bf === "none";             // меню в стеклянной шапке
      return opaque ? x.bg === "rgb(255, 255, 255)" && x.bf === "none" : x.bf !== "none" && /rgba\(255, 255, 255, 0\.\d+\)/.test(x.bg);
    };
    const wrong = list.filter((x) => !ok(x));
    console.log(`${wrong.length ? "FAIL" : "PASS"} ${name}: элементов ${list.length}, не так — ${wrong.length}${wrong.length ? " · " + wrong.map((x) => `${x.name} ${x.bg} ${x.bf}`).join(" | ") : ""}`);
    bad += wrong.length || (list.length ? 0 : 1);
  };
  await p.goto(URL, { waitUntil: "networkidle" }); await p.waitForTimeout(800);
  check("стекло по умолчанию", await state(), false);
  await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] });
  await p.waitForTimeout(700); // переход фона кнопок 200 мс — читаем после него
  check("prefers-reduced-transparency: reduce → белый", await state(), true);
  await cdp.send("Emulation.setEmulatedMedia", { features: [] });
  await p.evaluate(() => document.documentElement.classList.add("bk-glass-off")); await p.waitForTimeout(700); // переход фона кнопок 200 мс — читаем после него
  check("html.bk-glass-off → белый", await state(), true);
  await b.close();
  process.exit(bad ? 1 : 0);
})();
