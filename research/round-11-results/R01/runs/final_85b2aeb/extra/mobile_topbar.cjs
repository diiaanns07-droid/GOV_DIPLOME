// R01 evidence (C5/C18): at 390x844 the top bar fits in all three modes. Usage: node mobile_topbar.cjs <base_url> <out_dir>
"use strict";
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const [base, out] = process.argv.slice(2);
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  let ok = true;
  for (const mode of ["civic", "training", "school"]) {
    const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
    const p = await ctx.newPage();
    const errs = []; p.on("pageerror", (e) => errs.push(e.message));
    await p.goto(base + "#" + mode);
    await p.waitForFunction(() => typeof mapReady !== "undefined" && mapReady, null, { timeout: 30000 });
    await p.waitForTimeout(1500);
    const r = await p.evaluate(() => {
      const m = document.getElementById("civic-modes").getBoundingClientRect();
      const tog = document.getElementById("govtech-toggle");
      return { mode: window.CivicShell.mode, scrollW: document.documentElement.scrollWidth, modes: [Math.round(m.left), Math.round(m.right)],
        legacyToggleVisible: !!tog && getComputedStyle(tog).display !== "none" };
    });
    const pass = r.mode === mode && r.scrollW <= 390 && r.modes[0] >= 0 && r.modes[1] <= 390 && !r.legacyToggleVisible && errs.length === 0;
    ok = ok && pass;
    console.log((pass ? "PASS " : "FAIL ") + JSON.stringify(r) + (errs.length ? " errors=" + JSON.stringify(errs) : ""));
    await p.screenshot({ path: path.join(out, `topbar_${mode}_390.png`), clip: { x: 0, y: 0, width: 390, height: 120 } });
    await ctx.close();
  }
  await b.close();
  process.exit(ok ? 0 : 1);
})();
