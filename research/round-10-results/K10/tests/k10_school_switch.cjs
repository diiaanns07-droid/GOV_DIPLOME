// K10 round 10: city switch in BUILD's school-access main path (window.SCHOOL_UI, BUILD r10 and later) on the real page.
// Usage: node k10_school_switch.cjs [--url http://127.0.0.1:8501/] [--label …] [--sha …] [--out DIR] [--mutate nocityhook|keepsel]
// --mutate breaks the page on purpose (test of the test): checks must then FAIL.
// Shymkent: choose A and B, compare, select a school -> switch to Astana with the visible city button -> checks:
// city, case_id/snapshot/bbox/digest, school records and map layers hold only Astana data; no selection, A/B result or
// verdict text of Shymkent; analysis/candidate points inside the Astana frame -> back to Shymkent -> simulator (52,56).
// Desktop 1440 and 390 px. If the build has no SCHOOL_UI the run is TEST_INCOMPATIBLE (not PASS).
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const a = process.argv.slice(2), OPT = { url: "http://127.0.0.1:8501/", label: "site", sha: null, out: null, mutate: null };
for (let i = 0; i < a.length; i += 2) { const k = a[i].replace(/^--/, ""); if (!(k in OPT)) { console.error("unknown argument " + a[i]); process.exit(2); } OPT[k] = a[i + 1]; }
const OUT = path.resolve(OPT.out || path.join(__dirname, "..", "results", "school_switch_" + OPT.label)), SHOTS = path.join(OUT, "screenshots");
const checks = [];
const check = (id, expect, ok, observed, verdict) => checks.push({ id, expect, verdict: verdict || (ok ? "PASS" : "FAIL"), observed: observed === undefined ? null : observed });
const tick = (p, ms = 250) => p.waitForTimeout(ms);
const snap = (p) => p.evaluate(() => {
  const S = SCHOOL_UI.state, c = SCHOOL_UI.caseOf(S.city), D = CITY_EVIDENCE, bb = c.bbox;
  const inside = (r) => bb[0] <= r.lon && r.lon <= bb[2] && bb[1] <= r.lat && r.lat <= bb[3];
  const src = (id) => (typeof map !== "undefined" && map && map.getSource && map.getSource(id)) ? map.getSource(id)._data : null;
  const links = src("sc-links"), schools = src("sc-schools");
  return { city: S.city, case_city: c.city_id, case_id: c.case_id, snapshot: c.snapshot_id, bbox: bb, digest: S.cmp && S.cmp.case_digest, sel: S.sel, compared: S.compared, view: S.view,
    variants: c.variants, school_ids: c.schools.map((s) => s.id), origin_ids: c.origins.map((o) => o.id), cand_ids: c.candidates.map((k) => k.id),
    originsInside: c.origins.every(inside), candsInside: c.candidates.every(inside), sliceIds: D.cities[S.city].places.map((x) => x.id), astIds: D.cities.astana.places.map((x) => x.id),
    mapSchools: schools ? schools.features.map((f) => f.properties.id) : null,
    mapLinkCoords: links ? links.features.flatMap((f) => f.geometry.coordinates) : null,
    text: (document.getElementById("gov-panel") || document.body).innerText + " " + [...document.querySelectorAll("[class^=sc-], [class*=' sc-'], [id^=sc-]")].map((e) => e.innerText || "").join(" "),
    title: document.title, score: document.getElementById("city-score").textContent, mapReady: typeof mapReady !== "undefined" && mapReady };
});

