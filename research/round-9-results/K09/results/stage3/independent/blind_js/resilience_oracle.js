'use strict';
// Independent blind implementation of city-resilience-v1 exact optimizer.
// Written from research/round-9/CORE_SPEC.txt + research/round-8/CORE_SPEC.txt (commit 0ab1667)
// and the conventions given in the verifier task. No npm packages.
//
// Usage: node resilience_oracle.js <envelopes.jsonl> <contexts.json> <out.jsonl> [--haversine=asin|atan2]

const fs = require('fs');

const R = 6371008.8;
const argv = process.argv.slice(2);
const opts = { haversine: 'atan2' };
const pos = [];
for (const a of argv) {
  if (a.startsWith('--haversine=')) opts.haversine = a.slice('--haversine='.length);
  else pos.push(a);
}
const [envPath, ctxPath, outPath] = pos;
if (!envPath || !ctxPath || !outPath) {
  console.error('usage: node resilience_oracle.js <envelopes.jsonl> <contexts.json> <out.jsonl> [--haversine=asin|atan2]');
  process.exit(2);
}

function toRad(deg) { return deg * Math.PI / 180; }

// haversine on [lon,lat] degrees; clamp intermediate a into [0,1]; one rounding to mm.
function distMm(lon1, lat1, lon2, lat2) {
  const phi1 = toRad(lat1), phi2 = toRad(lat2);
  const dphi = toRad(lat2 - lat1);
  const dl = toRad(lon2 - lon1);
  const s1 = Math.sin(dphi / 2), s2 = Math.sin(dl / 2);
  let a = s1 * s1 + Math.cos(phi1) * Math.cos(phi2) * s2 * s2;
  if (a < 0) a = 0; else if (a > 1) a = 1;
  let c;
  if (opts.haversine === 'asin') c = 2 * Math.asin(Math.sqrt(a));
  else c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const d = R * c;
  return Math.floor(d * 1000 + 0.5);
}

// Code-point string compare (not UTF-16 unit compare).
function cpCmp(a, b) {
  const A = Array.from(a), B = Array.from(b);
  const n = Math.min(A.length, B.length);
  for (let i = 0; i < n; i++) {
    const x = A[i].codePointAt(0), y = B[i].codePointAt(0);
    if (x !== y) return x < y ? -1 : 1;
  }
  return A.length === B.length ? 0 : (A.length < B.length ? -1 : 1);
}
function idsCmp(a, b) { // element-wise, shorter prefix first
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) { const c = cpCmp(a[i], b[i]); if (c) return c; }
  return a.length === b.length ? 0 : (a.length < b.length ? -1 : 1);
}
function numCmp(x, y) { return x < y ? -1 : (x > y ? 1 : 0); }
// L = {u, s, m}; m = Infinity internally when any unknown (or no points known)
function lCmp(a, b) {
  return numCmp(a.u, b.u) || numCmp(a.s, b.s) || numCmp(a.m, b.m);
}
function lOut(l) {
  return { unknown_count: l.u, weighted_sum_mm: l.s, max_mm: l.m === Infinity ? null : l.m };
}

