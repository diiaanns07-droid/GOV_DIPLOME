// K12 r9: BUILD city-resilience-v1 behind the import interface of resilience_stress.cjs. Returns null when
// web/resilience.js is missing (-> NOT_RUN). Read web/resilience.js before running it.
// Import: RS.importResilience(text, ctxFor, F) if BUILD exports it; otherwise BUILD's own strict parser (whatif.js
// parseStrict, 256 KiB / duplicate keys / NaN) followed by RS.validateResilience(obj, ctx) — the composition CORE_SPEC r9 names.
// optimize() must be normalised to: {status, reasons[], evaluated, feasible_count, nominal{ids, worst_vector, worst_case_ids},
// robust{ids, worst_vector, worst_case_ids}, price_of_robustness_m}. Field names below follow CORE_SPEC r9; if BUILD
// differs, fix THIS mapping (an adapter error is not a product FAIL).
"use strict";
const fs = require("fs"), path = require("path");
module.exports = function ({ appRoot, D, requireWeb }) {
  if (!fs.existsSync(path.join(appRoot, "web", "resilience.js"))) return null;
  const F = requireWeb("facts.js"), X = requireWeb("whatif.js"), PL = requireWeb("plan.js"), RS = requireWeb("resilience.js");
  const cache = {};
  const ctxFor = (city) => cache[city] || (cache[city] = PL.makeContext(D, city, F));
  const ids = (p) => p && (p.ids || p.selected_ids || null);
  const norm = (p) => p && { ids: ids(p), worst_vector: p.worst_vector || null, worst_case_ids: p.worst_case_ids || null };
  return {
    name: "build-resilience-import",
    snapshot: (city) => PL.sourceSnapshot(D, city, F),
    initialState: () => ({ envelope: null }),
    importEnvelope(text, state) {
      try {
        let env;
        if (typeof RS.importResilience === "function") env = RS.importResilience(text, ctxFor, F);
        else { const o = X.parseStrict(text); env = RS.validateResilience(o, ctxFor(o && o.plan && o.plan.city_id)); }
        return { ok: true, code: null, state: { envelope: env.envelope || env } };
      } catch (e) {
        return { ok: false, code: (e && e.code) || "internal_error", message: String(e && e.message), state };
      }
    },
    optimize(state) {
      const env = state.envelope, r = RS.optimizeResilience(ctxFor(env.plan.city_id), env, { F });
      return { status: r.status, reasons: (r.reasons || []).map((x) => (x && x.code) || x), evaluated: r.evaluated, feasible_count: r.feasible_count,
        nominal: norm(r.nominal), robust: norm(r.robust), price_of_robustness_m: r.price_of_robustness_m !== undefined ? r.price_of_robustness_m : r.price_m, raw: r };
    },
  };
};
