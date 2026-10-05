// Headless browser smoke test of web/index.html via file:// (Playwright + Chromium).
// Usage:  NODE_PATH="$(npm root -g)" node tests/smoke.cjs [outdir]      (outdir default: research/round-5-results/BUILD/smoke)
// The page URL is built with url.pathToFileURL (works for Windows paths too — not run on Windows here).
const { chromium } = require("playwright");
const path = require("path"), fs = require("fs"), os = require("os");
const { pathToFileURL } = require("url");
const APP = path.resolve(__dirname, "..");
const out = path.resolve(process.argv[2] || path.join(APP, "..", "..", "research", "round-5-results", "BUILD", "smoke"));
fs.mkdirSync(out, { recursive: true });
const pageUrl = (dir) => pathToFileURL(path.join(dir, "index.html")).href;
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? " — " + detail : "")); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", (r) => { if (!r.url().startsWith("file://")) requests.push(r.url()); });
  await page.goto(pageUrl(path.join(APP, "web")));
  await page.waitForSelector("#tbl tr");

  // ---- both cities ----
  const s1 = await page.evaluate(() => ({ city: CITY_APP.state.city, rows: document.querySelectorAll("#tbl tr").length, markers: document.querySelectorAll("#map g[data-id]").length,
    slice: document.getElementById("sliceBody").textContent }));
  check("Shymkent: 55 records, slice says 'complete query result' and city total unknown",
    s1.city === "shymkent" && s1.rows === 55 && s1.markers === 55 && s1.slice.includes("55 в полном ответе запроса") && s1.slice.includes("Объектов по всему городу") && s1.slice.includes("нет данных"), JSON.stringify(s1).slice(0, 300));
  await page.screenshot({ path: path.join(out, "01_shymkent.png") });

  // ---- QA: colocated group of 10, labelled not removed ----
  const qa = await page.evaluate(() => ({ ring: [...document.querySelectorAll("#map text")].some((t) => t.textContent.startsWith("10 зап. в одной точке")),
    flagged: [...document.querySelectorAll("#tbl tr")].filter((r) => r.textContent.startsWith("⚠")).length }));
  check("Shymkent colocated group of 10 drawn on the map; flagged rows in table", qa.ring && qa.flagged >= 14, JSON.stringify(qa));
  const colocId = await page.evaluate(() => CITY_OBS.cities.shymkent.qa.colocated.find((g) => g.ids.length === 10).ids[0]);
  await page.evaluate((id) => CITY_APP.selectPlace(id), colocId);
  const card = await page.textContent("#selBody");
  const others = await page.$$eval("#selBody ul ul button", (b) => b.length);
  check("object card lists the 9 other records at the same coordinate, marks district as uncertain",
    card.includes("координата совпадает ещё с 9 записями") && others === 9 && card.includes("по координате под вопросом"), card.slice(0, 200));
  await page.screenshot({ path: path.join(out, "02_colocated_card.png") });
  const doubtId = await page.evaluate(() => Object.keys(CITY_OBS.cities.shymkent.qa.category_doubt)[0]);
  await page.evaluate((id) => CITY_APP.selectPlace(id), doubtId);
  const doubt = await page.textContent("#selBody");
  check("category doubt shown with rule and reason, record kept", doubt.includes("сомнение в категории") && doubt.includes("правило") && doubt.includes("не удаляются"));

  // ---- K07 P1/P2: clear point and selection (button, Escape) ----
  await page.click("#pointBtn");
  await page.mouse.click(300, 500);
  const pt = await page.evaluate(() => ({ sel: CITY_APP.state.selected, status: document.getElementById("mapStatus").textContent, dis: document.getElementById("clearBtn").disabled }));
  check("point selected; status line next to map; clear enabled", pt.sel && pt.sel.type === "point" && pt.status.includes("по прямой") && !pt.dis, JSON.stringify(pt));
  await page.keyboard.press("Escape");
  const cl = await page.evaluate(() => ({ sel: CITY_APP.state.selected, point: CITY_APP.state.point, dis: document.getElementById("clearBtn").disabled, card: document.getElementById("selBody").textContent }));
  check("Escape clears point, card and disables the clear button", cl.sel === null && cl.point === null && cl.dis && cl.card === "", JSON.stringify(cl));
  await page.click("#pointBtn");

  // ---- K07 CS2: tooltip must not survive a keyboard city switch ----
  const firstMarker = await page.$("#map g[data-id]");
  await firstMarker.hover();
  const tipBefore = await page.evaluate(() => getComputedStyle(document.getElementById("tip")).display);
  await page.focus('#citySeg button[data-city="astana"]');
  await page.keyboard.press("Enter");
  const s2 = await page.evaluate((old) => ({ city: CITY_APP.state.city, sel: CITY_APP.state.selected, rows: document.querySelectorAll("#tbl tr").length,
    hasOld: !!document.querySelector(`#map g[data-id="${old}"]`), tip: getComputedStyle(document.getElementById("tip")).display,
    slice: document.getElementById("sliceBody").textContent }), colocId);
  check("Astana after keyboard switch: own 65 records, no Shymkent markers, tooltip hidden",
    tipBefore === "block" && s2.city === "astana" && s2.sel === null && s2.rows === 65 && !s2.hasOld && s2.tip === "none" && s2.slice.includes("65 в полном ответе запроса"), JSON.stringify({ ...s2, slice: undefined, tipBefore }));
  check("Astana has no colocated groups (QA says 0)", s2.slice.includes("групп с совпадающими координатами (≥3 записей): 0"));
  await page.screenshot({ path: path.join(out, "03_astana.png") });

  // ---- filters, empty state, F2 ----
  await page.evaluate(() => document.querySelectorAll("#groupFilters input").forEach((cb) => { if (cb.dataset.group !== "school") cb.click(); }));
  const schools = await page.evaluate(() => document.querySelectorAll("#tbl tr").length);
  check("category filter (Astana: 8 school records)", schools === 8, String(schools));
  await page.evaluate(() => document.querySelector('#groupFilters input[data-group="school"]').click());
  const empty = await page.evaluate(() => ({ msg: document.getElementById("mapMsg").textContent, hidden: document.getElementById("mapMsg").hidden }));
  check("empty state is explicit", !empty.hidden && empty.msg.includes("Не выбрана ни одна категория"), empty.msg);
  await page.evaluate(() => document.querySelectorAll("#groupFilters input").forEach((cb) => cb.click()));
  await page.selectOption("#roadStyle", "foot");
  await page.evaluate(() => { const h = document.querySelector('#map path[role="button"]'); h.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  const seg = await page.textContent("#selBody");
  check("road card: foot access status, dataset, no walking minutes", seg.includes("Проход пешком") && seg.includes("Источник") && !/\bмин\b/.test(seg), seg.slice(0, 120));
  await page.click("#tRoads");
  check("hiding roads deselects the road (K07 F2)", await page.evaluate(() => CITY_APP.state.selected === null && document.getElementById("selBody").textContent === ""));
  await page.click("#tRoads");

  // ---- explanation: template label, units, reasons; stale after catalog update ----
  await page.click("#explainBody button");
  await page.waitForSelector("#explainBody .explain:not([hidden]) .who");
  const ex = await page.textContent("#explainBody .explain");
  check("template explanation labelled; units and missing reasons visible",
    ex.includes("шаблонное объяснение") && ex.includes("не LLM") && ex.includes("Школа в квадрате: 8 записей") && ex.includes("Мощность школ: нет данных (неизвестно, нет в источнике)"), ex.slice(0, 200));
  await page.screenshot({ path: path.join(out, "04_explanation.png") });
  // same city & filter: the catalog is updated between request and reply -> the old answer must be rejected
  await page.evaluate(() => {
    document.querySelector("#explainBody button").click();
    const o = CITY_OBS.cities.astana.observations.find((x) => x.indicator_id === "overture_place_records.school.conf_ge_0_0");
    o.value += 1;
  });
  await page.waitForTimeout(100);
  const stale = await page.textContent("#explainBody .explain");
  check("old answer rejected after catalog update in the same city (stale_catalog)", stale.includes("stale_catalog"), stale.slice(0, 160));
  await page.evaluate(() => { CITY_OBS.cities.astana.observations.find((x) => x.indicator_id === "overture_place_records.school.conf_ge_0_0").value -= 1; });
  await page.evaluate(() => { document.querySelector("#explainBody button").click(); CITY_APP.switchCity("shymkent"); });
  await page.waitForTimeout(100);
  const afterSwitch = await page.evaluate(() => document.querySelector("#explainBody .explain").hidden);
  check("pending answer discarded after city switch", afterSwitch === true);

  // ---- sources & licenses ----
  await page.click("#provCard summary");
  const prov = await page.textContent("#provBody");
  const links = await page.$$eval("#provBody a, #attrib a", (a) => a.map((x) => x.getAttribute("href")));
  const linkOk = links.every((h) => fs.existsSync(path.join(APP, "web", h)));
  check("source card: contract, K03 v2, K08 gap; license links resolve to committed files",
    prov.includes("k05-obs-v1.2+k12r4") && prov.includes("k03_assign_v2") && prov.includes("F5") && prov.includes("meta") && links.length >= 5 && linkOk, JSON.stringify(links));
  const attrib = await page.textContent("#attrib");
  check("map attribution names record providers (not only OSM)", attrib.includes("Meta") && attrib.includes("OpenStreetMap"), attrib);

  // ---- keyboard on map (K07 K5) and narrow viewport ----
  await page.focus("#map");
  const v0 = await page.evaluate(() => CITY_APP.state.view.cx);
  await page.keyboard.press("ArrowRight");
  check("focused map pans with arrow keys", await page.evaluate((v) => CITY_APP.state.view.cx !== v, v0));
  await page.setViewportSize({ width: 380, height: 800 });
  await page.waitForTimeout(150);
  const sw = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  check("narrow viewport (380 px) has no horizontal scroll", sw.sw <= sw.cw + 1, JSON.stringify(sw));
  await page.screenshot({ path: path.join(out, "05_narrow.png") });

  // ---- missing inputs ----
  for (const missing of ["data.js", "evidence.js"]) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ce-"));
    fs.cpSync(path.join(APP, "web"), dir, { recursive: true });
    fs.rmSync(path.join(dir, missing));
    const p2 = await browser.newPage();
    const errs2 = []; p2.on("pageerror", (e) => errs2.push(String(e)));
    await p2.goto(pageUrl(dir));
    await p2.waitForTimeout(200);
    const txt = await p2.textContent("main");
    const ok = missing === "data.js" ? txt.includes("Данные не найдены") : (txt.includes("Каталог фактов недоступен") && (await p2.$$("#tbl tr")).length === 55);
    check(`clear state when ${missing} is missing`, ok && errs2.length === 0, txt.slice(0, 120) + " " + errs2.join(" "));
    await p2.close(); fs.rmSync(dir, { recursive: true });
  }

  check("no console/page errors", errors.length === 0, errors.join(" | "));
  check("no network requests (file:// only)", requests.length === 0, requests.join(" "));
  await browser.close();
  fs.writeFileSync(path.join(out, "smoke_result.json"), JSON.stringify({ url: "web/index.html (file://, pathToFileURL)", results }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
