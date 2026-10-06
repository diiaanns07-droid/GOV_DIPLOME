// K01 round 9: browser (file://) atomicity of the REAL plan import UI. Refused imports must not change the plan or the city.
//   NODE_PATH=$(npm root -g) node browser_atomic.cjs --app-root APP
const fs = require("fs"), path = require("path"), { pathToFileURL } = require("url");
const { chromium } = require("playwright");
const APP = process.argv[process.argv.indexOf("--app-root") + 1];
const R8 = path.join(__dirname, "..", "..", "round-8-results", "K01", "fixtures");
const rd = (n) => fs.readFileSync(path.join(R8, n)).toString("utf8");   // like File.text(): replacement decoding
(async () => {
  const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  const page = await browser.newPage(); const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(pathToFileURL(path.join(path.resolve(APP), "web", "index.html")).href);
  await page.waitForFunction(() => window.CITY_PLAN_UI && window.CITY_APP);
  let pass = 0, fail = 0;
  const check = (n, ok, d) => { ok ? pass++ : fail++; console.log(ok ? "PASS" : "FAIL", n, ok ? "" : "— " + (d || "")); };
  const state = () => page.evaluate(() => { let sc; try { sc = CITY_PLAN_UI.scenario(); } catch (e) { sc = { error: String(e) }; }
    return JSON.stringify({ city: CITY_APP.state.city, sc, msg: CITY_PLAN_UI.state.msg || null }); });
  const imp = (t) => page.evaluate((x) => CITY_PLAN_UI.importText(x), t);

  check("valid Shymkent v2 file imported", await imp(rd("synthetic/shy_valid_clinic_constraints.json")) === true);
  const s0 = JSON.parse(await state());
  check("city is shymkent after import", s0.city === "shymkent", s0.city);
  const invalid = ["synthetic/shy_valid_forged_derived.json", "synthetic/shy_invalid_conflict.json", "synthetic/shy_invalid_outside_bbox.json",
    "synthetic/shy_invalid_nan.json", "synthetic/shy_invalid_dup_key_via_escape.json", "synthetic/shy_invalid_too_large.json",
    "synthetic/shy_invalid_bad_utf8.json", "synthetic/ast_invalid_foreign_snapshot.json", "synthetic/ast_invalid_17_candidates.json", "v1/astana_v1_from_build_whatif.json"];
  for (const n of invalid) {
    const ok = await imp(rd(n)); const s = JSON.parse(await state());
    check(`refused, plan and city unchanged: ${n}`, ok === false && s.city === s0.city && JSON.stringify(s.sc) === JSON.stringify(s0.sc) && /не изменён/.test(s.msg || ""),
      `ok=${ok} city=${s.city} msg=${(s.msg || "").slice(0, 80)}`);
  }
  check("valid Astana file switches the city (BUILD policy)", await imp(rd("synthetic/ast_valid_basic.json")) === true && JSON.parse(await state()).city === "astana");
  const s1 = JSON.parse(await state());
  check("then a refused Shymkent file keeps Astana plan", await imp(rd("synthetic/shy_invalid_conflict.json")) === false && await state() !== null && JSON.stringify(JSON.parse(await state()).sc) === JSON.stringify(s1.sc) && JSON.parse(await state()).city === "astana");
  check("no page errors", errors.length === 0, errors.join("; "));
  await browser.close();
  console.log(`\n${pass} passed, ${fail} failed, 0 skipped`);
  process.exitCode = fail ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
