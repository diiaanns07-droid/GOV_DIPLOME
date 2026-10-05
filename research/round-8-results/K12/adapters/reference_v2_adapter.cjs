// Adapter for the K12 reference city-plan-v2 module. sha256hex/placesDigest come from the app's own facts.js.
"use strict";
const path = require("path");
module.exports = function ({ D, requireWeb }) {
  const F = requireWeb("facts.js");
  const P = require(path.join(__dirname, "..", "reference", "plan_v2_ref.cjs"));
  const reg = P.makeRegistry(D, { sha256hex: F.sha256hex, placesDigest: F.placesDigest });
  return {
    name: "k12-reference-v2",
    snapshot: (city) => reg.cities[city].snapshot,
    initialState: () => ({ scenario: null, evaluation: null }),
    importScenario: (text, state) => P.importPlanScenario(text, reg, state),
    evaluate: (state) => state.evaluation,
    optimize: (state) => P.optimizePlans(reg, state.scenario),
    problemDigest: (state) => P.problemDigest(reg, state.scenario),
    // stage 2 hooks
    module: P, registry: reg,
  };
};
