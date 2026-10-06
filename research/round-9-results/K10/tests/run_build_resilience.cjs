// K10 round 9: run the K10 city-resilience-v1 packs through the BUILD's OWN web/resilience.js (headless, no DOM) and
// compare with the expectations of the independent K10 oracle (k10res/oracle_res.py). Expectations are never taken
// from BUILD. Output format of BUILD 33cc635 is mapped here (cases in input order, worst vector as an object, no
// manual plan inside optimize): comparison is by case id and by meaning, not byte for byte.
// Usage: node tests/run_build_resilience.cjs <app-root> <pack.json> ...  -> JSON report; exit 1 on FAIL, 3 if no resilience.js
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const [appRoot, ...files] = process.argv.slice(2);
const W = path.join(path.resolve(appRoot), "web");
if (!fs.existsSync(path.join(W, "resilience.js"))) {
  process.stdout.write(JSON.stringify({ status: "NOT_RUN", reason: "web/resilience.js not in this build" }));
  process.exit(3);
}
const c0 = {}; vm.createContext(c0); c0.window = c0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), c0, { filename: f });
const F = require(path.join(W, "facts.js")), X = require(path.join(W, "whatif.js")), PL = require(path.join(W, "plan.js"));
const RS = require(path.join(W, "resilience.js"));
const D = c0.CITY_EVIDENCE, J = JSON.stringify, clone = (o) => JSON.parse(J(o));
const FEAS = { count_exceeds_max_selected: "too_many", cost_exceeds_budget: "over_budget", required_missing: "missing_required", excluded_selected: "has_excluded" };
const INFEAS = { required_count_exceeds_max_selected: "required_exceeds_max_selected", required_cost_exceeds_budget: "required_cost_exceeds_budget" };
const near = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a)));
const vec = (v) => (Array.isArray(v) ? v : [v.unknown_count, v.weighted_sum_mm, v.max_mm]);
const ctxCache = {};
const ctxFor = (city) => ctxCache[city] || (ctxCache[city] = PL.makeContext(D, city, F));
const exportDir = process.env.K10_EXPORT_DIR || null;

function context(p) {
  if (p.kind === "real_slice") return ctxFor(p.city_id);
  const s = p.synthetic_slice;
  return PL.makeContext({ cities: { [p.city_id]: { bbox: s.bbox, release: "synthetic", files: {}, places: s.records } } }, p.city_id, F);
}
function inputOf(p, ctx) {
  const e = clone(p.envelope);
  if (p.kind !== "real_slice") e.plan.source_snapshot = ctx.source_snapshot;
  return e;
}
const caseText = (c) => (c.pad_to_bytes ? c.raw + " ".repeat(c.pad_to_bytes - Buffer.byteLength(c.raw, "utf8")) : c.raw);
const metView = (m) => [m.unknown_count, m.weighted_sum_mm, m.max_mm, m.covered_weight];

function samePlan(got, want) {
  if (!want) return got === null || got === undefined ? [] : ["expected null"];
  const bad = [];
  if (J(got.selected_ids) !== J(want.selected_ids)) bad.push(`ids ${J(got.selected_ids)} vs ${J(want.selected_ids)}`);
  if (got.cost !== want.cost) bad.push(`cost ${got.cost} vs ${want.cost}`);
  if (J(vec(got.worst_vector)) !== J(want.worst_vector)) bad.push(`W ${J(vec(got.worst_vector))} vs ${J(want.worst_vector)}`);
  if (J(got.worst_case_ids) !== J(want.worst_case_ids)) bad.push(`worst ids ${J(got.worst_case_ids)} vs ${J(want.worst_case_ids)}`);
  const byId = Object.fromEntries(got.per_case.map((c) => [c.case_id, c]));
  if (got.per_case.length !== want.per_case.length) bad.push("case count");
  for (const w of want.per_case) {
    const g = byId[w.case_id];
    if (!g) { bad.push(`missing case ${w.case_id}`); continue; }
    if (J(metView(g.metrics)) !== J(metView(w.metrics)) || !near(g.metrics.weighted_mean_mm, w.metrics.weighted_mean_mm)
      || g.source_records !== w.baseline_records) bad.push(`case ${w.case_id}: ${J(metView(g.metrics))}/${g.source_records} vs ${J(metView(w.metrics))}/${w.baseline_records}`);
  }
  if (got.feasibility.feasible !== want.feasibility.feasible
    || J(got.feasibility.reasons.map((r) => r.code).sort()) !== J(want.feasibility.reasons.map((c) => FEAS[c]).sort())) bad.push("feasibility");
  return bad;
}

