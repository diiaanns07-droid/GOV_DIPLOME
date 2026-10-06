// Browser test of «Устойчивость к допущениям» (round 9) via file:// — both cities, keyboard, cancel/stale, apply, files, 390 px.
// Usage:  NODE_PATH="$(npm root -g)" node tests/resilience_smoke.cjs [outdir]
const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
const { pathToFileURL } = require("url");
const APP = path.resolve(__dirname, "..");
const out = path.resolve(process.argv[2] || path.join(APP, "tests", "out"));
fs.mkdirSync(out, { recursive: true });
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? " — " + String(detail).slice(0, 300) : "")); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", (r) => { if (!/^(file|blob|data):/.test(r.url())) requests.push(r.url()); });
  await page.goto(pathToFileURL(path.join(APP, "web", "index.html")).href);
  const S = () => page.evaluate(() => ({ rs: { status: CITY_RESILIENCE_UI.state.status, cases: CITY_RESILIENCE_UI.state.cases.map((c) => ({ id: c.id, label: c.label, n: c.ids.size })),
    msg: (document.getElementById("rsMsg") || {}).textContent || "", result: CITY_RESILIENCE_UI.state.result }, selected: CITY_PLAN_UI.state.selected.slice(), city: CITY_APP.state.city,
    tbl: document.querySelectorAll("#tbl tr").length, places: CITY_EVIDENCE.cities[CITY_APP.state.city].places.length }));
  const active = () => page.evaluate(() => (document.activeElement || {}).id || document.activeElement.tagName);

  check("resilience card hidden in v1 mode", await page.evaluate(() => document.getElementById("resCard").hidden));
  await page.click('#toolSeg button[data-tool="v2"]');
  check("v2 mode: card shown with the 'не подтверждение закрытия' notice", (await page.textContent("#rsNotice")).includes("не подтверждение закрытия"));
  await page.click("#plDemo");
  const placesBefore = (await S()).places;

  // ---- cases by keyboard: add, label, records ----
  await page.focus("#rsAdd"); await page.keyboard.press("Enter"); await page.waitForTimeout(60);
  check("keyboard: «Добавить случай» → focus on the new case label", (await active()) === "rsLabel_c1", await active());
  await page.keyboard.press("Control+A"); await page.keyboard.type("Без трёх школ"); await page.keyboard.press("Tab"); await page.waitForTimeout(60);
  check("label typed by keyboard and applied; focus moved on", (await S()).rs.cases[0].label === "Без трёх школ" && (await active()) !== "BODY", await active());
  const recs = await page.evaluate(() => CITY_RESILIENCE_UI.sources().map((p) => ({ id: p.id, name: p.name })));
  check("records list shows real source IDs, names, source and QA", recs.length === 15 && (await page.textContent("#rsCase_c1")).includes(recs[0].id) && (await page.textContent("#rsCase_c1")).includes("QA:"));
  for (const k of [0, 1, 2]) { await page.focus(`#rsX_c1_${k}`); await page.keyboard.press("Space"); }
  check("3 records excluded with Space; focus kept on the checkbox", (await S()).rs.cases[0].n === 3 && (await active()) === "rsX_c1_2", await active());
  check("source data unchanged (records count, table rows)", (await S()).places === placesBefore && (await S()).tbl === 55);
  await page.click("#rsAdd"); await page.waitForTimeout(60);
  for (let k = 0; k < 15; k += 2) await page.check(`#rsX_c2_${k}`);
  await page.click("#rsAdd"); await page.waitForTimeout(60);
  for (const k of [0, 1, 2]) await page.check(`#rsX_c3_${k}`);
  check("duplicate exclusion sets shown as such", (await page.textContent("#rsDup")).includes("c1 = c3"));
  await page.focus("#rsDel_c3"); await page.keyboard.press("Enter"); await page.waitForTimeout(60);
  check("delete case by keyboard: removed, focus kept in the card", (await S()).rs.cases.length === 2 && /^rsDel_c2$|^rsAdd$/.test(await active()), await active());

  // ---- run, compare, apply only by button ----
  const manual0 = (await S()).selected;
  await page.focus("#rsRun"); await page.keyboard.press("Enter");
  await page.waitForFunction(() => CITY_RESILIENCE_UI.state.status !== "running");
  let s = await S();
  check("comparison done: three plan cards + per-case table (3 rows)", s.rs.status === "done" && (await page.$$("#rsCompare [data-rs-plan]")).length === 3 && (await page.$$("#rsTable tbody tr")).length === 3);
  const ref = await page.evaluate(() => { const e = CITY_RESILIENCE.validateResilience(CITY_RESILIENCE_UI.envelope(), CITY_PLAN_UI.ctxOf(CITY_APP.state.city));
    return CITY_RESILIENCE.optimizeResilience(CITY_PLAN_UI.ctxOf(CITY_APP.state.city), e, { F: CITY_FACTS }); });
  check("UI result = direct optimizeResilience (nominal, robust, price, digest)", JSON.stringify(s.rs.result.robust.selected_ids) === JSON.stringify(ref.robust.selected_ids)
    && JSON.stringify(s.rs.result.nominal.selected_ids) === JSON.stringify(ref.nominal.selected_ids) && s.rs.result.price_of_robustness_m === ref.price_of_robustness_m && s.rs.result.resilience_problem_digest === ref.resilience_problem_digest);
  check("price of robustness shown (or reason)", /Цена устойчивости/.test(await page.textContent("#rsPrice")));
  check("worst cases marked ▲ in the table", (await page.$$("#rsTable td.rs-worst")).length >= 2);
  check("search does not change the manual plan", JSON.stringify(s.selected) === JSON.stringify(manual0));
  await page.focus("#rsApply_robust"); await page.keyboard.press("Enter"); await page.waitForTimeout(60);
  s = await S();
  check("apply robust by keyboard: manual := robust, result still valid", JSON.stringify(s.selected) === JSON.stringify(ref.robust.selected_ids) && s.rs.status === "done");
  await page.click("#rsRestore"); await page.waitForTimeout(60);
  check("restore manual plan", JSON.stringify((await S()).selected) === JSON.stringify(manual0));
  await page.screenshot({ path: path.join(out, "r1_shymkent_resilience.png"), fullPage: true });

  // ---- explanation, export, report ----
  await page.click("#rsExplain");
  const ex = await page.textContent("#rsExplainText");
  check("explanation: template, conditional exclusions, no probabilities", ex.includes("не LLM") && ex.includes("не подтверждение закрытия") && !/%|вероятност[ьи] \d/.test(ex));
  const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#rsExport")]);
  const fexp = path.join(out, "city_resilience_export.json"); await dl.saveAs(fexp);
  const exported = fs.readFileSync(fexp, "utf8"), ej = JSON.parse(exported);
  check("export: city-resilience-v1, input only (plan + 2 cases), plan snapshot kept", ej.schema_version === "city-resilience-v1" && Object.keys(ej).join() === "schema_version,plan,cases"
    && ej.cases.length === 2 && !("derived_results" in ej.plan) && ej.plan.source_snapshot === (await page.evaluate(() => CITY_PLAN_UI.ctxOf("shymkent").source_snapshot)));
  const [dr] = await Promise.all([page.waitForEvent("download"), page.click("#rsReport")]);
  const frep = path.join(out, "city_resilience_report.html"); await dr.saveAs(frep);
  const rep = fs.readFileSync(frep, "utf8");
  check("HTML report: no scripts, exclusions + provenance + versions + limits", !/<script/i.test(rep) && rep.includes("worst-lex-v1") && rep.includes("exclusions_digest") && rep.includes("Без трёх школ") && rep.includes(recs[0].id) && rep.includes("не подтверждение закрытия"));

  // ---- stale and cancel ----
  await page.evaluate(() => { CITY_RESILIENCE_UI.start(); CITY_RESILIENCE_UI.cancel(); });
  await page.waitForTimeout(150);
  s = await S();
  check("cancel: status cancelled, no result shown later", s.rs.status === "cancelled" && !s.rs.result && !(await page.$("#rsCompare [data-rs-plan='robust']")));
  await page.evaluate(() => { CITY_RESILIENCE_UI.start(); CITY_RESILIENCE_UI.toggleRecord("c1", CITY_RESILIENCE_UI.sources()[5].id, true); });
  await page.waitForTimeout(300);
  s = await S();
  check("editing a case during the search: answer discarded (stale)", s.rs.status === "stale" && !s.rs.result, s.rs.status);
  await page.click("#rsRun"); await page.waitForFunction(() => CITY_RESILIENCE_UI.state.status !== "running");
  await page.fill("#plBudget", "500"); await page.press("#plBudget", "Tab"); await page.waitForTimeout(150);
  check("changing the v2 budget invalidates the comparison", (await S()).rs.status === "stale" && !(await page.$("#rsApply_robust")));

  // ---- invalid imports leave everything unchanged ----
  const before = await page.evaluate(() => JSON.stringify(CITY_RESILIENCE_UI.envelope()));
  const bad = { "nan.json": exported.replace(/"budget": \d+/, '"budget": NaN'), "dup.json": exported.replace('"cases"', '"cases": [], "cases"'),
    "forged.json": JSON.stringify({ ...ej, robust: { selected_ids: ["K1"] } }), "foreign.json": exported.replace(ej.plan.source_snapshot, "sha256:" + "c".repeat(64)),
    "candidate_as_source.json": JSON.stringify({ ...ej, cases: [{ id: "x", label: "x", disabled_source_ids: ["K1"] }] }), "base_id.json": JSON.stringify({ ...ej, cases: [{ ...ej.cases[0], id: "base" }] }),
    "v2.json": await page.evaluate(() => CITY_PLAN_UI.exportText()), "big.json": " ".repeat(270000) + exported };
  for (const [name, text] of Object.entries(bad)) {
    await page.evaluate(() => { CITY_RESILIENCE_UI.state.msg = ""; });
    await page.setInputFiles("#rsFile", { name, mimeType: "application/json", buffer: Buffer.from(text) });
    await page.waitForFunction(() => (document.getElementById("rsMsg").textContent || "").includes("не принят"));
    check(`import ${name} rejected, state unchanged`, (await page.evaluate(() => JSON.stringify(CITY_RESILIENCE_UI.envelope()))) === before, await page.textContent("#rsMsg"));
  }
  check("v2 file in the resilience import → hint to open it in v2 mode", (await page.textContent("#rsMsg")).length > 0);

  // ---- city switch resets; import of the Shymkent file from Astana restores everything ----
  await page.click('#citySeg button[data-city="astana"]'); await page.waitForTimeout(60);
  s = await S();
  check("city switch: cases reset with a reason, no IDs carried over", s.rs.cases.length === 0 && s.rs.msg.includes("Город изменён"), s.rs.msg);
  await page.click("#plDemo"); await page.click("#rsAdd"); await page.waitForTimeout(60);
  for (const k of [0, 3, 6]) await page.check(`#rsX_c1_${k}`);
  await page.click("#rsRun"); await page.waitForFunction(() => CITY_RESILIENCE_UI.state.status !== "running");
  s = await S();
  check("Astana: comparison computed on the Astana slice (65 records untouched)", s.rs.status === "done" && s.rs.result.status === "optimal" && s.tbl === 65);
  await page.screenshot({ path: path.join(out, "r2_astana_resilience.png"), fullPage: false });
  await page.setInputFiles("#rsFile", { name: "shym.json", mimeType: "application/json", buffer: Buffer.from(exported) });
  await page.waitForFunction(() => CITY_APP.state.city === "shymkent" && CITY_RESILIENCE_UI.state.cases.length === 2);
  check("import round trip: city switched back, plan and cases equal the export", (await page.evaluate(() => CITY_RESILIENCE_UI.exportText())) === exported);
  await page.selectOption("#plCat", "outpatient_clinic"); await page.waitForTimeout(60);
  check("category change: cases reset (record IDs belong to another category)", (await S()).rs.cases.length === 0);

  // ---- limit: >12 candidates is shown, nothing dropped ----
  await page.selectOption("#plCat", "school"); await page.click("#plDemo");
  await page.evaluate(() => { const U = CITY_PLAN_UI, b = CITY_EVIDENCE.cities.shymkent.bbox; U.setMode("cands"); for (let k = 0; k < 5; k++) U.place([b[0] + (b[2] - b[0]) * (0.1 + 0.15 * k), (b[1] + b[3]) / 2]); U.setMode("cands"); });
  await page.waitForTimeout(80);
  check("13 candidates: limit notice, run disabled, candidates kept", (await page.textContent("#rsLimit")).includes("до 12") && (await page.evaluate(() => CITY_PLAN_UI.state.cands.length)) === 13
    && (await page.evaluate(() => document.getElementById("rsRun").disabled)));

  // ---- v1 still works in its own mode ----
  await page.click('#toolSeg button[data-tool="v1"]');
  check("v1 mode intact: resilience card hidden, v1 card shown", await page.evaluate(() => document.getElementById("resCard").hidden && !document.getElementById("whatifCard").hidden));
  await page.click('#toolSeg button[data-tool="v2"]');

  // ---- 390 px ----
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(100);
  const ov = await page.evaluate(() => { const c = document.getElementById("resCard"); return { doc: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1, card: c.scrollWidth <= c.clientWidth + 1, sw: c.scrollWidth, cw: c.clientWidth }; });
  check("390 px: no page or card horizontal overflow", ov.doc && ov.card, JSON.stringify(ov));
  await page.screenshot({ path: path.join(out, "r3_390.png"), fullPage: false });
  check("no console/page errors", errors.length === 0, errors.join(" | "));
  check("no network requests", requests.length === 0, requests.join(" "));
  await browser.close();
  fs.writeFileSync(path.join(out, "resilience_smoke_result.json"), JSON.stringify({ url: "web/index.html (file://)", results }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
