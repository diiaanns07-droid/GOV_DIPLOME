// K07 r10 F3: 3D-кнопка без подложки (base :8501 vs patch :8502). Usage: node k07r10_f3_3d_offline.cjs
const { chromium } = require("playwright");
(async () => { const b = await chromium.launch(); for (const port of [8501, 8502]) { const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
 await pg.goto(`http://127.0.0.1:${port}/`); await pg.waitForTimeout(800); await pg.click("#govtech-toggle"); await pg.waitForTimeout(300);
 await pg.click("#toggle-3d"); await pg.waitForTimeout(300);
 console.log(port, JSON.stringify(await pg.evaluate(() => ({ pressed: document.getElementById("toggle-3d").getAttribute("aria-pressed"), toasts: [...document.querySelectorAll("[class*=toast], #toast")].map(t => t.textContent.trim()).filter(Boolean) })))); await pg.close(); }
 await b.close(); })();
