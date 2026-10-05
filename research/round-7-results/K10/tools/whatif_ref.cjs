// K10 round 7: JS port of whatif_ref.py (same formula and tie rules) for cross-checking IEEE results.
// Usage: node whatif_ref.cjs <fixture.json> ...   -> prints JSON {fixture_id: [{step, rows:[...]}]}
"use strict";
const fs = require("fs");
const R = 6371008.8;
function hav(a, b) {
  const p1 = (a[1] * Math.PI) / 180, p2 = (b[1] * Math.PI) / 180;
  const dp = p2 - p1, dl = ((b[0] - a[0]) * Math.PI) / 180;
  let h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  h = Math.min(1, Math.max(0, h));
  return 2 * R * Math.asin(Math.sqrt(h));
}
function compute(sc, recs) {
  const pool = recs.filter((r) => r.group === sc.category), prop = sc.proposed_object;
  return sc.control_points.map((cp) => {
    let best = null;
    for (const r of pool) {
      const d = hav([cp.lon, cp.lat], [r.lon, r.lat]);
      if (!best || d < best[0] || (d === best[0] && r.id < best[1].id)) best = [d, r];
    }
    const before = best ? best[0] : null, dp = prop ? hav([cp.lon, cp.lat], [prop.lon, prop.lat]) : null;
    let after, delta;
    if (before === null) { after = dp; delta = null; } else if (dp === null) { after = before; delta = 0; }
    else { after = Math.min(before, dp); delta = before - after; }
    return { control_point_id: cp.id, before_m: before, nearest_before_id: best ? best[1].id : null, after_m: after, delta_m: delta };
  });
}
const out = {};
for (const f of process.argv.slice(2)) {
  const fx = JSON.parse(fs.readFileSync(f, "utf8"));
  if (!fx.steps || !fx.steps[0].expected.rows) continue;
  const recs = fx.synthetic_slice ? fx.synthetic_slice.records : fx.source_copy.category_records;
  out[fx.fixture_id] = fx.steps.map((s) => ({ step: s.step, rows: compute(s.scenario, recs) }));
}
process.stdout.write(JSON.stringify(out));
