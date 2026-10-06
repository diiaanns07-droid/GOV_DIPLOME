// K10 round 9: import the K10 city-resilience-v1 demo envelopes through the REAL resilience panel of a BUILD (file:// page,
// hidden #rsFile input = the «Загрузить» button), run «Сравнить три плана», and compare what the page computed and shows
// with the expectations of the independent K10 oracle. Invalid files must be refused with the state unchanged.
// Usage: NODE_PATH="$(npm root -g)" node tests/ui_import.cjs <app-root> [out.json]
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), os = require("os"), path = require("path");
const { pathToFileURL } = require("url");
const [appRoot, outFile] = process.argv.slice(2);
const K10 = path.resolve(__dirname, "..");
const J = JSON.stringify;
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : String(detail).slice(0, 300) }); };
const near = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a)));

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", (r) => { if (!/^(file|blob|data):/.test(r.url())) requests.push(r.url()); });
  await page.goto(pathToFileURL(path.join(path.resolve(appRoot), "web", "index.html")).href);
  await page.click('#toolSeg button[data-tool="v2"]');
  const state = () => page.evaluate(() => ({
    city: CITY_APP.state.city, category: CITY_PLAN_UI.state.category, selected: CITY_PLAN_UI.state.selected.slice(),
    status: CITY_RESILIENCE_UI.state.status, msg: (document.getElementById("rsMsg") || {}).textContent || "",
    cases: CITY_RESILIENCE_UI.state.cases.map((c) => ({ id: c.id, label: c.label, ids: [...c.ids].sort() })),
    places: Object.fromEntries(Object.entries(CITY_EVIDENCE.cities).map(([k, v]) => [k, v.places.length])) }));
  const importFile = async (f) => {  // marks the message, then waits until the panel replaced it (accepted or refused)
    await page.evaluate(() => { CITY_RESILIENCE_UI.state.msg = "__k10_wait__"; });
    await page.setInputFiles("#rsFile", f);
    await page.waitForFunction(() => CITY_RESILIENCE_UI.state.msg !== "__k10_wait__", null, { timeout: 10000 });
    await page.waitForTimeout(30);
    return state();
  };
  const placesAtStart = (await state()).places;

  // ---- 1. every real demo envelope: import, run, compare with the K10 oracle ----
  const idx = JSON.parse(fs.readFileSync(path.join(K10, "envelopes", "INDEX.json"), "utf8"));
  for (const e of idx.packs.filter((p) => p.kind === "real_slice" && p.status === "optimal")) {
    const pack = JSON.parse(fs.readFileSync(path.join(K10, "envelopes", e.pack_id + ".json"), "utf8"));
    const want = pack.expected.optimize, env = pack.envelope;
    const s = await importFile(path.join(K10, "envelopes", "inputs", e.pack_id + ".json"));
    const casesOk = J(s.cases) === J(env.cases.map((c) => ({ id: c.id, label: c.label, ids: c.disabled_source_ids.slice().sort() })));
    check(`${e.pack_id}: imported (city, category, cases, manual plan)`, /загружен/.test(s.msg) && s.city === pack.city_id && s.category === pack.category && casesOk
      && J(s.selected.slice().sort()) === J(env.plan.selected_ids.slice().sort()), s.msg);
    await page.click("#rsRun");
    await page.waitForFunction(() => CITY_RESILIENCE_UI.state.status !== "running", null, { timeout: 60000 });
    const r = await page.evaluate(() => CITY_RESILIENCE_UI.state.result);
    const plan = (p) => p && [p.selected_ids, [p.worst_vector.unknown_count, p.worst_vector.weighted_sum_mm, p.worst_vector.max_mm], p.worst_case_ids];
    const exp = (p) => p && [p.selected_ids, p.worst_vector, p.worst_case_ids];
    check(`${e.pack_id}: UI result = K10 oracle (nominal, robust, worst vectors, worst cases, price, feasible count)`,
      r && r.status === want.status && J(plan(r.nominal)) === J(exp(want.nominal)) && J(plan(r.robust)) === J(exp(want.robust))
      && near(r.price_of_robustness_m, want.price_of_robustness_m) && r.same_plan === want.plans_identical && r.feasible_count === want.feasible_count,
      `${J(r && plan(r.robust))} vs ${J(exp(want.robust))}`);
    // what the page shows
    const shown = await page.evaluate(() => ({ price: (document.getElementById("rsPrice") || {}).textContent || "", same: !!document.getElementById("rsSame"),
      cards: document.querySelectorAll("#rsCompare [data-rs-plan]").length, rows: document.querySelectorAll("#rsTable tbody tr").length,
      worst: document.querySelectorAll("#rsTable td.rs-worst").length, notice: (document.getElementById("rsNotice") || {}).textContent || "" }));
    const nWorst = [want.manual, want.nominal, want.robust].reduce((t, p) => t + p.worst_case_ids.length, 0);
    const priceText = (want.price_of_robustness_m >= 0 ? "+" : "") + want.price_of_robustness_m.toFixed(1).replace(".", ",") + " м";
    check(`${e.pack_id}: page shows 3 plans, ${want.case_ids.length} case rows, ${nWorst} worst marks, price ${priceText}, same-plan note ${want.plans_identical}`,
      shown.cards === 3 && shown.rows === want.case_ids.length && shown.worst === nWorst && shown.price.includes(priceText) && shown.same === want.plans_identical
      && shown.notice.includes("не подтверждение закрытия"), J(shown));
  }
  const afterValid = await state();
  check("source records unchanged after all imports and runs", J(afterValid.places) === J(placesAtStart), J(afterValid.places));

  // ---- 2. files that must be refused (state unchanged) or accepted ----
  for (const pk of ["shymkent-school-invalid-envelopes", "astana-school-invalid-envelopes"]) {
    const pack = JSON.parse(fs.readFileSync(path.join(K10, "envelopes", pk + ".json"), "utf8"));
    await importFile(path.join(K10, "envelopes", "inputs", pack.pack_id.replace("-invalid-envelopes", "-relied") + ".json"));
    for (const c of pack.invalid_cases) {
      let f = path.join(K10, "envelopes", "inputs", "invalid", pk, c.case_id + ".json");
      if (c.pad_to_bytes) { f = path.join(os.tmpdir(), `k10_${c.case_id}.json`); fs.writeFileSync(f, c.raw + " ".repeat(c.pad_to_bytes - Buffer.byteLength(c.raw, "utf8"))); }
      const before = await state();
      const s = await importFile(f);
      if (c.expected.rejected) {
        check(`${pk}/${c.case_id}: refused, state unchanged`, /не принят/.test(s.msg) && J(s.cases) === J(before.cases) && J(s.selected) === J(before.selected) && s.city === before.city, s.msg);
      } else {
        const html = await page.evaluate(() => ({ imgs: document.querySelectorAll("#resBody img").length, text: document.getElementById("resBody").textContent }));
        check(`${pk}/${c.case_id}: accepted and shown as text`, /загружен/.test(s.msg) && html.imgs === 0, `${s.msg} ${J(html.imgs)}`);
        if (c.case_id === "label_html") check(`${pk}/label_html: label rendered literally, no element injected`, html.text.includes("<img src=x onerror=alert(1)>") && html.imgs === 0);
        await importFile(path.join(K10, "envelopes", "inputs", pack.pack_id.replace("-invalid-envelopes", "-relied") + ".json"));  // back to a known state
      }
    }
  }
  check("no page errors", errors.length === 0, errors.join(" | "));
  check("no network requests outside file:/blob:/data:", requests.length === 0, requests.join(" "));
  await browser.close();
  const out = { app_root: path.resolve(appRoot), checks: results.length, passed: results.filter((x) => x.ok).length,
    failed: results.filter((x) => !x.ok).map((x) => x.name), results };
  if (outFile) fs.writeFileSync(outFile, J(out, null, 1) + "\n");
  console.log(J({ checks: out.checks, passed: out.passed, failed: out.failed }));
  process.exit(out.failed.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
