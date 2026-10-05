// Adapter: BUILD city-plan-v2 module (prototypes/city-evidence/web/plan.js, first seen at d865dd4) -> K12 round-8 harness interface.
// Only maps shapes; it never changes BUILD behaviour. Read web/plan.js before running (pure module: no DOM, network or eval).
//   importScenario: PL.importPlanScenario(text, ctxFor, F) throws PlanError{code} -> {ok:false, code, state: unchanged}
//   optimize:       PL.optimizePlans(ctx, sc, {F}) + PL.sensitivity(...) -> {status, reasons[code], objectives{mean,...}, pareto, ...}
//   optimizeAsync:  BUILD primitives createSearch().step(chunk)/cancel()/result() driven with a yield between chunks
//   gate:           not exported by BUILD (the stale/request guard lives inside the plan-ui.js closure) -> SKIP, not PASS
"use strict";
const path = require("path");
module.exports = function ({ appRoot, D, requireWeb }) {
  const F = requireWeb("facts.js");
  const PL = requireWeb("plan.js");
  const ctxs = {};
  const ctxFor = (city) => ctxs[city] || (ctxs[city] = PL.makeContext(D, city, F));
  const obj = (o) => o && { selected_ids: o.ids, metrics: { unknown_count: o.unknown_count, weighted_sum_mm: o.weighted_sum_mm, max_mm: o.max_mm,
                                                            covered_weight: o.covered_weight, cost: o.cost } };
  const conv = (r) => ({
    status: r.status, reasons: (r.reasons || []).map((x) => (x && x.code) || String(x)),
    objectives: r.objectives ? { mean: obj(r.objectives.mean), minimax: obj(r.objectives.minimax), coverage: obj(r.objectives.coverage) }
                             : { mean: null, minimax: null, coverage: null },
    pareto: (r.pareto || []).map((p) => ({ cost: p.cost, weighted_sum_mm: p.weighted_sum_mm, selected_ids: p.ids })),
    evaluated: r.evaluated, feasible_count: r.feasible_count, problem_digest: r.problem_digest, metric_version: r.metric_version,
    request_id: r.request_id, complete: r.status === "optimal" || r.status === "infeasible", total_subsets: r.total_subsets });
  const sens = (ctx, sc) => PL.sensitivity(ctx, sc, { F }).map((x) => ({ budget: x.budget, status: x.status,
    reasons: (x.reasons || []).map((y) => y.code), feasible_count: x.feasible_count,
    mean: x.objectives && x.objectives.mean ? { selected_ids: x.objectives.mean.ids, cost: x.objectives.mean.cost,
      weighted_sum_mm: x.objectives.mean.weighted_sum_mm, unknown_count: x.objectives.mean.unknown_count } : null }));
  return {
    name: "build-v2-plan",
    snapshot: (city) => PL.sourceSnapshot(D, city, F),
    initialState: () => ({ scenario: null, evaluation: null }),
    importScenario(text, state) {
      try {
        const r = PL.importPlanScenario(text, ctxFor, F);
        return { ok: true, code: null, state: { scenario: r.scenario, evaluation: r.evaluation } };
      } catch (e) {
        return { ok: false, code: (e && e.code) || "internal_error", message: String(e && e.message), state };
      }
    },
    evaluate: (state) => state.evaluation,
    optimize(state) {
      const ctx = ctxFor(state.scenario.city_id);
      const r = conv(PL.optimizePlans(ctx, state.scenario, { F }));
      r.sensitivity = sens(ctx, state.scenario);
      return r;
    },
    problemDigest: (state) => PL.problemDigest(state.scenario, F),
    async optimizeAsync(state, { requestId = null, signal = null, chunk = 4096, yieldFn = () => new Promise((r) => setTimeout(r, 0)) } = {}) {
      const s = PL.createSearch(ctxFor(state.scenario.city_id), state.scenario, { F, request_id: requestId });
      for (;;) {
        if (signal && signal.aborted) { s.cancel(); break; }
        if (s.step(chunk)) break;
        await yieldFn();
      }
      return conv(s.result());
    },
    sources: () => ["plan.js", "plan-ui.js"].map((n) => path.join(appRoot, "web", n)),
    // API-level check: optimisation of an object that did NOT pass validatePlanScenario (UI and import validate first)
    optimizeUnchecked: (o) => conv(PL.optimizePlans(ctxFor(o.city_id), o, { F })),
  };
};
