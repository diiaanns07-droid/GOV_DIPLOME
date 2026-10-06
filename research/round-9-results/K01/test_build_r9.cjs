// K01 round 9 stage 3: run K01 city-resilience-v1 fixtures against the BUILD's own web/resilience.js (when it exists).
//   node test_build_r9.cjs --app-root APP [--label "BUILD <sha>"]
// exit 0 = no defect; 1 = defect (accept/reject mismatch, state change on refusal, digest not canonical, unvalidated API);
// 3 = NOT_RUN (BUILD has no web/resilience.js). Code-name differences are reported (CONTRACT_DIFF), not counted as defects.
// Adapter (CORE_SPEC r9 names): R.validateResilience(input, ctx); import = R.importResilience | R.importResilienceScenario (text, ctxFor, F);
// optimize = R.optimizeResilience(ctx, envelope, {F}) -> {status, resilience_problem_digest, ...}.
const fs = require("fs"), path = require("path");
const { loadBuild } = require("./build_adapter.cjs");
const APP = process.argv[process.argv.indexOf("--app-root") + 1];
const li = process.argv.indexOf("--label"), LABEL = li > 0 ? process.argv[li + 1] : "BUILD";
const B = loadBuild(APP);
if (!B.R) { console.log(`NOT_RUN: ${LABEL} has no web/resilience.js — BUILD r9 resilience integration not available`); process.exit(3); }
const R = B.R, FX = path.join(__dirname, "fixtures");
const importFn = R.importResilience || R.importResilienceScenario;
let pass = 0, fail = 0; const diffs = [];
const t = (n, fn) => { try { const r = fn(); if (r === "SKIP") { console.log("SKIP", n); return; } pass++; console.log("PASS", n); } catch (e) { fail++; console.log("FAIL", n, "—", e.message); } };
const imp = (txt) => {
  try { const r = importFn ? importFn(txt, B.ctxFor, B.F) : (() => { const o = B.X.parseStrict(txt); return { envelope: R.validateResilience(o, B.ctxFor(o.plan.city_id)) }; })();
    return { ok: true, env: r.envelope || r.scenario || r }; }
  catch (e) { if (e && e.code) return { ok: false, code: e.code }; return { ok: false, code: "UNTYPED:" + e.message }; }
};
const EXP = JSON.parse(fs.readFileSync(path.join(FX, "RESILIENCE_EXPECTED.json"), "utf8")).fixtures;
for (const [n, e] of Object.entries(EXP)) {
  t(`${LABEL}: ${n} → ${e.valid ? "valid" : "reject"}`, () => {
    const r = imp(B.browserText(new Uint8Array(fs.readFileSync(path.join(FX, "resilience", n)))));
    if (r.ok !== e.valid) throw new Error(`${r.ok ? "accepted" : "rejected (" + r.code + ")"}; K01 expects ${e.valid ? "valid" : e.code}; minimal: fixtures/resilience/${n}`);
    if (!r.ok && String(r.code).startsWith("UNTYPED")) throw new Error("untyped error " + r.code);
    if (!r.ok && r.code !== e.code) diffs.push({ fixture: n, k01: e.code, build: r.code });
  });
}
const optimize = R.optimizeResilience;
t(`${LABEL}: resilience_problem_digest canonical (cases/exclusions/points order) and selected-independent`, () => {
  if (!optimize) return "SKIP";
  const o = JSON.parse(fs.readFileSync(path.join(FX, "resilience", "shy_valid_two_cases.json"), "utf8"));
  const run = (x) => { const r = imp(JSON.stringify(x)); if (!r.ok) throw new Error("fixture rejected " + r.code); return optimize(B.ctxFor("shymkent"), r.env, { F: B.F }).resilience_problem_digest; };
  const d0 = run(o), p = JSON.parse(JSON.stringify(o));
  p.cases.reverse(); p.cases[0].disabled_source_ids.reverse(); p.plan.control_points.reverse(); p.plan.candidates.reverse();
  if (run(p) !== d0) throw new Error("digest depends on order");
  const s = JSON.parse(JSON.stringify(o)); s.plan.selected_ids = []; if (run(s) !== d0) throw new Error("selected_ids in problem digest");
  const l = JSON.parse(JSON.stringify(o)); l.cases[0].label += "!"; if (run(l) === d0) throw new Error("label not in digest");
});
t(`${LABEL}: optimizeResilience validates unverified input (13 candidates → typed too_many_candidates before search)`, () => {
  if (!optimize) return "SKIP";
  const ok = imp(fs.readFileSync(path.join(FX, "resilience", "shy_valid_two_cases.json"), "utf8")).env;
  const bad = JSON.parse(JSON.stringify(ok)); bad.plan.candidates = Array.from({ length: 13 }, (_, k) => Object.assign({}, ok.plan.candidates[0], { id: "k" + k }));
  bad.plan.required_ids = []; bad.plan.excluded_ids = []; bad.plan.selected_ids = [];
  let code = null; try { optimize(B.ctxFor("shymkent"), bad, { F: B.F }); } catch (e) { code = e.code; }
  if (code !== "too_many_candidates") throw new Error("got " + code + "; minimal: valid envelope, then plan.candidates = 13 copies, passed to optimizeResilience");
});
console.log(`\n${pass} passed, ${fail} failed`);
if (diffs.length) console.log("CONTRACT_DIFF (code names, not defects):\n" + diffs.map((d) => `  ${d.fixture}: K01 ${d.k01} / ${LABEL} ${d.build}`).join("\n"));
process.exitCode = fail ? 1 : 0;
