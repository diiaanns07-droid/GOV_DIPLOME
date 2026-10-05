// K10 round 8: run the K10 packs through the BUILD's own city-plan-v2 module (web/plan.js), headless, and compare with
// the expectations computed by the K10 Python oracle. Tests the BUILD's functions only (no DOM, no file-import UI).
// Usage: node run_build_v2.cjs <app-root> <pack.json> ...   -> JSON report on stdout; exit 1 on any FAIL, 3 if no plan.js
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const [appRoot, ...files] = process.argv.slice(2);
const W = path.join(path.resolve(appRoot), "web");
if (!fs.existsSync(path.join(W, "plan.js"))) {
  process.stdout.write(JSON.stringify({ status: "SKIP", reason: "web/plan.js not in this build (no city-plan-v2 module)" }));
  process.exit(3);
}
const ctx0 = {}; vm.createContext(ctx0); ctx0.window = ctx0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx0, { filename: f });
const F = require(path.join(W, "facts.js"));
const X = require(path.join(W, "whatif.js"));
const PL = require(path.join(W, "plan.js"));
const D = ctx0.CITY_EVIDENCE;
const J = JSON.stringify;
const clone = (o) => JSON.parse(J(o));
// K10 code names -> BUILD code names (names are implementation choices; the meaning must match)
const FEAS = { count_exceeds_max_selected: "too_many", cost_exceeds_budget: "over_budget", required_missing: "missing_required", excluded_selected: "has_excluded" };
const INFEAS = { required_count_exceeds_max_selected: "required_exceeds_max_selected", required_cost_exceeds_budget: "required_cost_exceeds_budget" };
const sameNum = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a)));

function buildCtx(p) {
  if (p.kind === "real_slice") return PL.makeContext(D, p.city_id, F);
  const s = p.synthetic_slice;  // synthetic geometry: a one-city data object built from the pack's own records
  const data = { cities: { [p.city_id]: { bbox: s.bbox, release: "synthetic", files: {}, places: s.records } } };
  return PL.makeContext(data, p.city_id, F);
}
function caseText(c) { return c.pad_to_bytes ? c.raw + " ".repeat(c.pad_to_bytes - Buffer.byteLength(c.raw, "utf8")) : c.raw; }
function objView(o) { return o && { ids: o.ids, cost: o.cost, unknown_count: o.unknown_count, weighted_sum_mm: o.weighted_sum_mm, max_mm: o.max_mm, covered_weight: o.covered_weight }; }
function expView(o) { return o && { ids: o.selected_ids, cost: o.cost, unknown_count: o.unknown_count, weighted_sum_mm: o.weighted_sum_mm, max_mm: o.max_mm, covered_weight: o.covered_weight }; }

