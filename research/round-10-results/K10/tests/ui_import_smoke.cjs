// K10 round 10: UI-import smoke of the Astana school-access-case-v1 package on a NEW BUILD of the main site.
// Usage: node ui_import_smoke.cjs --url http://127.0.0.1:8501/ --sha <BUILD_SHA> [--adapter adapter.json]
//        [--case package/astana.case.json] [--other-case <Shymkent case of K01>] [--out DIR]
// The page must expose an import seam. Default adapter (override any key with --adapter JSON):
//   open:   JS run before importing (e.g. open the school-access mode)                 default: GOVTECH?.setActive?.(true)
//   import: JS taking `text`, returns {ok:boolean, code?:string} (or use fileInput)    default: window.SCHOOL_ACCESS_UI.importText(text)
//   fileInput: CSS selector of the case <input type=file> (used when `import` is null)
//   state:  JS returning {city_id, case_id, case_digest, school_ids[], origin_ids[], candidate_ids[], result_digest|null,
//           ai_digest|null, labels_text}                                              default: window.SCHOOL_ACCESS_UI.state()
// If the seam is missing the run is TEST_INCOMPATIBLE and the integration stays NOT_RUN (never PASS).
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const K = path.join(__dirname, "..");
const a = process.argv.slice(2), OPT = { url: "http://127.0.0.1:8501/", sha: null, adapter: null, case: path.join(K, "package/astana.case.json"), "other-case": null, out: null };
for (let i = 0; i < a.length; i += 2) { const k = a[i].replace(/^--/, ""); if (!(k in OPT)) { console.error("unknown argument " + a[i]); process.exit(2); } OPT[k] = a[i + 1]; }
const AD = Object.assign({ open: "window.GOVTECH && GOVTECH.setActive && GOVTECH.setActive(true)", import: "window.SCHOOL_ACCESS_UI.importText(text)", fileInput: null, state: "window.SCHOOL_ACCESS_UI.state()" },
  OPT.adapter ? JSON.parse(fs.readFileSync(OPT.adapter, "utf8")) : {});
const OUT = path.resolve(OPT.out || path.join(K, "results", "ui_import_" + String(OPT.sha || "unknown").slice(0, 7)));
const checks = [];
const check = (id, expect, ok, observed, verdict) => checks.push({ id, expect, verdict: verdict || (ok ? "PASS" : "FAIL"), observed: observed === undefined ? null : observed });
const caseText = fs.readFileSync(OPT.case, "utf8"), C = JSON.parse(caseText);
const ids = (k) => C[k].map((r) => r.id).sort();
// refused imports: each must leave the page state exactly as it was (atomic refusal)
const BAD = {
  derived_results: (c) => { c.plans = []; },
  unknown_field: (c) => { c.schools[0].population = 1000; },
  too_many_origins: (c) => { c.origins = Array.from({ length: 26 }, (_, i) => ({ ...c.origins[0], id: "o" + i })); },
  bad_city: (c) => { c.city_id = "almaty"; },
  capacity_without_source: (c) => { c.schools[0].capacity = 900; },
  candidate_called_land: (c) => { c.candidates[0].land_status = "free"; },
  origin_outside_bbox: (c) => { c.origins[0].lon = c.bbox[2] + 0.05; },
  not_json: () => "{ not json",
};

