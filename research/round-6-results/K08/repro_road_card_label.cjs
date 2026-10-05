// K08 R6: минимальное воспроизведение подписи карточки дороги для не-OSM сегмента.
// Usage: NODE_PATH=$(npm root -g) node repro_road_card_label.cjs --app-root <prototypes/city-evidence>
// Открывает web/index.html (file://), переключает город, открывает карточку каждого TomTom-сегмента
// клавишей Enter и сравнивает заголовок карточки с полем dataset. Выход 1 — если заголовок говорит OSM для не-OSM.
const { chromium } = require("playwright");
const path = require("path");
const i = process.argv.indexOf("--app-root");
if (i < 0) { console.error("нужен --app-root"); process.exit(2); }
const root = path.resolve(process.argv[i + 1]);
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage();
  const errors = []; pg.on("pageerror", (e) => errors.push(String(e)));
  await pg.goto("file://" + path.join(root, "web", "index.html"));
  const out = [];
  for (const city of ["shymkent", "astana"]) {
    await pg.click(`button[data-city="${city}"]`);
    const idx = await pg.evaluate((c) => window.CITY_EVIDENCE.cities[c].segments
      .map((s, k) => [s.dataset, k, s.id]).filter(([d]) => d && d !== "OpenStreetMap"), city);
    for (const [dataset, k, id] of idx) {
      const hits = pg.locator('path[role="button"][aria-label^="Дорога"]');
      await hits.nth(k).focus(); await pg.keyboard.press("Enter");
      const card = await pg.evaluate(() => { const h = [...document.querySelectorAll("h3")].find((x) => x.textContent.startsWith("Дорога"));
        const src = [...document.querySelectorAll("dt")].find((x) => x.textContent.startsWith("Источник"));
        return { h3: h ? h.textContent : null, source: src && src.nextElementSibling ? src.nextElementSibling.textContent : null }; });
      const bad = !!(card.h3 && /OSM/.test(card.h3));
      out.push({ city, segment_id: id, dataset, heading: card.h3, source_row: card.source, mislabeled: bad });
    }
  }
  await b.close();
  const n = out.filter((x) => x.mislabeled).length;
  console.log(JSON.stringify({ app_root: root, non_osm_segments: out.length, mislabeled: n, page_errors: errors, cases: out }, null, 1));
  process.exit(n || errors.length ? 1 : 0);
})();