function runPack(p) {
  const r = { pack_id: p.pack_id, kind: p.kind, checks: {}, problems: [], notes: [] };
  const put = (name, ok, detail) => { r.checks[name] = ok ? "PASS" : "FAIL"; if (!ok && detail) r.problems.push(`${name}: ${String(detail).slice(0, 300)}`); };
  const ctx = buildCtx(p);
  let input = clone(p.scenario);
  if (p.kind === "real_slice") put("SNAPSHOT", ctx.source_snapshot === input.source_snapshot, `${ctx.source_snapshot} != ${input.source_snapshot}`);
  else { input.source_snapshot = ctx.source_snapshot; r.notes.push("synthetic pack: source_snapshot replaced by the BUILD's own value for the synthetic context"); }

  if (p.invalid_cases) {
    let bad = 0;
    for (const c of p.invalid_cases) {
      let text = caseText(c), got;
      if (p.kind === "real_slice") text = text.split(p.scenario.source_snapshot).join(ctx.source_snapshot);
      try { PL.validatePlanScenario(X.parseStrict(text), ctx); got = { rejected: false }; } catch (e) { got = { rejected: true, code: e.code || e.message }; }
      const want = c.expected.rejected;
      if (got.rejected !== want) {
        if (c.case_id === "html_in_ids" && got.code === "bad_id") r.notes.push("html_in_ids: BUILD refuses ids outside [A-Za-z0-9_.-] (stricter than the length-only rule; acceptable, documented)");
        else { bad++; r.problems.push(`case ${c.case_id}: BUILD ${J(got)} vs oracle ${J(c.expected)}`); }
      }
    }
    put("INVALID_CASES", bad === 0, `${bad} case(s) differ`);
    return r;
  }

  let sc;
  try { sc = PL.validatePlanScenario(input, ctx); } catch (e) { put("VALID", false, e.code || e.message); return r; }
  put("VALID", true);
  const exp = p.expected.optimize;
  const opt = PL.optimizePlans(ctx, sc, { F });
  put("STATUS", opt.status === exp.status, `${opt.status} vs ${exp.status}`);
  if (exp.status === "infeasible") {
    const want = exp.infeasible_reasons.map((c) => INFEAS[c] || c).sort(), got = opt.reasons.map((x) => x.code).sort();
    put("INFEASIBLE_REASONS", J(want) === J(got), `${J(got)} vs ${J(want)}`);
  } else {
    for (const name of ["mean", "minimax", "coverage"]) {
      const a = objView(opt.objectives && opt.objectives[name]), b = expView(exp.objectives[name]);
      put(`OBJ_${name}`, J(a) === J(b), `${J(a)} vs ${J(b)}`);
    }
    const pa = opt.pareto.map((q) => [q.cost, q.weighted_sum_mm, q.ids]), pb = exp.pareto.map((q) => [q.cost, q.weighted_sum_mm, q.selected_ids]);
    put("PARETO", J(pa) === J(pb), `${J(pa).slice(0, 150)} vs ${J(pb).slice(0, 150)}`);
  }
  put("FEASIBLE_COUNT", opt.feasible_count === exp.feasible_count, `${opt.feasible_count} vs ${exp.feasible_count}`);
  r.evaluated = { build: opt.evaluated, k10: exp.evaluated, note: "counted differently by design (BUILD: 2^free masks; K10: subsets within max_selected)" };

  const sens = PL.sensitivity(ctx, sc, { F });
  const sa = sens.map((s) => [s.budget, s.status, s.objectives ? Object.fromEntries(["mean", "minimax", "coverage"].map((n) => [n, s.objectives[n].ids])) : null,
    s.status === "infeasible" ? s.reasons.map((x) => x.code).sort() : null]);
  const sb = exp.sensitivity.map((s) => [s.budget, s.status, s.objectives && Object.keys(s.objectives).length ? Object.fromEntries(["mean", "minimax", "coverage"].map((n) => [n, s.objectives[n].selected_ids])) : null,
    s.status === "infeasible" ? s.infeasible_reasons.map((c) => INFEAS[c] || c).sort() : null]);
  put("SENSITIVITY", J(sa) === J(sb), `${J(sa).slice(0, 200)} vs ${J(sb).slice(0, 200)}`);

  let evalBad = 0;
  for (const [key, plan] of Object.entries(p.expected.plans)) {
    const e = PL.evaluatePlan(ctx, sc, plan.metrics.selected_ids);
    const rows = e.rows.map((x) => [x.id, x.before_mm, x.after_mm, x.delta_mm, x.nearest_before, x.nearest_after]);
    const want = plan.rows.map((x) => [x.control_point_id, x.before_mm, x.after_mm, x.delta_mm, x.nearest_before, x.nearest_after]);
    const m = e.metrics, w = plan.metrics;
    const metOk = m.unknown_count === w.unknown_count && m.weighted_sum_mm === w.weighted_sum_mm && sameNum(m.weighted_mean_mm, w.weighted_mean_mm)
      && m.max_mm === w.max_mm && m.covered_weight === w.covered_weight && sameNum(m.coverage_fraction, w.coverage_fraction) && m.cost === w.cost;
    const fr = e.feasibility.reasons.map((x) => x.code).sort(), fw = plan.feasibility.reasons.map((c) => FEAS[c]).sort();
    const ok = J(rows) === J(want) && metOk && e.feasibility.feasible === plan.feasibility.feasible && J(fr) === J(fw);
    if (!ok) { evalBad++; r.problems.push(`EVALUATE ${key}: rows ${J(rows) === J(want)}, metrics ${metOk}, feasibility ${J(fr)} vs ${J(fw)}`); }
  }
  put("EVALUATE", evalBad === 0, `${evalBad} plan(s) differ`);

  // order of input arrays must not change the plan or the problem digest
  const rev = clone(input);
  for (const k of ["control_points", "candidates", "required_ids", "excluded_ids", "selected_ids"]) rev[k] = rev[k].slice().reverse();
  const opt2 = PL.optimizePlans(ctx, PL.validatePlanScenario(rev, ctx), { F });
  put("ORDER", opt2.problem_digest === opt.problem_digest && J(opt2.objectives) === J(opt.objectives) && J(opt2.pareto) === J(opt.pareto), "reversed input changed the result");
  // selected_ids belong to the scenario digest, not to the problem digest
  const sel0 = { ...sc, selected_ids: [] };
  const selOk = PL.problemDigest(sel0, F) === PL.problemDigest(sc, F)
    && (sc.selected_ids.length === 0 || PL.scenarioDigest(sel0, F) !== PL.scenarioDigest(sc, F));
  put("DIGEST_SELECTED", selOk, "selected_ids handling in digests");
  // an interrupted search must not report "optimal"
  const s1 = PL.createSearch(ctx, sc, { F });
  if (s1.total > 1) {
    s1.step(1);
    const partial = s1.result().status;
    s1.cancel();
    const cancelled = s1.result().status;
    put("PARTIAL_NOT_OPTIMAL", partial !== "optimal" && cancelled !== "optimal", `${partial}/${cancelled}`);
  }
  return r;
}

const results = files.map((f) => {
  const p = JSON.parse(fs.readFileSync(f, "utf8"));
  try { return runPack(p); } catch (e) { return { pack_id: p.pack_id, kind: p.kind, checks: { NO_EXCEPTION: "FAIL" }, problems: [String(e && e.stack || e).slice(0, 400)], notes: [] }; }
});
const sha = (f) => crypto.createHash("sha256").update(fs.readFileSync(path.join(W, f))).digest("hex");
const out = { build: { app_root: path.resolve(appRoot), plan_js_sha256: sha("plan.js"), whatif_js_sha256: sha("whatif.js"), data_js_sha256: sha("data.js") },
  packs: results.length, failures: results.filter((x) => Object.values(x.checks).includes("FAIL")).map((x) => x.pack_id), results };
process.stdout.write(J(out, null, 1));
process.exit(out.failures.length ? 1 : 0);