async function doImport(p, text) {
  if (AD.import) return p.evaluate(({ expr, text }) => Promise.resolve(eval(expr)), { expr: AD.import, text });  // adapter expression, written by BUILD/K10
  await p.setInputFiles(AD.fileInput, { name: "case.json", mimeType: "application/json", buffer: Buffer.from(text, "utf8") });
  await p.waitForTimeout(400);
  return null;
}
const state = (p) => p.evaluate((expr) => eval(expr), AD.state);

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch(), p = await browser.newPage({ viewport: { width: 1440, height: 900 } }), errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  await p.goto(OPT.url); await p.waitForTimeout(2500);
  await p.evaluate((expr) => { try { eval(expr); } catch (e) { /* reported by the seam check */ } }, AD.open); await p.waitForTimeout(500);
  const seam = await p.evaluate(({ imp, st, fi }) => { try { return { state: typeof eval(st) === "object", imp: imp ? /\(/.test(imp) && typeof eval(imp.split("(")[0]) === "function" : !!document.querySelector(fi) }; } catch (e) { return { error: String(e.message) }; } },
    { imp: AD.import, st: AD.state, fi: AD.fileInput });
  if (!seam.state || !seam.imp) {
    check("U0", "the build exposes a school-access-case-v1 import seam (adapter: import/fileInput + state)", false, seam, "TEST_INCOMPATIBLE");
  } else {
    const s0 = await state(p);
    let r = await doImport(p, caseText); await p.waitForTimeout(400);
    const s1 = await state(p);
    check("U1", "Astana package imports: city astana, case_id, all school/origin/candidate IDs of the file", (!r || r.ok) && s1.city_id === "astana" && s1.case_id === C.case_id &&
      JSON.stringify((s1.school_ids || []).slice().sort()) === JSON.stringify(ids("schools")) && JSON.stringify((s1.origin_ids || []).slice().sort()) === JSON.stringify(ids("origins")) &&
      JSON.stringify((s1.candidate_ids || []).slice().sort()) === JSON.stringify(ids("candidates")), { r, city: s1.city_id, schools: (s1.school_ids || []).length, origins: (s1.origin_ids || []).length });
    check("U2", "the page shows that data are secondary/not verified and that candidates are hypotheses (labels text)", /не официальн|вторичн|NOT_FETCHED|не проверен/i.test(s1.labels_text || "") && /гипотез/i.test(s1.labels_text || ""), (s1.labels_text || "").slice(0, 200));
    check("U3", "a case digest is shown and no result/AI answer exists before a run", !!s1.case_digest && !s1.result_digest && !s1.ai_digest, { digest: s1.case_digest, result: s1.result_digest, ai: s1.ai_digest });
    for (const [name, f] of Object.entries(BAD)) {
      const c = JSON.parse(caseText); const t = f(c); const text = typeof t === "string" ? t : JSON.stringify(c);
      const before = JSON.stringify(await state(p));
      r = await doImport(p, text).catch((e) => ({ ok: false, code: "threw: " + e.message }));
      await p.waitForTimeout(300);
      const after = JSON.stringify(await state(p));
      check("UR-" + name, `refused import (${name}) leaves the state unchanged`, (r === null || r.ok === false) && before === after, { r, changed: before !== after });
    }
    if (OPT["other-case"]) {
      const other = fs.readFileSync(OPT["other-case"], "utf8"), O = JSON.parse(other);
      await doImport(p, other); await p.waitForTimeout(400);
      const so = await state(p);
      await doImport(p, caseText); await p.waitForTimeout(400);
      const sa = await state(p);
      const foreign = (sa.school_ids || []).concat(sa.origin_ids || [], sa.candidate_ids || []).filter((x) => O.schools.concat(O.origins, O.candidates).some((r) => r.id === x));
      check("U4", `switch ${O.city_id} → astana by import: digest changes, no record of ${O.city_id} remains, no result/AI of the previous case`,
        so.city_id === O.city_id && sa.city_id === "astana" && so.case_digest !== sa.case_digest && foreign.length === 0 && !sa.result_digest && !sa.ai_digest,
        { from: so.city_id, to: sa.city_id, digests: [so.case_digest, sa.case_digest], foreign: foreign.slice(0, 5) });
    } else check("U4", "switch between two city cases by import", false, "no --other-case (K01 Shymkent package) given", "NOT_RUN");
    await p.screenshot({ path: path.join(OUT, "astana_imported.png") });
    check("U5", "no page errors", errors.length === 0, errors.slice(0, 5));
  }
  await browser.close();
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K10 round-10 UI-import smoke (school-access-case-v1, Astana)", url: OPT.url, build_sha: OPT.sha, case: path.basename(OPT.case), adapter: AD, total: checks.length,
    pass: by("PASS"), fail: by("FAIL"), not_run: by("NOT_RUN"), test_incompatible: by("TEST_INCOMPATIBLE"), checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 300)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · NOT_RUN ${out.not_run.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  process.exitCode = out.fail.length || out.test_incompatible.length ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
