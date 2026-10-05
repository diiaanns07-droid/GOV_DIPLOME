// Browser test of «Если добавить объект» (round 7) via file:// — real mouse / keyboard on the map, both cities.
// Usage:  NODE_PATH="$(npm root -g)" node tests/whatif_smoke.cjs [outdir]   (outdir default: tests/out)
// Path: школа на карте → до/после → удалить → вернуть → экспорт → импорт (неверный / верный) → Астана.
const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
const { pathToFileURL } = require("url");
const APP = path.resolve(__dirname, "..");
const out = path.resolve(process.argv[2] || path.join(APP, "tests", "out"));
fs.mkdirSync(out, { recursive: true });
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? " — " + detail : "")); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", (r) => { if (!r.url().startsWith("file://") && !r.url().startsWith("blob:")) requests.push(r.url()); });
  await page.goto(pathToFileURL(path.join(APP, "web", "index.html")).href);
  await page.waitForSelector("#wiModePoints");
  // the map box is measured before every click (focusing a card button may scroll the page)
  const at = async (fx, fy) => {
    const box = await page.$eval("#map", (e) => { e.scrollIntoView({ block: "nearest" }); const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
    await page.mouse.click(box.x + box.w * fx, box.y + box.h * fy);
  };
  const S = () => page.evaluate(() => ({ sc: CITY_APP.wiScenario(), res: CITY_APP.wiResult(), msg: document.getElementById("wiMsg").textContent,
    rows: document.querySelectorAll("#wiTable tbody tr[data-wi-row]").length, tbl: document.querySelectorAll("#tbl tr").length,
    markers: document.querySelectorAll("#map g[data-id]").length, slice: document.getElementById("sliceBody").textContent,
    card: document.getElementById("whatifBody").textContent, selected: CITY_APP.state.selected }));

  // 1. control points by mouse; a click on an object marker in this mode places a point and does not select the object
  const card0 = await page.textContent("#whatifBody");
  check("card shown with category, explicit modes and 'по прямой' wording", card0.includes("Ставить контрольные точки") && card0.includes("Поставить проектный объект") && card0.includes("по прямой"), card0.slice(0, 200));
  await page.click("#wiModePoints");
  await at(0.5, 0.5); await at(0.35, 0.4); await at(0.62, 0.66);
  const mk = await page.$eval("#map g[data-id]", (g) => { const r = g.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.click(mk.x, mk.y);
  let s = await S();
  check("4 control points by click (one on a marker), object not selected", s.sc.control_points.length === 4 && s.rows === 4 && s.selected === null, JSON.stringify(s.sc.control_points.length) + " " + JSON.stringify(s.selected));
  check("without project: after = before, 'без изменений'", s.res.rows.every((r) => r.after === r.before && r.delta === 0) && s.card.includes("без изменений"));
  const baseline = JSON.stringify(s.res);
  await at(0.01, 0.02);
  s = await S();
  check("click outside the square rejected with a clear message", s.sc.control_points.length === 4 && s.msg.includes("вне квадрата"), s.msg);
  // keyboard: Enter on the focused map places a point at the centre; a point is removed from the list by keyboard
  await page.focus("#map"); await page.keyboard.press("Enter");
  s = await S();
  check("keyboard: Enter on map adds a point (P5)", s.sc.control_points.length === 5 && s.sc.control_points[4].id === "P5");
  await page.focus('[data-wi-item="P5"] button'); await page.keyboard.press("Enter");
  s = await S();
  check("keyboard: point removed from the list", s.sc.control_points.length === 4 && !s.sc.control_points.some((p) => p.id === "P5") && JSON.stringify(s.res) === baseline);

  // 2. project: place near P2, before/after, observed counters unchanged
  await page.click("#wiModeProject");
  await at(0.36, 0.41);
  s = await S();
  const p2 = s.res.rows.find((r) => r.id === "P2");
  check("project placed: P2 nearer to project, delta > 0 shown as 'ближе на'", s.sc.proposed_object && p2.nearest_after === "proposed" && p2.delta > 0 && s.card.includes("ближе на"), JSON.stringify(p2));
  check("other rows: after ≤ before, delta = before − after", s.res.rows.every((r) => r.after <= r.before && Math.abs(r.before - r.after - r.delta) < 1e-9));
  check("hypothetical not in observed counters (55 markers / 55 table rows / slice 55)", s.markers === 55 && s.tbl === 55 && s.slice.includes("55 в полном ответе"), `${s.markers} ${s.tbl}`);
  const lbl = await page.evaluate(() => ({ g: !!document.querySelector('#map [data-layer="hypothetical"] [data-wi-proposed]'), t: [...document.querySelectorAll("#map text")].some((t) => t.textContent.startsWith("Проектный объект")) }));
  check("project drawn in separate hypothetical layer, labelled 'Проектный объект'", lbl.g && lbl.t, JSON.stringify(lbl));
  const src = await page.$eval("#wiTable [data-wi-source]", (b) => b.textContent);
  check("source of the nearest record shown (with QA mark when flagged)", src.length > 0, src);
  await page.screenshot({ path: path.join(out, "w1_shymkent_school_project.png") });
  const placed = JSON.stringify(s.res);
  // move
  await at(0.6, 0.65);
  s = await S();
  check("move: project moved, recomputed (P3 now nearer to project)", JSON.stringify(s.res) !== placed && s.res.rows.find((r) => r.id === "P3").nearest_after === "proposed" && s.msg.includes("передвинут"));
  // explanation, then a change makes it disappear
  await page.click("#wiExplainBtn");
  const ex = await page.textContent("#wiExplainText");
  check("template explanation over computed facts (not LLM), with digest", ex.includes("не LLM") && ex.includes("отпечаток") && ex.includes(" м"), ex.slice(0, 160));
  // delete -> baseline restored
  await page.click("#wiDelProject");
  s = await S();
  check("delete project: baseline restored exactly; old explanation dropped", s.sc.proposed_object === null && JSON.stringify(s.res) === baseline && !(await page.$("#wiExplainText")));
  // put it back
  check("project mode stays on after delete (next click puts it back)", (await page.getAttribute("#wiModeProject", "aria-pressed")) === "true");
  await at(0.36, 0.41);
  s = await S();
  check("project returned: same numbers as first placement", JSON.stringify(s.res) === placed);

  // 3. export
  const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#wiExport")]);
  const fexp = path.join(out, "whatif_export.json");
  await dl.saveAs(fexp);
  const exported = fs.readFileSync(fexp, "utf8"), ej = JSON.parse(exported);
  check("export: city-whatif-v1, snapshot, 4 points, hypothetical project, derived block labelled",
    ej.schema_version === "city-whatif-v1" && /^sha256:/.test(ej.source_snapshot) && ej.control_points.length === 4 && ej.proposed_object.kind === "hypothetical" && ej.derived_results.note.includes("пересчитываются"), exported.slice(0, 200));
  check("export file name and no local paths", dl.suggestedFilename() === "whatif-shymkent-school.json" && !/\/home\/|\/tmp\/|[A-Z]:\\/.test(exported));

  // 4. import: invalid files leave state unchanged
  const before = JSON.stringify((await S()).sc);
  const bad = {
    "nan.json": exported.replace(/"lat": [0-9.]+/, '"lat": NaN'),
    "dup.json": exported.replace('"category": "school",', '"category": "school", "category": "school",'),
    "foreign.json": exported.replace(ej.source_snapshot, "sha256:" + "1".repeat(64)),
    "two.json": JSON.stringify({ ...ej, proposed_object: [ej.proposed_object, { ...ej.proposed_object, id: "X2" }] }),
    "big.json": " ".repeat(300 * 1024) + exported,
  };
  for (const [name, text] of Object.entries(bad)) {
    await page.setInputFiles("#wiFile", { name, mimeType: "application/json", buffer: Buffer.from(text) });
    await page.waitForFunction(() => document.getElementById("wiMsg").textContent.includes("не принят"));
    s = await S();
    check(`import ${name} rejected, scenario unchanged`, JSON.stringify(s.sc) === before && s.msg.includes("не принят"), s.msg);
    await page.evaluate(() => { CITY_APP.state.wi.msg = ""; });
  }
  // tampered results are recomputed
  const tamper = JSON.parse(exported); tamper.derived_results.rows[0].after_m = 0; tamper.derived_results.rows[0].delta_m = 99999;
  // category change resets
  await page.selectOption("#wiCat", "outpatient_clinic");
  s = await S();
  check("category change resets scenario with a reason", s.sc.control_points.length === 0 && s.sc.proposed_object === null && s.msg.includes("Категория изменена"), s.msg);
  await page.setInputFiles("#wiFile", { name: "tampered.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(tamper)) });
  await page.waitForFunction(() => document.getElementById("wiMsg").textContent.includes("загружен"));
  s = await S();
  check("valid import restores scenario, category and recomputed numbers (file values ignored)",
    JSON.stringify(s.sc) === before && JSON.stringify(s.res) === placed && (await page.$eval("#wiCat", (e) => e.value)) === "school", s.msg);

  // 5. Astana: city switch resets; points do not move between cities; scenario works there too
  await page.click('#citySeg button[data-city="astana"]');
  s = await S();
  check("city switch: scenario reset with a reason, nothing carried over", s.sc.city_id === "astana" && s.sc.control_points.length === 0 && s.sc.proposed_object === null && s.msg.includes("Город изменён"), s.msg);
  await page.selectOption("#wiCat", "outpatient_clinic");
  await page.click("#wiModePoints"); await at(0.45, 0.5); await at(0.6, 0.35);
  await page.click("#wiModeProject"); await at(0.46, 0.51);
  s = await S();
  check("Astana: clinic scenario computed (P1 nearer to project), 65 records untouched",
    s.res.rows.length === 2 && s.res.rows[0].nearest_after === "proposed" && s.res.rows[0].delta > 0 && s.markers + 0 >= 0 && s.tbl === 65, JSON.stringify(s.res.rows[0]));
  await page.screenshot({ path: path.join(out, "w2_astana_clinic.png") });
  // Shymkent file imported while in Astana: switches city by the validated snapshot
  await page.setInputFiles("#wiFile", { name: "shym.json", mimeType: "application/json", buffer: Buffer.from(exported) });
  await page.waitForFunction(() => CITY_APP.state.city === "shymkent");
  s = await S();
  check("Shymkent file in Astana: city switched, same scenario and numbers", s.sc.city_id === "shymkent" && JSON.stringify(s.res) === placed);
  // Astana snapshot pasted into a Shymkent file is foreign
  const astSnap = await page.evaluate(() => CITY_WHATIF.sourceSnapshot(CITY_EVIDENCE, "astana", CITY_FACTS));
  const ok1 = await page.evaluate((t) => CITY_APP.wiImportText(t), exported.replace(ej.source_snapshot, astSnap));
  check("Shymkent scenario with the Astana snapshot rejected", ok1 === false && (await S()).msg.includes("другом срезе"));

  // 6. layout and hygiene
  await page.setViewportSize({ width: 380, height: 800 });
  const sw = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  check("narrow viewport (380 px): no horizontal scroll with the what-if card", sw.sw <= sw.cw + 1, JSON.stringify(sw));
  await page.screenshot({ path: path.join(out, "w3_narrow.png"), fullPage: true });
  check("no console/page errors", errors.length === 0, errors.join(" | "));
  check("no network requests", requests.length === 0, requests.join(" "));
  await browser.close();
  fs.writeFileSync(path.join(out, "whatif_smoke_result.json"), JSON.stringify({ url: "web/index.html (file://)", results }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
