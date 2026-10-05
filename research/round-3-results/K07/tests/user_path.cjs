// K07 round 3: headless check of the main user path of prototype/index.html (file://, no server, no network).
// Usage (repo root): node research/round-3-results/K07/tests/user_path.cjs
// Needs: Node + playwright (preinstalled Chromium). Writes results/user_path_test.json and prototype/screenshots/*.png
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

const K07 = path.resolve(__dirname, "..");
const URL = "file://" + path.join(K07, "prototype/index.html");
const SHOTS = path.join(K07, "prototype/screenshots");
const checks = [];
function check(name, ok, detail) { checks.push({ name, ok: !!ok, detail: detail === undefined ? null : detail }); }

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 }, colorScheme: "light" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  const requests = [];
  page.on("request", (r) => requests.push(r.url()));

  await page.goto(URL);
  await page.waitForSelector("#map g[data-id]");
  const count = () => page.locator("#map g[data-id]").count();

  // 1. Shymkent by default
  check("title", (await page.title()) === "Карта доступности K07", await page.title());
  check("Shymkent selected by default", await page.locator('#citySeg button[data-city="shymkent"]').getAttribute("aria-pressed") === "true");
  check("Shymkent: 95 sample objects on the map", (await count()) === 95, await count());
  check("Shymkent: 4 district labels", (await page.locator("#map text").filter({ hasText: "ауданы" }).count()) === 4, await page.locator("#map text").filter({ hasText: "ауданы" }).count());
  check("Shymkent: table shows 95 of 95", (await page.textContent("#tblCount")).includes("95 из 95"), await page.textContent("#tblCount"));
  const prov = await page.textContent("#provBody");
  check("provenance: release and K10 SHA", prov.includes("2026-09-23.1") && prov.includes("e91898d"), null);
  check("provenance: sample vs extract table present", prov.includes("В выгрузке"), null);
  const graph = await page.textContent("#graphBody");
  check("graph: view-only status", graph.includes("Только просмотр данных") && graph.includes("view_only"), null);
  check("graph: 4 reasons", (await page.locator("#graphBody ul.reasons li").count()) === 4, await page.locator("#graphBody ul.reasons li").count());
  check("graph: K10 request with clip", graph.includes("69.57896") && graph.includes("Запрос к K10"), null);
  await page.screenshot({ path: path.join(SHOTS, "01_shymkent_overview.png") });

  // 2. select an object by mouse (topmost marker: in the dense centre markers overlap, the table is the fallback)
  const top = page.locator("#map g[data-id]").last();
  const topName = await top.getAttribute("aria-label");
  await top.click();
  const sel = await page.textContent("#selBody");
  check("mouse click selects the clicked object", sel.includes(topName.split(",")[0]), topName);
  check("object card opens on click", sel.includes("Мощность / места") && sel.includes("неизвестно") && sel.includes("производное K07"), sel.slice(0, 120));
  check("object card lists sources with licence", /CDLA|CC0|Apache/.test(sel), null);

  // 2b. select via the table view (reaches objects hidden under other markers)
  const row = page.locator("#tbl tr").nth(3);
  const rowName = await row.locator("td").first().textContent();
  await row.click();
  check("table row selects object and highlights it", (await page.textContent("#selBody")).includes(rowName) &&
        (await page.locator("#map g[data-id] circle[r='10']").count()) === 1, rowName);

  // 3. keyboard selection of a road segment
  await page.locator('#map path[role="button"]').first().focus();
  await page.keyboard.press("Enter");
  const segCard = await page.textContent("#selBody");
  check("road card by keyboard: permission unknown", segCard.includes("Дорога из выборки K10") && segCard.includes("нет access_restrictions"), null);

  // 4. switch to Astana and filter
  await page.click('#citySeg button[data-city="astana"]');
  check("Astana: 105 sample objects", (await count()) === 105, await count());
  check("Astana: 6 district labels", (await page.locator("#map text").filter({ hasText: "ауданы" }).count()) === 6, await page.locator("#map text").filter({ hasText: "ауданы" }).count());
  await page.uncheck('input[data-group="school"]');
  check("filter: schools off -> 90 objects", (await count()) === 90, await count());
  check("filter: table follows (90 из 105)", (await page.textContent("#tblCount")).includes("90 из 105"), await page.textContent("#tblCount"));
  check("selection cleared on city switch", !(await page.isHidden("#selEmpty")) || (await page.textContent("#selBody")) === "", null);
  await page.check('input[data-group="school"]');

  // 5. point mode inside the city, threshold change
  await page.click("#pointBtn");
  const pt = await page.evaluate(() => {
    const c = window.K07_DATA.cities.astana.k10_request_clip.centre;
    const [x, y] = window.K07_APP.toScreen(c[0], c[1]);
    const r = document.getElementById("map").getBoundingClientRect();
    return { x: r.left + x + 40, y: r.top + y + 40 };
  });
  await page.mouse.click(pt.x, pt.y);
  let ptxt = await page.textContent("#selBody");
  check("point analysis shown", ptxt.includes("порог T = 800 м"), ptxt.slice(0, 80));
  check("point: network distance not computed (view_only)", ptxt.includes("Расстояние по сети не рассчитано") && ptxt.includes("Сеть") &&
        (await page.locator("#selBody tbody td:nth-child(4)").allTextContents()).every((t) => t === "—"), null);
  check("point: no 'unreachable' wording", !/недостиж/i.test(ptxt), null);
  check("point inside city: no outside warning", !ptxt.includes("вне полигона"), null);
  await page.fill("#thr", "2000");
  await page.dispatchEvent("#thr", "input");
  ptxt = await page.textContent("#selBody");
  check("threshold updates analysis and map label", ptxt.includes("порог T = 2000 м") && (await page.textContent("#map")).includes("T = 2000 м"), null);
  await page.screenshot({ path: path.join(SHOTS, "02_astana_point_T2000.png") });

  // 6. point outside the city polygon
  const r = await page.evaluate(() => { const b = document.getElementById("map").getBoundingClientRect(); return { x: b.left + 25, y: b.top + 25 }; });
  await page.mouse.click(r.x + 30, r.y + 60);
  ptxt = await page.textContent("#selBody");
  check("point outside city: warning", ptxt.includes("вне полигона города"), ptxt.slice(0, 120));

  // 7. empty state: no groups selected
  for (const g of await page.locator("input[data-group]").all()) await g.uncheck();
  check("empty state on map", (await page.isVisible("#mapMsg")) && (await page.textContent("#mapMsg")).includes("Не выбрана ни одна группа"), null);
  check("empty state in table", (await page.textContent("#tbl")).includes("Не выбрана ни одна группа"), null);
  check("empty state in point analysis", (await page.textContent("#selBody")).includes("Не выбрана ни одна группа"), null);

  check("no network requests besides local files", requests.every((u) => u.startsWith("file://")), requests.filter((u) => !u.startsWith("file://")));
  check("no console or page errors", errors.length === 0, errors);

  // 8. error state when data.js is missing
  const p2 = await ctx.newPage();
  await p2.route("**/data.js", (route) => route.abort());
  await p2.goto(URL);
  check("error state when data.js missing", (await p2.textContent("main")).includes("Данные не найдены"), null);

  // 9. dark mode renders
  const dark = await browser.newContext({ viewport: { width: 1400, height: 900 }, colorScheme: "dark" });
  const p3 = await dark.newPage();
  await p3.goto(URL);
  await p3.waitForSelector("#map g[data-id]");
  const bg = await p3.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check("dark mode uses dark page token", bg === "rgb(13, 13, 13)", bg);
  await p3.screenshot({ path: path.join(SHOTS, "03_shymkent_dark.png") });

  // 10. narrow screen: no horizontal page scroll
  const narrow = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const p4 = await narrow.newPage();
  await p4.goto(URL);
  await p4.waitForSelector("#map g[data-id]");
  const sw = await p4.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  check("390 px wide: no horizontal page scroll", sw[0] <= sw[1], sw);

  await browser.close();
  const out = { kind: "headless user-path check (Chromium via Playwright)", url: "prototype/index.html (file://)",
    passed: checks.every((c) => c.ok), total: checks.length, failed: checks.filter((c) => !c.ok).map((c) => c.name), checks };
  fs.mkdirSync(path.join(K07, "results"), { recursive: true });
  fs.writeFileSync(path.join(K07, "results/user_path_test.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log((c.ok ? "PASS " : "FAIL ") + c.name + (c.ok ? "" : "  -> " + JSON.stringify(c.detail)));
  console.log(out.passed ? `ALL ${out.total} CHECKS PASSED` : `${out.failed.length} FAILED`);
  process.exit(out.passed ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
