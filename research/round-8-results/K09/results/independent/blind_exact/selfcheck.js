'use strict';
// Second, structurally different enumeration (recursive combinations + full sort) to cross-check out.json.
const fs = require('fs');
const { distMm } = require('./exact.js');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const INF = Number.POSITIVE_INFINITY;
function lexIds(a, b) { // ASCII ids here; also verify via localeCompare-free code
  for (let i = 0; i < Math.min(a.length, b.length); i++) { if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; }
  return a.length - b.length;
}
function solve(t, budget) {
  const sc = t.scenario, ctx = t.context;
  const C = [...sc.candidates].sort((x, y) => (x.id < y.id ? -1 : 1));
  const req = new Set(sc.required_ids), exc = new Set(sc.excluded_ids);
  if (req.size > sc.max_selected) return { status: 'infeasible', reason: 'required_count_exceeds_max_selected', fc: 0 };
  if (C.filter(c => req.has(c.id)).reduce((s, c) => s + c.cost, 0) > budget) return { status: 'infeasible', reason: 'required_cost_exceeds_budget', fc: 0 };
  const plans = [];
  const rec = (i, chosen) => {
    if (i === C.length) {
      const cost = chosen.reduce((s, c) => s + c.cost, 0);
      if (chosen.length > sc.max_selected || cost > budget) return;
      if ([...req].some(r => !chosen.some(c => c.id === r))) return;
      let u = 0, ws = 0, mx = 0, cw = 0;
      for (const p of sc.control_points) {
        const ds = [...ctx.sources, ...chosen].map(o => distMm(p.lon, p.lat, o.lon, o.lat));
        if (!ds.length) { u++; continue; }
        const d = Math.min(...ds);
        ws += p.weight * d; mx = Math.max(mx, d); if (d <= sc.coverage_radius_m * 1000) cw += p.weight;
      }
      plans.push({ ids: chosen.map(c => c.id), cost, u, ws, mx: u ? INF : mx, cw });
      return;
    }
    rec(i + 1, chosen);
    if (!exc.has(C[i].id)) rec(i + 1, [...chosen, C[i]]);
  };
  rec(0, []);
  const K = {
    mean: p => [p.u, p.ws, p.mx, p.cost],
    minimax: p => [p.u, p.mx, p.ws, p.cost],
    coverage: p => [-p.cw, p.u, p.ws, p.mx, p.cost],
  };
  const res = { status: 'optimal', fc: plans.length, win: {}, ties: {} };
  for (const [name, f] of Object.entries(K)) {
    const s = [...plans].sort((a, b) => { const ka = f(a), kb = f(b); for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1; return lexIds(a.ids, b.ids); });
    res.win[name] = s[0];
    const k0 = f(s[0]); res.ties[name] = s.filter(p => f(p).every((v, i) => v === k0[i])).length;
    const k0n = name === 'coverage' ? k0.slice(0, 4) : k0.slice(0, 3); // ignoring cost
    res.ties[name + '_nocost'] = s.filter(p => { const k = f(p); return k0n.every((v, i) => v === k[i]); }).length;
  }
  const kn = plans.filter(p => p.u === 0);
  const par = kn.filter(p => !kn.some(q => q.cost <= p.cost && q.ws <= p.ws && (q.cost < p.cost || q.ws < p.ws)));
  const byPair = new Map();
  for (const p of par) { const k = p.cost + ',' + p.ws; if (!byPair.has(k) || lexIds(p.ids, byPair.get(k).ids) < 0) byPair.set(k, p); }
  res.pareto = [...byPair.values()].sort((a, b) => a.cost - b.cost).map(p => ({ cost: p.cost, weighted_sum_mm: p.ws, selected_ids: p.ids }));
  return res;
}
let bad = 0;
for (const t of data.tasks) {
  const o = out[t.task_id];
  const r = solve(t, t.scenario.budget);
  const errs = [];
  if (r.status !== o.status) errs.push('status');
  if (r.fc !== o.feasible_count) errs.push('fc ' + r.fc + ' vs ' + o.feasible_count);
  if (r.status === 'infeasible' && r.reason !== o.reason) errs.push('reason');
  if (r.status === 'optimal') {
    for (const n of ['mean', 'minimax', 'coverage']) {
      const w = r.win[n], e = o.objectives[n];
      if (JSON.stringify(w.ids) !== JSON.stringify(e.selected_ids) || w.ws !== e.weighted_sum_mm || (w.mx === INF ? null : w.mx) !== e.max_mm || w.cw !== e.covered_weight || w.u !== e.unknown_count || w.cost !== e.cost) errs.push('obj ' + n);
    }
    if (JSON.stringify(r.pareto) !== JSON.stringify(o.pareto)) errs.push('pareto');
  }
  const B = t.scenario.budget;
  const bs = [...new Set([0, Math.floor(B / 2), B])].sort((a, b) => a - b);
  if (JSON.stringify(bs) !== JSON.stringify(o.budget_sensitivity.map(s => s.budget))) errs.push('sens budgets');
  bs.forEach((b, i) => { const rr = solve(t, b); const s = o.budget_sensitivity[i];
    if (rr.status !== s.status) errs.push('sens status ' + b);
    for (const n of ['mean', 'minimax', 'coverage']) { const exp = rr.status === 'optimal' ? rr.win[n].ids : null; if (JSON.stringify(exp) !== JSON.stringify(s.objectives[n])) errs.push('sens ' + b + ' ' + n); } });
  if (errs.length) bad++;
  const tieInfo = r.status === 'optimal' ? Object.entries(r.ties).filter(([k, v]) => v > 1).map(([k, v]) => k + '=' + v).join(' ') : '';
  console.log(t.task_id, errs.length ? 'MISMATCH ' + errs.join('; ') : 'ok', tieInfo ? 'ties: ' + tieInfo : '');
}
console.log('mismatching tasks:', bad);
