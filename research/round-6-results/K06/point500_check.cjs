// K06 round 6: one-off check of the new "N записей … в пределах 500 м по прямой" status (BUILD 064ed25).
// Usage: NODE_PATH=$(npm root -g) node point500_check.cjs <index.html URL>  -> JSON for point500_check.py
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(), page = await b.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(process.argv[2]); await page.waitForSelector("#tbl tr");
  const out = {};
  for (const city of ["shymkent", "astana"]) {
    await page.click(`#citySeg button[data-city="${city}"]`);
    await page.click("#pointBtn");
    const box = await (await page.$("#map")).boundingBox();
    for (const [fx, fy] of [[0.5, 0.5], [0.45, 0.55], [0.55, 0.45], [0.4, 0.4], [0.6, 0.6]]) {
      await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
      if (await page.evaluate(() => CITY_APP.state.selected && CITY_APP.state.selected.type === "point")) break;
    }
    out[city] = await page.evaluate(() => ({ point: CITY_APP.state.point,
      status: [...document.querySelectorAll("body *")].map((e) => e.childElementCount ? "" : e.textContent).find((t) => t.startsWith("Точка выбрана")) || null,
      places: CITY_APP.visiblePlaces().map((p) => [p.lon, p.lat]) }));
    await page.click("#pointBtn");
  }
  await b.close(); console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(2); });
