// Кадры макета ui-kit prototypes/reference-a.html (?f=home|obj|proj|phone) → <OUT>/proto-<f>.png. node ref_proto_shots.cjs <OUT> [URL]
const { chromium } = require('playwright');
(async () => {
  const out = process.argv[2], base = process.argv[3] || 'http://127.0.0.1:8766/civic/ui-kit/prototypes/reference-a.html';
  const b = await chromium.launch();
  for (const f of ['home','obj','proj','phone']) {
    const vp = f === 'phone' ? { width: 375, height: 812 } : { width: 1366, height: 768 };
    const p = await b.newPage({ viewport: vp, deviceScaleFactor: 1 });
    await p.goto(base + '?f=' + f, { waitUntil: 'networkidle' });
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(400);
    await p.locator('.ra-frame.is-on').screenshot({ path: `${out}/proto-${f}.png` });
    await p.close();
  }
  await b.close();
})();
