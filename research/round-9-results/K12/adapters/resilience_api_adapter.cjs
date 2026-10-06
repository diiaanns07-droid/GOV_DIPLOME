// K12 r9: direct public API of a BUILD city-resilience-v1 module (CORE_SPEC r9: validateResilience, evaluateResilience,
// createResilienceSearch, optimizeResilience). Returns null when web/resilience.js does not exist -> probes are NOT_RUN.
// The export names below follow CORE_SPEC r9; if BUILD exports a different shape, fix THIS adapter (an adapter error is
// not a product FAIL). Read web/resilience.js before running it.
"use strict";
const fs = require("fs"), path = require("path");
module.exports = function ({ appRoot, D, requireWeb }) {
  if (!fs.existsSync(path.join(appRoot, "web", "resilience.js"))) return null;
  const F = requireWeb("facts.js");
  const PL = requireWeb("plan.js");
  const RS = requireWeb("resilience.js");
  const need = ["validateResilience", "evaluateResilience", "createResilienceSearch", "optimizeResilience"];
  const missing = need.filter((n) => typeof RS[n] !== "function");
  if (missing.length) return { adapterError: `web/resilience.js has no ${missing.join(", ")} (update adapters/resilience_api_adapter.cjs)` };
  const cache = {};
  const ctx = (city) => cache[city] || (cache[city] = PL.makeContext(D, city, F));
  return {
    name: "build-resilience-direct-api",
    ctx,
    snapshot: (city) => ctx(city).source_snapshot,
    places: (city, category) => ctx(city).places.filter((p) => p.group === category).map((p) => p.id),
    validate: (env, c) => RS.validateResilience(env, c),
    createSearch: (c, env) => RS.createResilienceSearch(c, env, { F }),
    optimize: (c, env) => RS.optimizeResilience(c, env, { F }),
    evaluate: (c, env, ids) => RS.evaluateResilience(c, env, ids),
  };
};