async function run(browser, vp, tag) {
  const ctx = await browser.newContext({ viewport: vp }), p = await ctx.newPage(), errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message || e)));
  await p.goto(OPT.url); await tick(p, 4000);
  const score0 = await p.evaluate(() => document.getElementById("city-score").textContent);
  if (!(await p.evaluate(() => !!window.SCHOOL_UI))) { check(`${tag}-SS0`, "build has the school-access main path (window.SCHOOL_UI)", false, null, "TEST_INCOMPATIBLE"); await ctx.close(); return; }
  await p.click("#govtech-toggle"); await tick(p, 1500);
  if (OPT.mutate === "nocityhook") await p.evaluate(() => { CITY_APP.ui.EXT.onCity.length = 0; });
  if (OPT.mutate === "keepsel") await p.evaluate(() => { const S = SCHOOL_UI.state; CITY_APP.ui.EXT.onCity.unshift(() => { const keep = { sel: S.sel, compared: S.compared }; setTimeout(() => Object.assign(S, keep), 0); }); });
  await p.evaluate(() => { const c = SCHOOL_UI.caseOf(SCHOOL_UI.state.city); SCHOOL_UI.assign("A", c.candidates[0].id); SCHOOL_UI.assign("B", c.candidates[c.candidates.length - 1].id); SCHOOL_UI.compare(); SCHOOL_UI.select("school", c.schools[0].id); });
  await tick(p, 800);
  const s1 = await snap(p);
  const shyNames = await p.evaluate(() => SCHOOL_UI.caseOf("shymkent").schools.map((s) => s.label).filter((l) => l && l.length > 5));
  check(`${tag}-SS1`, "Shymkent state produced: A and B set, compared, a school selected (precondition)", s1.city === "shymkent" && s1.variants.A && s1.variants.B && s1.compared && s1.sel, { variants: s1.variants, compared: s1.compared, sel: s1.sel });
  await p.locator('[data-city="astana"]:visible').first().click(); await tick(p, 1500);
  const s2 = await snap(p);
  check(`${tag}-SS2`, "the case follows the city: city, case_id, snapshot, bbox and case_digest change", s2.city === "astana" && s2.case_city === "astana" && s2.case_id !== s1.case_id && s2.snapshot !== s1.snapshot && JSON.stringify(s2.bbox) !== JSON.stringify(s1.bbox) && s2.digest !== s1.digest,
    { case_id: [s1.case_id, s2.case_id], snapshot: [s1.snapshot, s2.snapshot], digest: [String(s1.digest).slice(0, 18), String(s2.digest).slice(0, 18)] });
  check(`${tag}-SS3`, "no selection, comparison or A/B view of Shymkent survives the switch", !s2.sel && !s2.compared && s2.view === "current", { sel: s2.sel, compared: s2.compared, view: s2.view, variants: s2.variants });
  const foreign = s2.school_ids.filter((id) => s1.school_ids.includes(id) || !s2.sliceIds.includes(id));
  check(`${tag}-SS4`, "school records are Astana records only", s2.school_ids.length > 0 && foreign.length === 0, { n: s2.school_ids.length, foreign: foreign.slice(0, 3) });
  check(`${tag}-SS5`, "analysis points and candidate places lie inside the Astana frame", s2.originsInside && s2.candsInside, { originsInside: s2.originsInside, candsInside: s2.candsInside });
  const sharedIds = s2.origin_ids.filter((id) => s1.origin_ids.includes(id)).length + s2.cand_ids.filter((id) => s1.cand_ids.includes(id)).length;
  check(`${tag}-SS6`, "info: generated point/place IDs reused across cities (coordinates differ; results are keyed by case_digest)", true, { shared_generated_ids: sharedIds }, "INFO");
  if (s2.mapReady && s2.mapSchools) {
    const bb = s2.bbox, far = s2.mapLinkCoords.filter(([x, y]) => x < bb[0] - 0.05 || x > bb[2] + 0.05 || y < bb[1] - 0.05 || y > bb[3] + 0.05);
    check(`${tag}-SS7`, "map layers: school layer holds only Astana school IDs (= the case); every link vertex is near the Astana frame", s2.mapSchools.every((id) => s2.school_ids.includes(id) && s2.astIds.includes(id)) && s2.mapSchools.length === s2.school_ids.length && far.length === 0,
      { schools: s2.mapSchools.length, far: far.slice(0, 2) });
  } else check(`${tag}-SS7`, "map layers hold only Astana data", false, "map not ready", "NOT_RUN");
  const leaked = shyNames.filter((n) => s2.text.includes(n));
  check(`${tag}-SS8`, "no Shymkent school name in the visible planning UI after the switch (strip, card, verdict)", leaked.length === 0, leaked.slice(0, 3));
  if (tag === "1440") await p.screenshot({ path: path.join(SHOTS, `${tag}_astana_after_switch.png`) });
  await p.locator('[data-city="shymkent"]:visible').first().click(); await tick(p, 1200);
  const s3 = await snap(p);
  check(`${tag}-SS9`, "back to Shymkent: only Shymkent records; the digest is Shymkent's again (per-city state is kept by design, nothing of Astana)", s3.city === "shymkent" && s3.school_ids.every((id) => s3.sliceIds.includes(id)) && s3.digest !== s2.digest,
    { digest: String(s3.digest).slice(0, 18), restoredVariants: s3.variants });
  await p.click("#govtech-toggle"); await tick(p, 800);
  const s4 = await p.evaluate(() => ({ active: GOVTECH.active, score: document.getElementById("city-score").textContent }));
  check(`${tag}-SS10`, "simulator: training score unchanged", !s4.active && s4.score === score0, { score0, ...s4 });
  check(`${tag}-SS11`, "no page errors", errors.length === 0, errors.slice(0, 3));
  await ctx.close();
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  await run(browser, { width: 1440, height: 900 }, "1440");
  await run(browser, { width: 390, height: 844 }, "390");
  await browser.close();
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K10 round-10 city switch in BUILD's school-access path", url: OPT.url, label: OPT.label, sha: OPT.sha, total: checks.length,
    pass: by("PASS"), fail: by("FAIL"), not_run: by("NOT_RUN"), info: by("INFO"), test_incompatible: by("TEST_INCOMPATIBLE"), checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 300)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · NOT_RUN ${out.not_run.length} · INFO ${out.info.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  process.exitCode = out.fail.length || out.test_incompatible.length ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
