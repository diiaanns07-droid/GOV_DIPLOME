// K12 r9: direct public API of BUILD web/plan.js (city-plan-v2), WITHOUT the validating UI/import path.
// Shape (see api_guard.cjs): {name, ctx(city), snapshot(city), places(city, category), validate(obj, ctx),
//   createSearch(ctx, obj), optimize(ctx, obj), sensitivity(ctx, obj), evaluate(ctx, obj, ids)}.
// Only maps names; never changes BUILD behaviour. Read web/plan.js before running it.
"use strict";
module.exports = function ({ D, requireWeb }) {
  const F = requireWeb("facts.js");
  const PL = requireWeb("plan.js");
  const cache = {};
  const ctx = (city) => cache[city] || (cache[city] = PL.makeContext(D, city, F));
  return {
    name: "build-plan-v2-direct-api",
    ctx,
    snapshot: (city) => ctx(city).source_snapshot,
    places: (city, category) => ctx(city).places.filter((p) => p.group === category).map((p) => p.id),
    validate: (obj, c) => PL.validatePlanScenario(obj, c),
    createSearch: (c, obj) => PL.createSearch(c, obj, { F }),
    optimize: (c, obj) => PL.optimizePlans(c, obj, { F }),
    sensitivity: (c, obj) => PL.sensitivity(c, obj, { F }),
    evaluate: (c, obj, ids) => PL.evaluatePlan(c, obj, ids),
  };
};
