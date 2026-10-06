// K10 round 9: run the K10 resilience packs through proposals/resilience.js placed next to the BUILD's own web/plan.js
// (a temporary copy of the app root; the BUILD tree is not changed) and compare with the K10 Python oracle expectations.
// This tests the K10 proposal on top of BUILD plan.js — NOT a BUILD implementation of city-resilience-v1.
// Usage: node tests/run_res_adapter.cjs <app-root> <pack.json> ...   -> JSON report; exit 1 on any FAIL
"use strict";
const fs = require("fs"), os = require("os"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const [appRoot, ...files] = process.argv.slice(2);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "k10res_"));
fs.cpSync(path.join(path.resolve(appRoot), "web"), path.join(tmp, "web"), { recursive: true });
const PROPOSAL = process.env.K10_RES_JS || path.join(__dirname, "..", "proposals", "resilience.js");  // override: mutation runs
fs.copyFileSync(PROPOSAL, path.join(tmp, "web", "resilience.js"));
const W = path.join(tmp, "web");
const ctx0 = {}; vm.createContext(ctx0); ctx0.window = ctx0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx0, { filename: f });
const F = require(path.join(W, "facts.js")), X = require(path.join(W, "whatif.js")), PL = require(path.join(W, "plan.js"));
const RS = require(path.join(W, "resilience.js"));
const D = ctx0.CITY_EVIDENCE, J = JSON.stringify, clone = (o) => JSON.parse(J(o));
const INFEAS = { required_count_exceeds_max_selected: "required_exceeds_max_selected", required_cost_exceeds_budget: "required_cost_exceeds_budget",
  no_subset_satisfies_constraints: "no_feasible_set" };
const FEAS = { count_exceeds_max_selected: "too_many", cost_exceeds_budget: "over_budget", required_missing: "missing_required", excluded_selected: "has_excluded" };
const near = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a)));

function context(p) {
  if (p.kind === "real_slice") return PL.makeContext(D, p.city_id, F);
  const s = p.synthetic_slice;
  return PL.makeContext({ cities: { [p.city_id]: { bbox: s.bbox, release: "synthetic", files: {}, places: s.records } } }, p.city_id, F);
}
function inputOf(p, ctx) {
  const e = clone(p.envelope);
  if (p.kind !== "real_slice") e.plan.source_snapshot = ctx.source_snapshot;  // synthetic: the BUILD's own value
  return e;
}
const caseText = (c) => (c.pad_to_bytes ? c.raw + " ".repeat(c.pad_to_bytes - Buffer.byteLength(c.raw, "utf8")) : c.raw);
const metView = (m) => ({ unknown_count: m.unknown_count, weighted_sum_mm: m.weighted_sum_mm, max_mm: m.max_mm, covered_weight: m.covered_weight, cost: m.cost });

function comparePlan(name, got, want, put) {
  if (!want) { put(`${name}`, got === null, "expected null"); return; }
  const ok = J(got.selected_ids) === J(want.selected_ids) && J(got.worst_vector) === J(want.worst_vector) && J(got.worst_case_ids) === J(want.worst_case_ids)
    && got.per_case.length === want.per_case.length
    && got.per_case.every((c, k) => c.case_id === want.per_case[k].case_id && c.baseline_records === want.per_case[k].baseline_records
      && J(metView(c.metrics)) === J(metView(want.per_case[k].metrics)) && near(c.metrics.weighted_mean_mm, want.per_case[k].metrics.weighted_mean_mm))
    && got.feasibility.feasible === want.feasibility.feasible
    && J(got.feasibility.reasons.map((r) => r.code).sort()) === J(want.feasibility.reasons.map((c) => FEAS[c]).sort());
  put(name, ok, `${J(got.selected_ids)} W ${J(got.worst_vector)} ${J(got.worst_case_ids)} vs ${J(want.selected_ids)} W ${J(want.worst_vector)} ${J(want.worst_case_ids)}`);
}

