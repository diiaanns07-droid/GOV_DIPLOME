// Adapter: BUILD web/whatif.js (city-whatif-v1) -> interface of research/round-7-results/K12/whatif_import_stress.cjs.
// Maps the BUILD API as read at a5b5e2d: importScenario(text, data, F) -> {scenario, result} or throws WhatIfError{code}.
"use strict";
module.exports = function ({ D, requireWeb }) {
  const W = requireWeb("whatif.js");
  const F = requireWeb("facts.js");
  return {
    name: "build-v1-whatif",
    snapshot: (city /* , category: not part of the BUILD fingerprint */) => W.sourceSnapshot(D, city, F),
    initialState: (city, category) => ({ schema_version: W.SCHEMA, city_id: city, source_snapshot: W.sourceSnapshot(D, city, F),
                                         category, control_points: [], proposed_object: null }),
    importScenario(text, state) {
      try { return { ok: true, code: null, state: W.importScenario(text, D, F).scenario }; }
      catch (e) { return { ok: false, code: e && e.code ? e.code : "exception:" + (e && e.name), state }; }
    },
    compute: (st) => W.compute(D.cities[st.city_id].places, st.category, st.control_points, st.proposed_object).rows
      .map((r) => ({ id: r.id, before_m: r.before, after_m: r.after, delta_m: r.delta, nearest_before_id: r.nearest_before })),
    exportScenario: (st) => W.exportScenario(st, D, F),
  };
};
