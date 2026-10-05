// K12 round 8, stage 3: limit checks run in a CHILD process so that a freeze is observable (the parent kills it on timeout).
//   node limits_child.cjs <app-root> <adapter>   -> prints one JSON line
// Over-limit plans must be refused BEFORE enumeration: import of 17/24/40 candidates is rejected, and (if the adapter
// exposes optimizeUnchecked) a direct optimisation call with 20/30 candidates returns status "too_large" with 0 evaluated.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const [APP, ADAPTER] = process.argv.slice(2);
const WEB = path.join(APP, "web");
const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(WEB, f), "utf8"), ctx, { filename: f });
const A = require(path.resolve(ADAPTER))({ appRoot: APP, D: ctx.CITY_EVIDENCE, EV: ctx.CITY_OBS, ctx, requireWeb: (n) => require(path.join(WEB, n)) });
const bb = ctx.CITY_EVIDENCE.cities.shymkent.bbox;
function scenario(nc, np = 25) {
  const at = (k, m) => [+(bb[0] + 0.001 + (k % 7) * (bb[2] - bb[0] - 0.002) / 6).toFixed(6), +(bb[1] + 0.001 + Math.floor(k / 7) * (bb[3] - bb[1] - 0.002) / Math.max(1, Math.ceil(m / 7))).toFixed(6)];
  return { schema_version: "city-plan-v2", city_id: "shymkent", source_snapshot: A.snapshot("shymkent"), category: "school",
    control_points: Array.from({ length: np }, (_, k) => ({ id: `cp${k}`, lon: at(k, np)[0], lat: at(k, np)[1], weight: 1 })),
    candidates: Array.from({ length: nc }, (_, k) => ({ id: `c${k}`, lon: at(k, nc)[0], lat: at(k, nc)[1], category: "school", kind: "hypothetical", cost: 1 })),
    budget: 1000000, max_selected: 5, coverage_radius_m: 500, required_ids: [], excluded_ids: [], selected_ids: [] };
}
const out = { import: {}, unchecked: {} };
for (const n of [16, 17, 24, 40]) {
  const t0 = process.hrtime.bigint();
  const r = A.importScenario(JSON.stringify(scenario(n)), A.initialState());
  out.import[n] = { ok: !!r.ok, code: r.code || null, ms: Number(process.hrtime.bigint() - t0) / 1e6 };
}
if (typeof A.optimizeUnchecked === "function") {
  for (const n of [20, 30]) {
    const t0 = process.hrtime.bigint();
    const r = A.optimizeUnchecked(scenario(n));
    out.unchecked[n] = { status: r.status, evaluated: r.evaluated, ms: Number(process.hrtime.bigint() - t0) / 1e6 };
  }
} else out.unchecked = null;
process.stdout.write(JSON.stringify(out) + "\n");
