// K10 round-5 REVIEW: UI check of a stacked-coordinate group in the city-evidence BUILD (Playwright, Chromium).
// Usage:
//   NODE_PATH=$(npm root -g) node ui_coord_group.cjs --app-root <extracted prototypes/city-evidence> [--json out.json]
//   NODE_PATH=$(npm root -g) node ui_coord_group.cjs --url http://127.0.0.1:8765/ [--json out.json]
//   optional: --fixture <path>  (default ../fixtures/ui_coord_group_shymkent.json)
// MUST failures -> exit 1. SHOULD checks are proposals of this review: FAIL on baseline 0bf27de is expected.
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const args = process.argv.slice(2);
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const appRoot = opt("--app-root"), base = opt("--url");
if (!!appRoot === !!base) { console.error("give exactly one of --app-root or --url"); process.exit(2); }
const fx = JSON.parse(fs.readFileSync(opt("--fixture") || path.join(__dirname, "..", "fixtures", "ui_coord_group_shymkent.json"), "utf8"));
const target = appRoot ? "file://" + path.resolve(appRoot, "web", "index.html") : (base.endsWith("/") ? base : base + "/");
const BASELINE_EXPECTED_FAIL = new Set(["SHOULD_group_indicated_in_ui", "SHOULD_each_group_record_selectable_from_map"]);
const results = [];
const check = (name, level, ok, detail) => {
  results.push({ check: name, level, status: ok ? "PASS" : "FAIL", detail, expected_fail_at_baseline_0bf27de: BASELINE_EXPECTED_FAIL.has(name) });
  console.log(`${ok ? "PASS" : "FAIL"} [${level}] ${name} ${JSON.stringify(detail)}`);
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(target);
  await page.waitForSelector("#tbl tr");
  const city = await page.evaluate(() => CITY_APP.state.city);
  if (city !== fx.city) {
    await page.click(`#citySeg button[data-city="${fx.city}"]`);
    await page.waitForFunction((c) => CITY_APP.state.city === c, fx.city);
  }

  // MUST: every group record is rendered and listed
  const info = await page.evaluate((ids) => {
    const places = CITY_APP.visiblePlaces();
    const byId = Object.fromEntries(places.map((p) => [p.id, p]));
    const marks = ids.map((id) => {
      const g = document.querySelector(`#map g[data-id="${id}"]`);
      if (!g) return { id, rendered: false };
      const r = g.getBoundingClientRect();
      return { id, rendered: true, transform: g.getAttribute("transform"), cx: r.x + r.width / 2, cy: r.y + r.height / 2, name: byId[id] ? byId[id].name : null };
    });
    return { visible: places.length, rows: document.querySelectorAll("#tbl tr").length, marks };
  }, fx.ids);
  const rendered = info.marks.filter((m) => m.rendered);
  check("MUST_all_group_records_rendered_as_markers", "MUST", rendered.length === fx.ids.length, { rendered: rendered.length, of: fx.ids.length });
  check("MUST_table_rows_equal_visible_records", "MUST", info.rows === info.visible, { rows: info.rows, visible: info.visible });
  const transforms = new Set(rendered.map((m) => m.transform));
  check("INFO_group_markers_share_one_screen_position", "INFO", transforms.size === 1, { distinct_positions: transforms.size });

  // MUST: each record selectable from the table
  let viaTable = 0;
  for (const m of rendered) {
    const rows = page.locator("#tbl tr", { has: page.locator("td:first-child", { hasText: m.name || "Без названия" }) });
    const n = await rows.count();
    for (let k = 0; k < n; k++) {
      await rows.nth(k).click();
      if (await page.evaluate((id) => CITY_APP.state.selected && CITY_APP.state.selected.id === id, m.id)) { viaTable++; break; }
    }
  }
  check("MUST_each_group_record_selectable_from_table", "MUST", viaTable === fx.ids.length, { selectable: viaTable, of: fx.ids.length });

  // SHOULD: map click at the group position reaches every record (e.g. a chooser list); baseline: top marker only
  const reached = new Set();
  if (rendered.length) {
    const { cx, cy } = rendered[0];
    for (let k = 0; k < fx.ids.length; k++) {
      await page.mouse.click(cx, cy);
      const sel = await page.evaluate(() => CITY_APP.state.selected && CITY_APP.state.selected.id);
      if (sel) reached.add(sel);
      const chooser = await page.$("[data-coord-group-item]");  // proposal hook: list of records at one point
      if (chooser) {
        const items = await page.$$eval("[data-coord-group-item]", (els) => els.map((e) => e.getAttribute("data-coord-group-item")));
        items.forEach((i) => reached.add(i));
        break;
      }
    }
  }
  const reachedGroup = fx.ids.filter((i) => reached.has(i));
  check("SHOULD_each_group_record_selectable_from_map", "SHOULD", reachedGroup.length === fx.ids.length, { reachable_by_map_click: reachedGroup.length, of: fx.ids.length });

  // SHOULD: UI says that several records share one coordinate
  const indicated = await page.evaluate(() => {
    const attr = document.querySelector("[data-coord-group], [data-qa-group], [data-coord-group-item]");
    const txt = document.body.innerText;
    return { attr: !!attr, text: /в одной точке|одной координат|координата требует проверки|совпадающ\S* координат/i.test(txt) };
  });
  check("SHOULD_group_indicated_in_ui", "SHOULD", indicated.attr || indicated.text, indicated);

  check("MUST_no_page_errors", "MUST", errors.length === 0, { errors: errors.slice(0, 5) });
  await browser.close();
  const out = { target: appRoot ? { app_root_given: true } : { url: base }, fixture: fx.fixture, group_id: fx.group_id, results,
    must_failures: results.filter((r) => r.level === "MUST" && r.status === "FAIL").map((r) => r.check),
    should_failures: results.filter((r) => r.level === "SHOULD" && r.status === "FAIL").map((r) => r.check) };
  const jp = opt("--json");
  if (jp) fs.writeFileSync(jp, JSON.stringify(out, null, 1) + "\n");
  process.exit(out.must_failures.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
