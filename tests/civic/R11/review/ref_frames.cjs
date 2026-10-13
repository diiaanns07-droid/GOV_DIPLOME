const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1500, height: 1100 } });
  await p.goto("http://127.0.0.1:8790/REFERENCE.html", { waitUntil: "load" }); await p.waitForTimeout(800);
  for (const f of ["home", "obj", "proj", "phone"]) {
    await p.click(`.switch button[data-f=${f}]`); await p.waitForTimeout(300);
    const sel = f === "phone" ? "#stagePhone .frame.on" : `#stage .frame[data-f=${f}]`;
    await p.evaluate((s) => { const fr = document.querySelector(s); fr.style.transform = "none"; const st = fr.parentElement; st.style.width = fr.offsetWidth + "px"; st.style.maxWidth = "none"; st.style.aspectRatio = "auto"; st.style.height = fr.offsetHeight + "px"; st.style.borderRadius = "0"; }, sel);
    await p.waitForTimeout(300);
    const el = await p.$(sel);
    await el.screenshot({ path: `${process.argv[2]}/ref-${f}.png` });
    console.log(f, JSON.stringify(await el.boundingBox()));
  }
  await b.close();
})();
