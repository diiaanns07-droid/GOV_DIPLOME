// K10 round 10: the Astana package against BUILD's school-access engine (web/govtech/school/case.js), headless.
// Usage: node crosscheck_build_school_case.cjs --app-root <extracted BUILD tree with web/govtech/school/case.js> --sha <BUILD_SHA> [--out DIR]
// 1. Contract divergences: BUILD validateCase/importCase on the package as it is (first refusal is recorded).
// 2. A documented in-memory adapter (to_build): adds variants {A,B}, parameters.target_policy that makes exactly the
//    known_public schools eligible (include_ids), model_assumptions as "id: text" strings. Nothing else is changed.
// 3. BUILD compareCase on the adapted case vs the independent K10 reference (scripts/reference_compare.py):
//    per origin before/after mm (±1 mm allowed for floating-point rounding), metrics, auto choice.
const fs = require("fs"), path = require("path"), { spawnSync } = require("child_process");
const K = path.join(__dirname, "..");
const a = process.argv.slice(2), OPT = { "app-root": null, sha: null, out: null, case: path.join(K, "package/astana.case.json") };
for (let i = 0; i < a.length; i += 2) { const k = a[i].replace(/^--/, ""); if (!(k in OPT)) { console.error("unknown argument " + a[i]); process.exit(2); } OPT[k] = a[i + 1]; }
const ROOT = path.resolve(OPT["app-root"]), OUT = path.resolve(OPT.out || path.join(K, "results", "build_school_case_" + String(OPT.sha || "x").slice(0, 7)));
fs.mkdirSync(OUT, { recursive: true });
const checks = [];
const check = (id, expect, ok, observed, verdict) => checks.push({ id, expect, verdict: verdict || (ok ? "PASS" : "FAIL"), observed: observed === undefined ? null : observed });
const caseFile = path.resolve(OPT.case), text = fs.readFileSync(caseFile, "utf8"), C = JSON.parse(text);
const SCP = path.join(ROOT, "web/govtech/school/case.js");
if (!fs.existsSync(SCP)) { check("X0", "BUILD has web/govtech/school/case.js", false, SCP, "TEST_INCOMPATIBLE"); finish(); return; }
const SC = require(SCP);
const refusal = (f) => { try { f(); return null; } catch (e) { return { code: e.code || null, detail: String(e.detail || e.message).slice(0, 200) }; } };

// 1. as is
const asIs = refusal(() => SC.validateCase(JSON.parse(text)));
const imp = refusal(() => SC.importCase(text, { cities: { astana: { release: "2026-09-23.1" } } }));
check("X1", "record BUILD's verdict on the package as delivered (CONTRACT fields only): valid, or the first contract divergence", true, { validateCase: asIs || "valid", importCase: imp || "imported" }, "INFO");

// 2. adapter
function toBuild(c) {
  const d = JSON.parse(JSON.stringify(c));
  d.variants = { A: null, B: null };
  d.parameters.target_policy = { id: SC.TARGET_POLICY, categories: [], exclude_qa: [], include_ids: d.schools.filter((s) => s.access_eligibility === "known_public").map((s) => s.id).sort(), exclude_ids: [] };
  d.model_assumptions = d.model_assumptions.map((x) => (typeof x === "string" ? x : `${x.id}: ${x.text}`));
  return d;
}
const B = toBuild(C);
const adapted = refusal(() => SC.validateCase(B));
check("X2", "the adapted package passes BUILD validateCase", !adapted, adapted);
const impAdapted = refusal(() => SC.importCase(JSON.stringify(B), { cities: { astana: { release: "2026-09-23.1" } } }));
check("X3", "record BUILD importCase on the adapted package (a snapshot other than the loaded app slice is expected to be refused by BUILD's design)", true, impAdapted || "imported", "INFO");

// 3. numbers vs the K10 reference
const py = spawnSync("python3", [path.join(K, "scripts/reference_compare.py"), caseFile], { encoding: "utf8" });
const ref = JSON.parse(py.stdout);
const refPlan = (sel) => ref.plans.find((p) => p.selected_candidate_ids.join() === sel.join());
const cands = C.candidates.map((k) => k.id).sort();
const runs = [];
for (let i = 0; i < cands.length; i += 2) {
  const d = JSON.parse(JSON.stringify(B)); d.variants = { A: cands[i], B: cands[i + 1] || null };
  runs.push(SC.compareCase(d, SC.geodesicMatrix(d)));
}
const cmp0 = runs[0];
check("X4", "BUILD eligible schools = the package's known_public schools", JSON.stringify(cmp0.eligible_school_ids) === JSON.stringify(B.parameters.target_policy.include_ids), { build: cmp0.eligible_school_ids.length, k10: B.parameters.target_policy.include_ids.length });
const plansByCand = { "": cmp0.plans.find((p) => p.id === "current") };
for (const r of runs) for (const p of r.plans) if (p.id === "A" || p.id === "B") plansByCand[p.selected_candidate_ids.join()] = p;
let worst = 0, rowsCompared = 0;
for (const [sel, bp] of Object.entries(plansByCand)) {
  const rp = refPlan(sel ? sel.split(",") : []);
  const rowsOk = bp.rows.every((r) => { const q = rp.rows.find((x) => x.origin_id === r.origin_id); rowsCompared++; const d = Math.max(Math.abs(r.before_mm - q.before_mm), Math.abs(r.after_mm - q.after_mm)); worst = Math.max(worst, d); return d <= 1 && r.nearest_target_id === q.nearest_target_id; });
  const m = bp.metrics, n = rp.metrics;
  const metricsOk = m.total_origins === n.total_origins && m.known_count === n.known_count && m.unknown_count === n.unknown_count && Math.abs(m.sum_distance_mm - n.sum_distance_mm) <= m.total_origins &&
    Math.abs(m.max_distance_mm - n.max_distance_mm) <= 1 && m.within_threshold_count === n.within_threshold_count;
  check("X5-" + (sel || "current"), `BUILD compareCase = K10 reference for plan [${sel || "current"}]: rows (±1 mm, same nearest target) and metrics`, rowsOk && metricsOk,
    { build: m, k10: n });
}
const auto = cmp0.plans.find((p) => p.id === "auto");
const refBest = ref.plans.slice().sort((x, y) => x.metrics.unknown_count - y.metrics.unknown_count || x.metrics.sum_distance_mm - y.metrics.sum_distance_mm || x.metrics.max_distance_mm - y.metrics.max_distance_mm || x.selected_candidate_ids.length - y.selected_candidate_ids.length)[0];
check("X6", "auto choice (lexicographic min [unknown, sum, max], empty set first on ties) is the same", auto.selected_candidate_ids.join() === refBest.selected_candidate_ids.join(), { build: auto.selected_candidate_ids, k10: refBest.selected_candidate_ids });
check("X7", "BUILD compare result keeps its limitation list honest for this package (records whether 'schools_outside_slice_not_loaded' is still claimed although the package carries buffer schools)", true, cmp0.limitations, "INFO");
finish();

function finish() {
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K10 round-10 cross-check: Astana package × BUILD school-access engine", build_sha: OPT.sha, app_root: path.basename(ROOT), case: path.basename(caseFile),
    adapter: "variants {A,B}=null; target_policy.include_ids = known_public; model_assumptions as strings (in memory only)", total: checks.length,
    pass: by("PASS"), fail: by("FAIL"), info: by("INFO"), test_incompatible: by("TEST_INCOMPATIBLE"), checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 300)}`);
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · INFO ${out.info.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  process.exitCode = out.fail.length || out.test_incompatible.length ? 1 : 0;
}
