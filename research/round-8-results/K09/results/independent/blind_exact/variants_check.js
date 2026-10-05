'use strict';
// Sensitivity check: do alternative haversine formulations change any mm value?
const fs = require('fs');
const R = 6371008.8;
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const V = {
  asin_floor: (a1, b1, a2, b2) => { const r = Math.PI/180; const dp=(b2-b1)*r, dl=(a2-a1)*r; let a=Math.sin(dp/2)**2+Math.cos(b1*r)*Math.cos(b2*r)*Math.sin(dl/2)**2; a=Math.min(1,Math.max(0,a)); return Math.floor(2*R*Math.asin(Math.sqrt(a))*1000+0.5); },
  atan2_floor: (a1, b1, a2, b2) => { const r = Math.PI/180; const dp=(b2-b1)*r, dl=(a2-a1)*r; let a=Math.sin(dp/2)**2+Math.cos(b1*r)*Math.cos(b2*r)*Math.sin(dl/2)**2; a=Math.min(1,Math.max(0,a)); return Math.floor(2*R*Math.atan2(Math.sqrt(a),Math.sqrt(1-a))*1000+0.5); },
  asin_round_radsub: (a1, b1, a2, b2) => { const r = x=>x*Math.PI/180; const dp=r(b2)-r(b1), dl=r(a2)-r(a1); let a=Math.sin(dp/2)*Math.sin(dp/2)+Math.cos(r(b1))*Math.cos(r(b2))*Math.sin(dl/2)*Math.sin(dl/2); a=Math.min(1,Math.max(0,a)); return Math.round(R*2*Math.asin(Math.sqrt(a))*1000); },
};
let total = 0, diffs = 0, nearHalf = [];
for (const t of data.tasks) {
  const objs = [...t.context.sources, ...t.scenario.candidates];
  for (const p of t.scenario.control_points) for (const o of objs) {
    total++;
    const vals = Object.values(V).map(f => f(p.lon, p.lat, o.lon, o.lat));
    if (new Set(vals).size > 1) { diffs++; console.log('DIFF', t.task_id, p.id, o.id, vals); }
    const r = Math.PI/180; const dp=(o.lat-p.lat)*r, dl=(o.lon-p.lon)*r; let a=Math.sin(dp/2)**2+Math.cos(p.lat*r)*Math.cos(o.lat*r)*Math.sin(dl/2)**2;
    const x = 2*R*Math.asin(Math.sqrt(Math.min(1,Math.max(0,a))))*1000;
    const f = x - Math.floor(x);
    if (Math.abs(f - 0.5) < 1e-4) nearHalf.push([t.task_id, p.id, o.id, x]);
  }
}
console.log('pairs', total, 'formulation diffs', diffs, 'near-.5 (<1e-4 mm)', nearHalf.length);
for (const n of nearHalf) console.log('NEAR', n);