function runPack(p) {
  const r = { pack_id: p.pack_id, checks: {}, problems: [], notes: [] };
  const put = (n, ok, d) => { r.checks[n] = ok ? "PASS" : "FAIL"; if (!ok && d) r.problems.push(`${n}: ${String(d).slice(0, 300)}`); };
  const ctx = context(p);
  if (p.invalid_cases) {
    let bad = 0;
    for (const c of p.invalid_cases) {
      let text = caseText(c), got;
      if (p.kind !== "real_slice") text = text.split(p.synthetic_slice.source_snapshot).join(ctx.source_snapshot);
      try { RS.validateResilience(X.parseStrict(text), ctx); got = { rejected: false }; } catch (e) { got = { rejected: true, code: e.code || e.message }; }
      r.codes = r.codes || {}; r.codes[c.case_id] = got.rejected ? got.code : "accepted";
      if (got.rejected !== c.expected.rejected) { bad++; r.problems.push(`case ${c.case_id}: adapter ${J(got)} vs oracle ${J(c.expected)}`); }
    }
    put("INVALID_CASES", bad === 0, `${bad} differ`);
    return r;
  }
  const env = RS.validateResilience(inputOf(p, ctx), ctx);
  const want = p.expected.optimize, got = RS.optimizeResilience(ctx, env, { F });
  put("STATUS", got.status === want.status, `${got.status} vs ${want.status}`);
  put("CASE_IDS", J(got.case_ids) === J(want.case_ids), `${J(got.case_ids)} vs ${J(want.case_ids)}`);
  put("FEASIBLE_COUNT", got.feasible_count === want.feasible_count, `${got.feasible_count} vs ${want.feasible_count}`);
  comparePlan("MANUAL", got.manual, want.manual, put);
  if (want.status === "optimal") {
    comparePlan("NOMINAL", got.nominal, want.nominal, put);
    comparePlan("ROBUST", got.robust, want.robust, put);
    put("PRICE", near(got.price_of_robustness_m, want.price_of_robustness_m) && got.plans_identical === want.plans_identical,
      `${got.price_of_robustness_m} vs ${want.price_of_robustness_m}`);
  } else {
    put("INFEASIBLE_REASONS", J(got.reasons.map((x) => x.code).sort()) === J(want.infeasible_reasons.map((c) => INFEAS[c] || c).sort()),
      `${J(got.reasons.map((x) => x.code))} vs ${J(want.infeasible_reasons)}`);
    put("PRICE_NULL", got.price_of_robustness_m === null && got.price_reason !== null);
  }
  // rows inside each case (before/after/nearest) for the manual plan
  const rows = (e) => e.per_case.map((c) => c.rows.map((x) => [x.id || x.control_point_id, x.before_mm, x.after_mm, x.delta_mm, x.nearest_before, x.nearest_after]));
  put("ROWS_PER_CASE", J(rows(got.manual)) === J(rows(p.expected.plans_with_rows.manual)), "manual rows differ");
  // order of cases / ids / arrays does not matter
  const rev = inputOf(p, ctx);
  rev.cases = rev.cases.slice().reverse().map((c) => ({ ...c, disabled_source_ids: c.disabled_source_ids.slice().reverse() }));
  for (const k of ["control_points", "candidates", "required_ids", "excluded_ids", "selected_ids"]) rev.plan[k] = rev.plan[k].slice().reverse();
  const got2 = RS.optimizeResilience(ctx, RS.validateResilience(rev, ctx), { F });
  const noRows = (e) => e && { ...e, per_case: e.per_case.map(({ rows, ...c }) => c) };  // rows follow the input order of points
  put("ORDER", got2.resilience_problem_digest === got.resilience_problem_digest && got2.exclusions_digest === got.exclusions_digest
    && J(noRows(got2.robust)) === J(noRows(got.robust)) && J(noRows(got2.nominal)) === J(noRows(got.nominal)), "reversed input changed the result");
  // an interrupted search is never "optimal"; a validated envelope cannot be changed; an unchecked one is validated
  const s = RS.createResilienceSearch(ctx, env, { F });
  if (s.total > 1) { s.step(1); const a = s.result().status; s.cancel(); put("PARTIAL_NOT_OPTIMAL", a !== "optimal" && s.result().status === "cancelled", a); }
  let frozen = false; try { env.plan.candidates.push({}); } catch (e) { frozen = true; }
  put("VALIDATED_FROZEN", frozen && Object.isFrozen(env.plan.candidates));
  if (p.kind === "real_slice") {
    const big = inputOf(p, ctx);
    big.plan.candidates.push({ ...big.plan.candidates[0], id: "c13x" });
    let code = "accepted"; try { RS.optimizeResilience(ctx, big, { F }); } catch (e) { code = e.code; }
    put("UNCHECKED_INPUT_VALIDATED", code === "too_many_candidates", code);
  }
  return r;
}

const results = files.map((f) => { const p = JSON.parse(fs.readFileSync(f, "utf8")); try { return runPack(p); } catch (e) {
  return { pack_id: p.pack_id, checks: { NO_EXCEPTION: "FAIL" }, problems: [String(e && e.stack || e).slice(0, 400)] }; } });
fs.rmSync(tmp, { recursive: true, force: true });
const sha = (f) => crypto.createHash("sha256").update(fs.readFileSync(path.join(path.resolve(appRoot), "web", f))).digest("hex");
const out = { note: "K10 proposal resilience.js on top of the BUILD's plan.js; not a BUILD implementation",
  build_plan_js_sha256: sha("plan.js"), proposal_sha256: crypto.createHash("sha256").update(fs.readFileSync(PROPOSAL)).digest("hex"),
  packs: results.length, failures: results.filter((x) => Object.values(x.checks).includes("FAIL")).map((x) => x.pack_id), results };
process.stdout.write(J(out, null, 1));
process.exit(out.failures.length ? 1 : 0);
