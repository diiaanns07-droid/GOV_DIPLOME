// DELIBERATELY NAIVE importer — shows what the stress test catches. Not a proposal.
// JSON.parse (last duplicate key wins, 1e999 -> Infinity), few checks, mutates the passed state,
// trusts imported "results".
"use strict";
module.exports = function ({ D }) {
  const snapshot = (city, category) => `naive:${city}:${category}`;
  const initialState = (city, category) => ({ city, category, snapshot: snapshot(city, category), control_points: [], proposed_object: null });
  function importScenario(text, state) {
    try {
      const s = JSON.parse(text);
      if (s.schema_version !== "city-whatif-v1") return { ok: false, code: "unknown_version", state };
      if (!D.cities[s.city_id]) return { ok: false, code: "unknown_city", state };
      if (!Array.isArray(s.control_points) || s.control_points.length === 0) return { ok: false, code: "no_points", state };
      Object.assign(state, { city: s.city_id, category: s.category, snapshot: s.source_snapshot,
                             control_points: s.control_points, proposed_object: s.proposed_object, results: s.results });
      return { ok: true, code: null, state };
    } catch (e) {
      return { ok: false, code: "invalid_json", state };
    }
  }
  function compute(state) {
    if (state.results && state.results.rows) return state.results.rows.map((r) => ({ id: r.id, before_m: r.before_m, after_m: r.after_m, delta_m: r.delta_m, nearest_before_id: null }));
    return state.control_points.map((cp) => ({ id: cp.id, before_m: null, after_m: null, delta_m: null, nearest_before_id: null }));
  }
  return { name: "naive", snapshot, initialState, importScenario, compute };
};