function runPack(p) {
  const r = { pack_id: p.pack_id, checks: {}, problems: [], notes: [] };
  const put = (n, bad) => { const b = Array.isArray(bad) ? bad : bad ? [] : ["failed"]; r.checks[n] = b.length ? "FAIL" : "PASS"; b.forEach((x) => r.problems.push(`${n}: ${String(x).slice(0, 300)}`)); };
  const ctx = context(p);
  if (p.invalid_cases) {
    let bad = 0;
    r.codes = {};
    for (const c of p.invalid_cases) {
      let got;
      try {
        if (p.kind === "real_slice") RS.importResilience(caseText(c), ctxFor);       // the BUILD's own file-import path
        else RS.validateResilience(X.parseStrict(caseText(c).split(p.synthetic_slice.source_snapshot).join(ctx.source_snapshot)), ctx);
        got = { rejected: false };
      } catch (e) { got = { rejected: true, code: e.code || e.message }; }
      r.codes[c.case_id] = got.rejected ? got.code : "accepted";
      if (got.rejected !== c.expected.rejected) { bad++; r.problems.push(`case ${c.case_id}: BUILD ${J(got)} vs oracle ${J(c.expected)}`); }
    }
    r.checks.INVALID_CASES = bad ? "FAIL" : "PASS";
    return r;
  }
  const input = inputOf(p, ctx);
  let env;
  try { env = RS.validateResilience(clone(input), ctx); r.checks.VALID = "PASS"; } catch (e) { put("VALID", [e.code || e.message]); return r; }
  if (p.kind === "real_slice") {
    try { const im = RS.importResilience(J(input), ctxFor); put("IMPORT", RS.resilienceScenarioDigest(im.envelope, F) === RS.resilienceScenarioDigest(env, F)); }
    catch (e) { put("IMPORT", [e.code || e.message]); }
  }
  const want = p.expected.optimize, got = RS.optimizeResilience(ctx, env, { F });
  put("STATUS", got.status === want.status);
  put("CASE_IDS", J(got.cases.slice().sort()) === J(want.case_ids.slice().sort()));
  put("FEASIBLE_COUNT", got.feasible_count === want.feasible_count);
  put("MANUAL", samePlan(RS.evaluateResilience(ctx, env, env.plan.selected_ids), want.manual));
  if (want.status === "optimal") {
    put("NOMINAL", samePlan(got.nominal, want.nominal));
    put("ROBUST", samePlan(got.robust, want.robust));
    put("PRICE", near(got.price_of_robustness_m, want.price_of_robustness_m) && got.same_plan === want.plans_identical);
  } else {
    put("INFEASIBLE_REASONS", J(got.reasons.map((x) => x.code).sort()) === J(want.infeasible_reasons.map((c) => INFEAS[c] || c).sort()));
    put("PRICE_NULL", got.price_of_robustness_m === null && !!got.price_reason);
  }
  // rows inside each case for the manual plan (before/after/delta/nearest)
  const man = RS.evaluateResilience(ctx, env, env.plan.selected_ids);
  const rowsOf = (pc) => pc.rows.map((x) => [x.id || x.control_point_id, x.before_mm, x.after_mm, x.delta_mm, x.nearest_before, x.nearest_after]);
  const wantRows = Object.fromEntries(p.expected.plans_with_rows.manual.per_case.map((c) => [c.case_id, J(rowsOf(c))]));
  put("ROWS_PER_CASE", man.per_case.every((c) => J(rowsOf(c)) === wantRows[c.case_id]));
  // reversed input: same digest and same plans
  const rev = clone(input);
  rev.cases = rev.cases.slice().reverse().map((c) => ({ ...c, disabled_source_ids: c.disabled_source_ids.slice().reverse() }));
  for (const k of ["control_points", "candidates", "required_ids", "excluded_ids", "selected_ids"]) rev.plan[k] = rev.plan[k].slice().reverse();
  const got2 = RS.optimizeResilience(ctx, RS.validateResilience(rev, ctx), { F });
  const ids = (x) => x && [x.selected_ids, vec(x.worst_vector), x.worst_case_ids];
  put("ORDER", got2.resilience_problem_digest === got.resilience_problem_digest && got2.exclusions_digest === got.exclusions_digest
    && J(ids(got2.nominal)) === J(ids(got.nominal)) && J(ids(got2.robust)) === J(ids(got.robust)));
  // an interrupted search is never "optimal"; an unchecked oversized input is refused before the search
  const s = RS.createResilienceSearch(ctx, clone(input), { F });
  if (s.total > 1) { s.step(1); const a = s.result().status; s.cancel(); put("PARTIAL_NOT_OPTIMAL", a !== "optimal" && s.result().status !== "optimal"); }
  if (p.kind === "real_slice") {
    const big = clone(input);
    big.plan.candidates.push({ ...big.plan.candidates[0], id: "c13x" });
    let code = "accepted"; try { RS.optimizeResilience(ctx, big, { F }); } catch (e) { code = e.code; }
    put("UNCHECKED_INPUT_VALIDATED", code === "too_many_candidates" ? [] : [code]);
    // export is input only and imports again unchanged
    const text = RS.exportResilience(ctx, env);
    const back = RS.importResilience(text, ctxFor).envelope;
    put("EXPORT_ROUNDTRIP", RS.resilienceScenarioDigest(back, F) === RS.resilienceScenarioDigest(env, F) && !/derived/.test(text));
    if (exportDir) fs.writeFileSync(path.join(exportDir, p.pack_id + ".json"), text);
  }
  r.duplicate_case_groups = got.duplicate_case_groups || null;
  return r;
}

const results = files.map((f) => { const p = JSON.parse(fs.readFileSync(f, "utf8")); try { return runPack(p); } catch (e) {
  return { pack_id: p.pack_id, checks: { NO_EXCEPTION: "FAIL" }, problems: [String(e && e.stack || e).slice(0, 400)] }; } });
const sha = (f) => crypto.createHash("sha256").update(fs.readFileSync(path.join(W, f))).digest("hex");
const out = { note: "BUILD web/resilience.js vs K10 oracle expectations", resilience_js_sha256: sha("resilience.js"), plan_js_sha256: sha("plan.js"),
  packs: results.length, failures: results.filter((x) => Object.values(x.checks).includes("FAIL")).map((x) => x.pack_id), results };
process.stdout.write(J(out, null, 1));
process.exit(out.failures.length ? 1 : 0);
