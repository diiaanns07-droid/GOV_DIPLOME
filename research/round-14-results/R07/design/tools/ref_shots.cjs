// Эталон (вариант A) 1:1: кадры «Главная акимата», «Выбран объект», «Проекты», «Житель, телефон» без масштаба.
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const OUT = process.argv[2], DPR = Number(process.argv[3] || 1);
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const p = await b.newPage({ viewport: { width: 1414, height: 1000 }, deviceScaleFactor: DPR });
  await p.goto("http://127.0.0.1:8790/REFERENCE.html");
  await p.waitForTimeout(500);
  for (const f of ["home", "obj", "proj"]) {
    await p.click(`.switch button[data-f="${f}"]`); await p.waitForTimeout(300);
    const w = await p.evaluate(() => document.getElementById("stage").clientWidth);
    await p.locator("#stage").screenshot({ path: `${OUT}/ref-${f}-1366.png` });
    console.log(f, "stage", w);
  }
  await p.click(`.switch button[data-f="phone"]`); await p.waitForTimeout(300);
  await p.locator("#stagePhone").screenshot({ path: `${OUT}/ref-phone-375.png` });
  // размеры и цвета значков и карточки эталона — для сверки числами
  await p.click(`.switch button[data-f="obj"]`); await p.waitForTimeout(300);
  const m = await p.evaluate(() => {
    const cs = (s) => { const e = document.querySelector(s); if (!e) return null; const c = getComputedStyle(e); const r = e.getBoundingClientRect(); return { w: r.width, h: r.height, bg: c.backgroundColor, color: c.color, fs: c.fontSize, fw: c.fontWeight, radius: c.borderRadius, shadow: c.boxShadow, border: c.border, pad: c.padding }; };
    return { pin: cs('.frame.on .pin:not(.sel) .c'), n: cs('.frame.on .pin .n'), sel: cs('.frame.on .pin.sel .c'), card: cs('.frame.on .card'), h2: cs('.frame.on .card h2'), sub: cs('.frame.on .card .sub'), tile: cs('.frame.on .tile'), big: cs('.frame.on .big b'), st: cs('.frame.on .st'), btn: cs('.frame.on .btn.p'), btn2: cs('.frame.on .btn.s'), tabs: cs('.frame.on .tabs a.on'), row: cs('.frame.on .row'), quote: cs('.frame.on .quote'), more: cs('.frame.on .more'), x: cs('.frame.on .x') };
  });
  console.log(JSON.stringify(m, null, 1));
  await b.close();
})();
