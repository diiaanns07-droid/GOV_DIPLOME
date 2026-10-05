// K10 round-6 acceptance, UI level (Playwright, Chromium). Adapter of round-5 ui_coord_group.cjs to the NEW build:
// the new build opens the other records of a co-located group via buttons in the selection card
// ("Проверка качества записи"), not via a [data-coord-group-item] hook. Criteria are unchanged.
// Usage:
//   NODE_PATH=$(npm root -g) node k10r6_ui.cjs --app-root <extracted prototypes/city-evidence> [--json out.json]
//   NODE_PATH=$(npm root -g) node k10r6_ui.cjs --url http://127.0.0.1:8765/ [--json out.json]
// Exit 1 if any MUST invariant fails. No EXPECTED_FAIL list is applied.
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const args = process.argv.slice(2);
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const appRoot = opt("--app-root"), base = opt("--url");
if (!!appRoot === !!base) { console.error("give exactly one of --app-root or --url"); process.exit(2); }
const fx = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "..", "round-5-results", "K10", "fixtures", "ui_coord_group_shymkent.json"), "utf8"));
const target = appRoot ? "file://" + path.resolve(appRoot, "web", "index.html") : (base.endsWith("/") ? base : base + "/");
const CLAIM = /ошибк|неверн|ошибочн|некоррект|неправильн/i;   // wording that would assert a proven coordinate error
const res = [];
const inv = (name, ok, detail) => { res.push({ invariant: name, level: "MUST", verdict: ok ? "PASS" : "FAIL", detail }); console.log(`${ok ? "PASS" : "FAIL"} ${name} ${JSON.stringify(detail)}`); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(target);
  await page.waitForSelector("#tbl tr");
  if (await page.evaluate(() => CITY_APP.state.city) !== fx.city) {
    await page.click(`#citySeg button[data-city="${fx.city}"]`);
    await page.waitForFunction((c) => CITY_APP.state.city === c, fx.city);
  }
  const names = await page.evaluate((ids) => Object.fromEntries(CITY_APP.visiblePlaces().filter((p) => ids.includes(p.id))
    .map((p) => [p.id, `${p.name || "Без названия"} · ${p.group_label}`])), fx.ids);

  // U1 group is visible on the map at the group position
  const vis = await page.evaluate((ids) => {
    const g = document.querySelector(`#map g[data-id="${ids[0]}"]`), r = g.getBoundingClientRect();
    const mx = r.x + r.width / 2, my = r.y + r.height / 2;
    const labels = [...document.querySelectorAll("#map text")].filter((t) => /в одной точке/.test(t.textContent))
      .map((t) => { const b = t.getBoundingClientRect(); return { text: t.textContent.replace(/\s+$/, ""), title: (t.querySelector("title") || {}).textContent || "", dx: b.x - mx, dy: b.y - my }; });
    const rings = [...document.querySelectorAll("#map circle[stroke-dasharray]")].map((c) => { const b = c.getBoundingClientRect(); return Math.hypot(b.x + b.width / 2 - mx, b.y + b.height / 2 - my); });
    return { mx, my, labels, ring_offsets_px: rings.map((d) => Math.round(d * 10) / 10) };
  }, fx.ids);
  const lab = vis.labels.find((l) => l.text.startsWith(`×${fx.ids.length} `) && Math.abs(l.dx) < 60 && Math.abs(l.dy) < 60);
  inv("U1_group_label_visible_at_group", !!lab && vis.ring_offsets_px.some((d) => d < 2),
      { label: lab ? lab.text : null, ring_within_2px: vis.ring_offsets_px.some((d) => d < 2) });

  // U2 every record of the group opens starting from the map (map click -> card buttons)
  const opened = new Set(), texts = [];
  await page.mouse.click(vis.mx, vis.my);
  const first = await page.evaluate(() => CITY_APP.state.selected && CITY_APP.state.selected.id);
  if (first) opened.add(first);
  for (const id of fx.ids) {
    if (opened.has(id)) continue;
    await page.mouse.click(vis.mx, vis.my);
    const btn = page.locator("#selBody li.warn button", { hasText: names[id] });
    if (await btn.count() !== 1) { texts.push({ id, button_matches: await btn.count() }); continue; }
    await btn.click();
    const sel = await page.evaluate(() => CITY_APP.state.selected && CITY_APP.state.selected.id);
    if (sel === id) opened.add(id);
  }
  inv("U2_each_group_record_opens_from_map", fx.ids.every((i) => opened.has(i)),
      { opened: fx.ids.filter((i) => opened.has(i)).length, of: fx.ids.length, first_by_map_click: first, problems: texts });

  // U3 every record opens from the table (round-5 MUST, repeated on the new build)
  let viaTable = 0;
  for (const id of fx.ids) {
    const nm = names[id].split(" · ")[0];
    const rows = page.locator("#tbl tr", { has: page.locator("td:first-child", { hasText: nm }) });
    for (let k = 0; k < await rows.count(); k++) {
      await rows.nth(k).click();
      if (await page.evaluate((x) => CITY_APP.state.selected && CITY_APP.state.selected.id === x, id)) { viaTable++; break; }
    }
  }
  inv("U3_each_group_record_opens_from_table", viaTable === fx.ids.length, { opened: viaTable, of: fx.ids.length });

  // U4 wording: flags a check, does not assert a proven coordinate error; U5 district vs coordinate doubt
  const cards = [];
  for (const id of fx.ids) {
    await page.evaluate((x) => CITY_APP.selectPlace(x), id);
    cards.push(await page.evaluate(() => {
      const b = document.getElementById("selBody");
      const dts = [...b.querySelectorAll("dt")], dd = dts.find((d) => d.textContent === "Район");
      const dist = dd ? dd.nextElementSibling : null;
      return { qa: [...b.querySelectorAll("li.warn")].map((l) => l.firstChild.textContent.trim()),
               note: [...b.querySelectorAll("p.muted")].map((p) => p.textContent).find((t) => /Метки не означают/.test(t)) || null,
               district_text: dist ? dist.firstChild.textContent : null,
               district_badge: dist && dist.querySelector(".badge") ? dist.querySelector(".badge").textContent : null };
    }));
  }
  const wording = [lab ? lab.text : "", lab ? lab.title : "", ...cards.flatMap((c) => c.qa.filter((t) => /координат/.test(t))), ...cards.map((c) => c.district_badge || "")];
  const claims = wording.filter((t) => CLAIM.test(t));
  const hedged = cards.every((c) => c.qa.some((t) => /координата совпадает/.test(t) && /не проверено/.test(t)) && c.note);
  inv("U4_wording_flags_check_not_proven_error", !claims.length && hedged && lab && /не проверено/.test(lab.title),
      { claims, every_card_hedged_and_noted: hedged, label_title: lab ? lab.title : null });

  // U5 geometric district result shown separately from the coordinate doubt
  const other = await page.evaluate((ids) => {
    const ev = (window.CITY_OBS && window.CITY_OBS.cities && window.CITY_OBS.cities[CITY_APP.state.city]) || {};
    const coloc = new Set(((ev.qa || {}).colocated || []).flatMap((g) => g.ids));
    const pd = ev.place_district || {};
    const p = CITY_APP.visiblePlaces().find((x) => !ids.includes(x.id) && !coloc.has(x.id) && pd[x.id] && pd[x.id].status === "matched");
    if (!p) return { id: null, badge: null };
    CITY_APP.selectPlace(p.id);
    const dd = [...document.querySelectorAll("#selBody dt")].find((d) => d.textContent === "Район").nextElementSibling;
    return { id: p.id, badge: dd.querySelector(".badge") ? dd.querySelector(".badge").textContent : null };
  }, fx.ids);
  const groupBadges = [...new Set(cards.map((c) => c.district_badge))];
  const groupNamed = cards.every((c) => c.district_text && !/не присвоен|не определён/.test(c.district_text));
  inv("U5_district_matched_shown_with_coordinate_doubt", groupNamed && groupBadges.length === 1 && /координата под вопросом/.test(groupBadges[0] || "")
      && other.badge && !/под вопросом/.test(other.badge),
      { group_district_texts: [...new Set(cards.map((c) => c.district_text))], group_badges: groupBadges, non_group_matched_badge: other.badge });

  inv("U6_no_page_errors", errors.length === 0, { errors: errors.slice(0, 5) });
  await browser.close();
  const out = { target: appRoot ? { mode: "app-root" } : { mode: "url", url: base }, fixture: fx.group_id, results: res,
    must_failures: res.filter((r) => r.verdict === "FAIL").map((r) => r.invariant) };
  const jp = opt("--json");
  if (jp) fs.writeFileSync(jp, JSON.stringify(out, null, 1) + "\n");
  process.exit(out.must_failures.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
