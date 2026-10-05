/* Пишет набор задач и ответов plan.js для Python-оракула.
 *   node tests/dump_cases.cjs --app-root <checkout>/prototypes/city-evidence --out runs/cases_dump.json
 * Реальные срезы сборки (записи observed_secondary) + SYNTHETIC кандидаты/веса/стоимости; плюс чисто синтетические краевые.
 */
"use strict";
const fs = require("node:fs");
const H = require("./helpers.cjs");
const { PL } = H;
const APP = H.arg("--app-root"), OUT = H.arg("--out");
if (!APP || !OUT) { console.error("нужны --app-root и --out"); process.exit(2); }
const B = H.loadBuild(APP);
const cases = [];
const add = (name, ctx, raw) => {
  const v = PL.validatePlanScenario(raw, ctx);
  if (!v.ok) throw new Error(name + ": " + JSON.stringify(v.error));
  const result = PL.optimizePlans(ctx, v.scenario);
  cases.push({ name, context: { city_id: ctx.city_id, bbox: ctx.bbox, source_snapshot: ctx.source_snapshot, records: ctx.records },
    scenario: v.scenario, result: JSON.parse(PL.toStrictJSON(result)) });
};
let n = 0;
for (const city of ["shymkent", "astana"]) {
  const ctx = H.buildContext(B, city);
  for (const cat of ["school", "outpatient_clinic"]) {
    for (let seed = 1; seed <= 6; seed++) {
      const nCand = [0, 1, 5, 9, 12, 16][seed - 1];
      const req = seed === 4 ? ["syn_c03"] : seed === 5 ? ["syn_c00", "syn_c07"] : [];
      const exc = seed === 4 ? ["syn_c01", "syn_c05"] : seed === 6 ? ["syn_c15"] : [];
      add(`${city}/${cat}/seed${seed}/n${nCand}`, ctx, H.syntheticScenario(ctx, cat, { seed: 1000 + seed * 7 + n++, nPoints: 3 + seed * 4 > 25 ? 25 : 3 + seed * 4,
        nCand, budget: [0, 100, 250, 400, 700, 1000][seed - 1], maxSel: Math.min(5, seed - 1), radius: [100, 250, 500, 800, 1500, 5000][seed - 1],
        required: req, excluded: exc }));
    }
  }
}
// пустой baseline (synthetic контекст без записей категории)
const empty = { city_id: "astana", bbox: [71.418372, 51.163033, 71.447, 51.181], source_snapshot: "SYNTHETIC-empty", records: [] };
add("synthetic/empty-baseline", empty, H.syntheticScenario(empty, "school", { seed: 77, nPoints: 6, nCand: 6, budget: 300, maxSel: 2 }));
// ничьи: кандидаты в одной точке
const tie = { city_id: "shymkent", bbox: [69.593365, 42.306645, 69.617658, 42.324611], source_snapshot: "SYNTHETIC-tie",
  records: [{ id: "src", lon: 69.60, lat: 42.31, group: "school" }] };
const ts = H.syntheticScenario(tie, "school", { seed: 5, nPoints: 5, nCand: 6, budget: 1000, maxSel: 2 });
ts.candidates.forEach((c) => { c.lon = 69.605; c.lat = 42.315; c.cost = 100; });
add("synthetic/all-candidates-same-point", tie, ts);
// infeasible: required дороже бюджета и больше max_selected (synthetic кандидаты на реальном срезе)
{
  const ctx = H.buildContext(B, "shymkent");
  const s1 = H.syntheticScenario(ctx, "school", { seed: 9, nPoints: 5, nCand: 6, budget: 60, maxSel: 3, required: ["syn_c00", "syn_c01"] });
  add("shymkent/school/infeasible-budget", ctx, s1);
  const s2 = H.syntheticScenario(ctx, "outpatient_clinic", { seed: 10, nPoints: 5, nCand: 6, budget: 1000, maxSel: 1, required: ["syn_c00", "syn_c01"] });
  add("shymkent/outpatient_clinic/infeasible-count", ctx, s2);
}
fs.writeFileSync(OUT, JSON.stringify(cases) + "\n");
console.log(`${cases.length} задач → ${OUT}`);
