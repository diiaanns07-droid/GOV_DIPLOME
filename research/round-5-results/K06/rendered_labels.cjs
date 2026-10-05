// K06 round 5: collect RENDERED labels/numbers of the city-evidence demo (Playwright Chromium).
// Usage: NODE_PATH=$(npm root -g) node rendered_labels.cjs <file:///.../web/index.html | http://host:port/>
// Prints JSON with what the user actually sees; verification is done by rendered_check.py.
const { chromium } = require("playwright");

(async () => {
  const target = process.argv[2];
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(target);
  await page.waitForSelector("#tbl tr");
  const out = { target, cities: {}, errors };
  for (const city of ["shymkent", "astana"]) {
    await page.click(`#citySeg button[data-city="${city}"]`);
    await page.waitForFunction((c) => CITY_APP.state.city === c, city);
    const r = { slice: await page.textContent("#sliceBody") };
    // data the page itself loaded (arrays, not the precomputed counts)
    r.data = await page.evaluate((c) => {
      const C = window.CITY_EVIDENCE.cities[c], [w, s, e, n] = C.bbox;
      const inside = ([x, y]) => x >= w && x <= e && y >= s && y <= n;
      const cross = C.segments.map((sg, i) => [i, sg]).filter(([, sg]) => !sg.coords.every(inside));
      const keep = C.segments.map((sg, i) => [i, sg]).filter(([, sg]) => sg.coords.every(inside));
      const pick = (arr) => arr.slice().sort((a, b) => b[1].length_m - a[1].length_m)[0];
      const [ci, cs] = pick(cross), [ki, ks] = pick(keep);
      return { places: C.places.length, segments: C.segments.length, crossing: cross.length, bbox: C.bbox,
               cross_seg: { index: ci, id: cs.id, length_m: cs.length_m, coords: cs.coords },
               inner_seg: { index: ki, id: ks.id, length_m: ks.length_m, coords: ks.coords } };
    }, city);
    // road cards: click the transparent hit path of the chosen segments
    for (const key of ["cross_seg", "inner_seg"]) {
      await page.evaluate((i) => document.querySelectorAll('#map path[role="button"]')[i].dispatchEvent(new MouseEvent("click", { bubbles: true })), r.data[key].index);
      r[key + "_card"] = await page.textContent("#selBody");
      r[key + "_selected"] = await page.evaluate(() => CITY_APP.state.selected && CITY_APP.state.selected.id);
    }
    // point mode: click empty map spots until a point card appears
    await page.click("#pointBtn");
    const box = await (await page.$("#map")).boundingBox();
    r.point_card = null;
    for (const [fx, fy] of [[0.5, 0.5], [0.45, 0.55], [0.55, 0.45], [0.4, 0.4], [0.6, 0.6], [0.35, 0.65], [0.65, 0.35]]) {
      await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
      const sel = await page.evaluate(() => CITY_APP.state.selected && CITY_APP.state.selected.type);
      if (sel === "point") {
        r.point = await page.evaluate(() => CITY_APP.state.point);
        r.point_card = await page.textContent("#selBody");
        r.point_rows = await page.evaluate(() => [...document.querySelectorAll("#selBody tbody tr")].map((tr) => [...tr.children].map((td) => td.textContent)));
        r.point_header = await page.evaluate(() => [...document.querySelectorAll("#selBody thead th")].map((t) => t.textContent));
        r.point_places = await page.evaluate(() => CITY_APP.visiblePlaces().map((p) => ({ name: p.name || "Без названия", lon: p.lon, lat: p.lat })));
        break;
      }
    }
    await page.click("#pointBtn");
    r.table_count = await page.textContent("#tblCount");
    r.banner = await page.textContent("#banner");
    r.explain_catalog = await page.textContent("#explainBody details").catch(() => null);
    r.body_text = await page.evaluate(() => document.body.innerText);
    out.cities[city] = r;
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(2); });
