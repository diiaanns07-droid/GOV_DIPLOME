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

  // ---- stage 2: districts, facts catalog, template explanation, stale reply ----
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.click('#citySeg button[data-city="shymkent"]');
  const dist = await page.evaluate(() => [...document.querySelectorAll("#tbl tr td:nth-child(3)")].map((t) => t.textContent));
  check("district column shows K03 names (ru / kk)", dist.length === 55 && dist.every((t) => /Әл-Фараби|Еңбекші|Аль-Фараби|Енбекши/.test(t)), dist.slice(0, 3).join(" | "));
  await page.click("#explainBody button");
  await page.waitForSelector("#explainBody .explain:not([hidden]) .who");
  const ex = await page.textContent("#explainBody .explain");
  check("template explanation is labelled and built from facts", ex.includes("шаблонное объяснение") && ex.includes("не LLM") && ex.includes("Школа: записей в квадрате: 15") && ex.includes("Мощность школ (места): нет данных"), ex.slice(0, 160));
  await page.screenshot({ path: path.join(out, "05_explanation.png") });
  // click "explain" and switch city in the same task: the pending reply must not appear for Astana
  await page.evaluate(() => { document.querySelector("#explainBody button").click(); CITY_APP.switchCity("astana"); });
  await page.waitForTimeout(100);
  const after = await page.evaluate(() => { const b = document.querySelector("#explainBody .explain"); return { hidden: b.hidden, text: b.textContent }; });
  check("stale explanation discarded after city switch", after.hidden && !after.text.includes("Шымкент") && !after.text.includes("15"), JSON.stringify(after));
  const catalogText = await page.textContent("#explainBody details");
  check("catalog after switch is Astana's own (scenario k10r3_g127, 65 records)", catalogText.includes("k10r3_g127") && catalogText.includes("65"), catalogText.slice(0, 120));
  await page.click("#provCard summary");
  const prov = await page.textContent("#provBody");
  check("source card shows SHA, K03 rule, K05 contract and K08 note", prov.includes("ea703f1ddd") && prov.includes("k03_assign_v1") && prov.includes("k05-obs-v1.1") && prov.includes("K08"), prov.slice(0, 100));

  // missing inputs: copy web/ without data.js, then without evidence.js
  const os = require("os");
  for (const missing of ["data.js", "evidence.js"]) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ce-"));
    for (const f of fs.readdirSync(path.join(__dirname, "..", "web"))) if (f !== missing) fs.copyFileSync(path.join(__dirname, "..", "web", f), path.join(dir, f));
    const p2 = await browser.newPage();
    const errs2 = []; p2.on("pageerror", (e) => errs2.push(String(e)));
    await p2.goto("file://" + path.join(dir, "index.html"));
    await p2.waitForTimeout(200);
    const txt = await p2.textContent("main");
    const ok = missing === "data.js" ? txt.includes("Данные не найдены") : (txt.includes("Каталог фактов недоступен") && (await p2.$$("#tbl tr")).length === 55);
    check(`clear state when ${missing} is missing`, ok && errs2.length === 0, txt.slice(0, 120) + " " + errs2.join(" "));
    if (missing === "data.js") await p2.screenshot({ path: path.join(out, "06_missing_data.png") });
    await p2.close(); fs.rmSync(dir, { recursive: true });
  }

  check("no console/page errors", errors.length === 0, errors.join(" | "));
  check("no network requests (file:// only)", requests.length === 0, requests.join(" "));
  await browser.close();
  fs.writeFileSync(path.join(out, "smoke_result.json"), JSON.stringify({ url: "web/index.html (file://)", results }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
