// K10 round 8: IEEE cross-check of pack geometry with the BUILD's own JS (web/whatif.js haversine, facts.js sha256hex and
// placesDigest, web/plan.js sourceSnapshot when present, records from web/data.js). It does NOT test a city-plan-v2 implementation; it checks that the oracle's millimetre
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
let PL = null;  // web/plan.js exists from BUILD 97405ef on; older builds are checked through the same formula via facts.js
if (fs.existsSync(path.join(W, "plan.js"))) PL = require(path.join(W, "plan.js"));
function planSnapshot(city) {  // the plan-v2 formula written out with the BUILD's own sha256hex and placesDigest
  const c = D.cities[city], fsha = c.files && c.files.places_social && c.files.places_social.sha256;
  return "sha256:" + F.sha256hex(JSON.stringify(["city-plan-v2", city, c.release, fsha || null, F.placesDigest(D, city), "haversine-mm-v1"]));
}
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
  out[p.pack_id] = { snapshot: planSnapshot(sc.city_id), plan_js_snapshot: PL ? PL.sourceSnapshot(D, sc.city_id, F) : null,
    whatif_v1_snapshot: X.sourceSnapshot(D, sc.city_id, F), base, cand, raw };
}
process.stdout.write(JSON.stringify(out));
