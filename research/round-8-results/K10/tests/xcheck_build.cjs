// K10 round 8: IEEE cross-check of pack geometry with the BUILD's own JS (web/whatif.js haversine + sourceSnapshot,
// records from web/data.js). It does NOT test a city-plan-v2 implementation; it checks that the oracle's millimetre
// distances and snapshot equal what the BUILD's JavaScript computes from the same data.
// Usage: node xcheck_build.cjs <app-root> <pack.json> ...  -> JSON {pack_id: {snapshot, base: [[mm,id]|null], cand: [[mm]]}}
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const [appRoot, ...packs] = process.argv.slice(2);
const W = path.join(path.resolve(appRoot), "web");
const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx, { filename: f });
const F = require(path.join(W, "facts.js"));
const X = require(path.join(W, "whatif.js"));
const D = ctx.CITY_EVIDENCE;
const mm = (d) => Math.round(d * 1000);
const out = {};
for (const file of packs) {
  const p = JSON.parse(fs.readFileSync(file, "utf8"));
  if (p.kind !== "real_slice") continue;
  const sc = p.scenario, city = D.cities[sc.city_id];
  const pool = city.places.filter((r) => r.group === sc.category);
  const base = sc.control_points.map((cp) => {
    let best = null;
    for (const r of pool) {
      const k = [mm(X.haversine(cp.lon, cp.lat, r.lon, r.lat)), r.id];
      if (!best || k[0] < best[0] || (k[0] === best[0] && k[1] < best[1])) best = k;
    }
    return best;
  });
  const cand = sc.control_points.map((cp) => sc.candidates.map((c) => mm(X.haversine(cp.lon, cp.lat, c.lon, c.lat))));
  const raw = sc.control_points.map((cp) => sc.candidates.map((c) => X.haversine(cp.lon, cp.lat, c.lon, c.lat)));
  out[p.pack_id] = { snapshot: X.sourceSnapshot(D, sc.city_id, F), base, cand, raw };
}
process.stdout.write(JSON.stringify(out));