function solve(task, ctx) {
  const env = task.envelope;
  const plan = env.plan;
  const pts = plan.control_points;
  const cands = plan.candidates;
  const P = pts.length, C = cands.length;
  if (C > 12) return { status: 'too_many_candidates' };

  const sources = ctx.sources;
  const srcIds = new Set(sources.map(s => s.id));
  // Cases: base first, then user cases.
  const cases = [{ id: 'base', disabled_source_ids: [] }].concat(env.cases.map(c => ({ id: c.id, disabled_source_ids: c.disabled_source_ids })));
  for (const c of env.cases) {
    if (c.id === 'base') return { status: 'invalid', reason: 'reserved_case_id' };
    for (const d of c.disabled_source_ids) if (!srcIds.has(d)) return { status: 'invalid', reason: 'unknown_source_id:' + d };
  }
  const K = cases.length;

  // Precompute source distances per point (mm), then case baseline per point.
  const srcD = sources.map(s => pts.map(p => distMm(p.lon, p.lat, s.lon, s.lat)));
  const caseBase = []; // caseBase[k][i] = min mm over enabled sources or Infinity
  for (const cs of cases) {
    const dis = new Set(cs.disabled_source_ids);
    const row = new Array(P).fill(Infinity);
    for (let j = 0; j < sources.length; j++) {
      if (dis.has(sources[j].id)) continue;
      for (let i = 0; i < P; i++) if (srcD[j][i] < row[i]) row[i] = srcD[j][i];
    }
    caseBase.push(row);
  }
  const candD = cands.map(c => pts.map(p => distMm(p.lon, p.lat, c.lon, c.lat)));
  const weights = pts.map(p => p.weight);
  const totalW = weights.reduce((a, b) => a + b, 0);

  const idIndex = new Map(cands.map((c, i) => [c.id, i]));
  const req = plan.required_ids || [], exc = plan.excluded_ids || [];
  let reqMask = 0, excMask = 0, reqCost = 0;
  for (const id of req) { const i = idIndex.get(id); if (i === undefined) return { status: 'invalid', reason: 'unknown_required' }; reqMask |= (1 << i); reqCost += cands[i].cost; }
  for (const id of exc) { const i = idIndex.get(id); if (i === undefined) return { status: 'invalid', reason: 'unknown_excluded' }; excMask |= (1 << i); }
  if (reqMask & excMask) return { status: 'invalid', reason: 'required_excluded_overlap' };
  if (req.length > plan.max_selected || reqCost > plan.budget) {
    return { status: 'infeasible', nominal: null, robust: null, same_plan: null, price_of_robustness_m: null, feasible_count: 0 };
  }

  function evalMask(mask) {
    // per-point candidate min
    const cmin = new Array(P).fill(Infinity);
    for (let j = 0; j < C; j++) {
      if (!(mask & (1 << j))) continue;
      const row = candD[j];
      for (let i = 0; i < P; i++) if (row[i] < cmin[i]) cmin[i] = row[i];
    }
    const Ls = [];
    for (let k = 0; k < K; k++) {
      const b = caseBase[k];
      let u = 0, s = 0, m = -Infinity;
      for (let i = 0; i < P; i++) {
        const d = b[i] < cmin[i] ? b[i] : cmin[i];
        if (d === Infinity) { u++; continue; }
        s += weights[i] * d;
        if (d > m) m = d;
      }
      if (u > 0) m = Infinity;
      if (m === -Infinity) m = Infinity; // P>=1 so only reachable when u>0
      Ls.push({ u, s, m });
    }
    let W = Ls[0];
    for (let k = 1; k < K; k++) if (lCmp(Ls[k], W) > 0) W = Ls[k];
    const worst = [];
    for (let k = 0; k < K; k++) if (lCmp(Ls[k], W) === 0) worst.push(cases[k].id);
    worst.sort(cpCmp);
    return { Ls, W, worst, base: Ls[0] };
  }

  let feasible = 0;
  let nom = null, rob = null;
  for (let mask = 0; mask < (1 << C); mask++) {
    if ((mask & reqMask) !== reqMask) continue;
    if (mask & excMask) continue;
    let cnt = 0, cost = 0;
    const ids = [];
    for (let j = 0; j < C; j++) if (mask & (1 << j)) { cnt++; cost += cands[j].cost; ids.push(cands[j].id); }
    if (cnt > plan.max_selected || cost > plan.budget) continue;
    feasible++;
    ids.sort(cpCmp);
    const ev = evalMask(mask);
    const rec = { mask, ids, cost, ev };
    if (nom === null) nom = rec;
    else {
      const c = lCmp(rec.ev.base, nom.ev.base) || numCmp(rec.cost, nom.cost) || idsCmp(rec.ids, nom.ids);
      if (c < 0) nom = rec;
    }
    if (rob === null) rob = rec;
    else {
      const c = lCmp(rec.ev.W, rob.ev.W) || lCmp(rec.ev.base, rob.ev.base) || numCmp(rec.cost, rob.cost) || idsCmp(rec.ids, rob.ids);
      if (c < 0) rob = rec;
    }
  }
  if (feasible === 0) {
    return { status: 'infeasible', nominal: null, robust: null, same_plan: null, price_of_robustness_m: null, feasible_count: 0 };
  }
  function planOut(r) {
    return { ids: r.ids, W: lOut(r.ev.W), worst_case_ids: r.ev.worst, base: lOut(r.ev.base) };
  }
  let price = null;
  if (nom.ev.base.u === 0 && rob.ev.base.u === 0) {
    const meanR = rob.ev.base.s / totalW;
    const meanN = nom.ev.base.s / totalW;
    price = (meanR - meanN) / 1000;
  }
  return {
    status: 'optimal',
    nominal: planOut(nom),
    robust: planOut(rob),
    same_plan: idsCmp(nom.ids, rob.ids) === 0,
    price_of_robustness_m: price,
    feasible_count: feasible,
  };
}

const contexts = JSON.parse(fs.readFileSync(ctxPath, 'utf8'));
const lines = fs.readFileSync(envPath, 'utf8').split('\n').filter(l => l.trim().length > 0);
const out = [];
for (const line of lines) {
  const task = JSON.parse(line);
  const ctx = contexts[task.slice];
  let res;
  if (!ctx) res = { status: 'invalid', reason: 'unknown_slice' };
  else if (ctx.city_id !== task.envelope.plan.city_id || ctx.category !== task.envelope.plan.category || ctx.source_snapshot !== task.envelope.plan.source_snapshot) res = { status: 'invalid', reason: 'context_mismatch' };
  else res = solve(task, ctx);
  const rec = Object.assign({ task_key: task.task_key }, res);
  if (!('nominal' in rec)) Object.assign(rec, { nominal: null, robust: null, same_plan: null, price_of_robustness_m: null, feasible_count: 0 });
  out.push(JSON.stringify({
    task_key: rec.task_key, status: rec.status, nominal: rec.nominal, robust: rec.robust,
    same_plan: rec.same_plan, price_of_robustness_m: rec.price_of_robustness_m, feasible_count: rec.feasible_count,
    ...(rec.reason ? { reason: rec.reason } : {}),
  }));
}
fs.writeFileSync(outPath, out.join('\n') + '\n');
console.error('wrote ' + out.length + ' lines to ' + outPath);
