// R14 · кадры эталона REFERENCE.html (вариант A) один к одному: 1366×768 и 375×812.
// node ref_shots.cjs <REFERENCE.html> <папка кадров>
// Эталон масштабирует кадр под ширину страницы; здесь сцене ставится точный размер, кадр — без масштаба.
const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
const SRC = path.resolve(process.argv[2]), OUT = path.resolve(process.argv[3] || "ref");
fs.mkdirSync(OUT, { recursive: true });
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 }, deviceScaleFactor: 1 });
  await page.goto("file://" + SRC);
  await page.click('.vswitch button[data-v="v-a"]');
  for (const f of ["home", "obj", "proj", "phone"]) {
    await page.click(`.switch button[data-f="${f}"]`);
    const sel = f === "phone" ? "#stagePhone" : "#stage";
    await page.evaluate(([s, ph]) => {
      const st = document.querySelector(s);
      st.style.width = ph ? "375px" : "1366px"; st.style.maxWidth = "none"; st.style.borderRadius = "0"; st.style.boxShadow = "none";
      st.querySelectorAll(".frame").forEach(x => { x.style.transform = "none"; });
    }, [sel, f === "phone"]);
    await page.waitForTimeout(400);
    const name = (f === "phone" ? "375" : "1366") + "-ref-a-" + f + ".png";
    await page.locator(sel).screenshot({ path: path.join(OUT, name) });
    console.log(name);
  }
  await browser.close();
})();
