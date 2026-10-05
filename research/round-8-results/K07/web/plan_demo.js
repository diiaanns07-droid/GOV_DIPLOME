/* K07 round 8 — explicit SYNTHETIC demo set for the city-plan-v2 editor.
 * Positions are a deterministic grid inside the slice bbox; weights and costs are made-up conditional values for
 * checking the interface. They are NOT city statistics, NOT addresses of real sites, NOT prices in tenge.
 * Browser: window.CITY_PLAN_DEMO; Node: module.exports (tools/make_fixtures.cjs writes the same set to fixtures/).
 */
(function (root) {
  "use strict";
  const LABEL = "SYNTHETIC demo (K07 r8): точки, места, веса и стоимости выдуманы для проверки интерфейса, не данные города";
  const r6 = (x) => Math.round(x * 1e6) / 1e6;
  // u, v in [0, 1] → a point inside bbox with a 10 % margin
  const at = (bb, u, v) => [r6(bb[0] + (bb[2] - bb[0]) * (0.1 + 0.8 * u)), r6(bb[1] + (bb[3] - bb[1]) * (0.1 + 0.8 * v))];
  const PTS = [[0.05, 0.1], [0.35, 0.05], [0.7, 0.12], [0.95, 0.08], [0.15, 0.4], [0.5, 0.35], [0.85, 0.45], [0.05, 0.75],
    [0.4, 0.7], [0.75, 0.8], [0.25, 0.97], [0.95, 0.95]];
  const WEIGHTS = [3, 1, 2, 1, 2, 5, 1, 1, 3, 2, 1, 4];
  const SITES = [[0.2, 0.2], [0.6, 0.15], [0.9, 0.3], [0.3, 0.55], [0.65, 0.6], [0.1, 0.9], [0.55, 0.9], [0.85, 0.75]];
  const COSTS = [120, 90, 150, 60, 200, 80, 110, 130];
  function syntheticDemo(bbox, category) {
    return {
      label: LABEL, synthetic: true,
      control_points: PTS.map(([u, v], i) => { const [lon, lat] = at(bbox, u, v); return { id: `cp-${i + 1}`, lon, lat, weight: WEIGHTS[i] }; }),
      candidates: SITES.map(([u, v], i) => { const [lon, lat] = at(bbox, u, v); return { id: `site-${i + 1}`, lon, lat, category, kind: "hypothetical", cost: COSTS[i] }; }),
      // chosen so that in 3 of the 4 city/category slices the strategies differ and in one they coincide (both cases shown)
      budget: 150, max_selected: 2, coverage_radius_m: 300, required_ids: [], excluded_ids: [], selected_ids: [],
    };
  }
  const api = { LABEL, syntheticDemo };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN_DEMO = api;
})(typeof window !== "undefined" ? window : globalThis);
