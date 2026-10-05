/* Бенчмарк максимального размера: 16 кандидатов, 25 точек, max_selected=5, бюджет 1e6 (SYNTHETIC кандидаты/веса/стоимости).
 *   node tests/bench.cjs --app-root <checkout>/prototypes/city-evidence [--json OUT] [--repeat 5]
 */
"use strict";
const fs = require("node:fs");
const os = require("node:os");
const H = require("./helpers.cjs");
const { PL } = H;
const APP = H.arg("--app-root");
if (!APP) { console.error("нужен --app-root"); process.exit(2); }
const REP = Number(H.arg("--repeat", "5"));
const B = H.loadBuild(APP);
const now = () => Number(process.hrtime.bigint()) / 1e6;

async function main() {
  const rows = [];
  for (const city of ["shymkent", "astana"]) for (const cat of ["school", "outpatient_clinic"]) {
    const ctx = H.buildContext(B, city);
    const v = PL.validatePlanScenario(H.syntheticScenario(ctx, cat, { seed: 2026, nPoints: 25, nCand: 16, budget: 1000000, maxSel: 5, radius: 500 }), ctx);
    const s = v.scenario;
    const sync = [], syncNoSens = [];
    let res;
    for (let i = 0; i < REP; i++) { const t0 = now(); res = PL.optimizePlans(ctx, s); sync.push(now() - t0); }
    for (let i = 0; i < REP; i++) { const t0 = now(); PL.optimizePlans(ctx, s, { sensitivity: false }); syncNoSens.push(now() - t0); }
    // async: максимум длительности одного чанка — оценка «заморозки» UI
    let last = now(), maxGap = 0;
    const t0 = now();
    const ar = await PL.optimizePlansAsync(ctx, s, { chunk: 2048, onProgress: () => { const x = now(); maxGap = Math.max(maxGap, x - last); last = x; } });
    const asyncTotal = now() - t0;
    const med = (a) => a.slice().sort((x, y) => x - y)[Math.floor(a.length / 2)];
    rows.push({ city, category: cat, candidates: 16, control_points: 25, max_selected: 5, total_masks: res.total,
      feasible_count: res.feasible_count, status: res.status, haversine_calls: res.haversine_calls,
      sync_ms_median_with_sensitivity: +med(sync).toFixed(1), sync_ms_median_no_sensitivity: +med(syncNoSens).toFixed(1),
      async_total_ms: +asyncTotal.toFixed(1), async_max_chunk_ms_2048: +maxGap.toFixed(2), async_status: ar.status,
      async_equals_sync: JSON.stringify(ar) === JSON.stringify(res) });
  }
  const out = { node: process.version, cpu: (os.cpus()[0] || {}).model, cores: os.cpus().length, repeat: REP, rows,
    note: "SYNTHETIC кандидаты/стоимости/веса на реальных срезах сборки; время зависит от машины" };
  console.log(JSON.stringify(out, null, 1));
  const j = H.arg("--json");
  if (j) fs.writeFileSync(j, JSON.stringify(out, null, 1) + "\n");
}
main();
