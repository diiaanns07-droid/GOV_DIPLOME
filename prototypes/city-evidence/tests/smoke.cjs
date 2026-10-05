// Headless smoke test of web/index.html via file:// (Playwright, Chromium). Usage:
//   NODE_PATH=$(npm root -g) node tests/smoke.cjs [outdir]
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
const out = process.argv[2] || path.join(__dirname, "..", "..", "..", "research", "round-4-results", "BUILD", "smoke");
fs.mkdirSync(out, { recursive: true });
const url = "file://" + path.resolve(__dirname, "..", "web", "index.html");
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail }); console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : "")); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", (r) => { if (!r.url().startsWith("file://")) requests.push(r.url()); });
  await page.goto(url);
  await page.waitForSelector("#tbl tr");

  const s1 = await page.evaluate(() => ({ city: CITY_APP.state.city, rows: document.querySelectorAll("#tbl tr").length,
    count: document.getElementById("tblCount").textContent, markers: document.querySelectorAll("#map g[data-id]").length }));
  check("shymkent loads with table and markers", s1.city === "shymkent" && s1.rows === 55 && s1.markers === 55, JSON.stringify(s1));
  await page.screenshot({ path: path.join(out, "01_shymkent.png") });

  // select an object via the table -> card shows name + "Мощность / места: нет данных"
  await page.click("#tbl tr:first-child");
  const card = await page.textContent("#selBody");
  check("object card opens from table", card.includes("Мощность / места") && card.includes("нет данных"), card.slice(0, 80));
  const selId = await page.evaluate(() => CITY_APP.state.selected && CITY_APP.state.selected.id);

  // switch city -> selection, point and old rows must be gone
  await page.click('#citySeg button[data-city="astana"]');
  const s2 = await page.evaluate((old) => ({ city: CITY_APP.state.city, sel: CITY_APP.state.selected, rows: document.querySelectorAll("#tbl tr").length,
    hasOld: !!document.querySelector(`#map g[data-id="${old}"]`), selText: document.getElementById("selBody").textContent,
    slice: document.getElementById("sliceBody").textContent }), selId);
  check("astana resets selection and shows its own slice", s2.city === "astana" && s2.sel === null && s2.rows === 65 && !s2.hasOld && s2.selText === "" && s2.slice.includes("65 в срезе"), JSON.stringify({ ...s2, slice: undefined, selText: undefined }));
  await page.screenshot({ path: path.join(out, "02_astana.png") });

  // filter: only schools -> table has 8 rows; then none -> clear empty state
  await page.evaluate(() => document.querySelectorAll("#groupFilters input").forEach((cb) => { if (cb.dataset.group !== "school") cb.click(); }));
  const schools = await page.evaluate(() => document.querySelectorAll("#tbl tr").length);
  check("category filter (Astana schools = 8 records)", schools === 8, String(schools));
  await page.evaluate(() => document.querySelector('#groupFilters input[data-group="school"]').click());
  const empty = await page.evaluate(() => ({ msg: document.getElementById("mapMsg").textContent, hidden: document.getElementById("mapMsg").hidden, tbl: document.getElementById("tbl").textContent }));
  check("empty state is explicit", !empty.hidden && empty.msg.includes("Не выбрана ни одна категория") && empty.tbl.includes("Не выбрана"), empty.msg);
  await page.screenshot({ path: path.join(out, "03_empty_state.png") });
  await page.evaluate(() => document.querySelectorAll("#groupFilters input").forEach((cb) => cb.click()));

  // road style by foot access + segment card
  await page.selectOption("#roadStyle", "foot");
  await page.evaluate(() => { const h = document.querySelector('#map path[role="button"]'); h.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  const seg = await page.textContent("#selBody");
  check("segment card shows foot-access status and no walking time", seg.includes("Проход пешком") && !/мин\b/.test(seg), seg.slice(0, 100));

  // narrow viewport: no horizontal page scroll
  await page.setViewportSize({ width: 380, height: 800 });
  await page.waitForTimeout(150);
  const sw = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  check("narrow viewport has no horizontal scroll", sw.sw <= sw.cw + 1, JSON.stringify(sw));
  await page.screenshot({ path: path.join(out, "04_narrow.png"), fullPage: false });

  check("no console/page errors", errors.length === 0, errors.join(" | "));
  check("no network requests (file:// only)", requests.length === 0, requests.join(" "));
  await browser.close();
  fs.writeFileSync(path.join(out, "smoke_result.json"), JSON.stringify({ url: "web/index.html (file://)", results }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
