'use strict';
// Blind greedy heuristics G1 / G2 for city-plan-v2, written from the task text only.
const fs = require('fs');
const path = require('path');

const IN = process.argv[2] || '/tmp/claude-0/-home-user-GOV-DIPLOME/e220e412-94a1-5250-b65e-0d50545b9515/scratchpad/blind_in/inputs.json';
const OUT = process.argv[3] || path.join(__dirname, 'out.json');

const R = 6371008.8;
const RAD = Math.PI / 180;

function haversineM(lon1, lat1, lon2, lat2) {
  const p1 = lat1 * RAD, p2 = lat2 * RAD;
  const dp = (lat2 - lat1) * RAD;
  const dl = (lon2 - lon1) * RAD;
  const s1 = Math.sin(dp / 2), s2 = Math.sin(dl / 2);
  let a = s1 * s1 + Math.cos(p1) * Math.cos(p2) * s2 * s2;
  if (a < 0) a = 0;
  if (a > 1) a = 1;
  return 2 * R * Math.asin(Math.sqrt(a));
}
function distMm(lon1, lat1, lon2, lat2) {
  return Math.floor(haversineM(lon1, lat1, lon2, lat2) * 1000 + 0.5);
}

// code-point string comparison
function cmpStr(a, b) {
  if (a === b) return 0;
  const A = Array.from(a), B = Array.from(b);
  const n = Math.min(A.length, B.length);
  for (let i = 0; i < n; i++) {
    const x = A[i].codePointAt(0), y = B[i].codePointAt(0);
    if (x !== y) return x < y ? -1 : 1;
  }
  return A.length === B.length ? 0 : (A.length < B.length ? -1 : 1);
}
function cmpIds(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const c = cmpStr(a[i], b[i]);
    if (c !== 0) return c;
  }
  return a.length === b.length ? 0 : (a.length < b.length ? -1 : 1);
}
function cmpNum(a, b) { return a < b ? -1 : (a > b ? 1 : 0); }
function cmpKey(k1, k2) {
  for (let i = 0; i < k1.length; i++) {
    const c = Array.isArray(k1[i]) ? cmpIds(k1[i], k2[i]) : cmpNum(k1[i], k2[i]);
    if (c !== 0) return c;
  }
  return 0;
}

function buildProblem(task) {
  const ctx = task.context, sc = task.scenario;
  const pts = sc.control_points;
  const cands = sc.candidates.slice().sort((a, b) => cmpStr(a.id, b.id));
  const byId = new Map(cands.map(c => [c.id, c]));
  // baseline nearest mm per point
  const base = pts.map(p => {
    let best = null;
    for (const s of ctx.sources) {
      const d = distMm(p.lon, p.lat, s.lon, s.lat);
      if (best === null || d < best) best = d;
    }
    return best;
  });
  // candidate distance matrix: candMm[id][pointIndex]
  const candMm = new Map();
  for (const c of cands) candMm.set(c.id, pts.map(p => distMm(p.lon, p.lat, c.lon, c.lat)));
  return {
    pts, cands, byId, base, candMm,
    budget: sc.budget, maxSel: sc.max_selected, radiusMm: sc.coverage_radius_m * 1000,
    required: sc.required_ids.slice().sort(cmpStr),
    excluded: new Set(sc.excluded_ids),
  };
}

function metrics(P, ids) {
  let unknown = 0, wsum = 0, max = -1, covered = 0, cost = 0;
  for (const id of ids) cost += P.byId.get(id).cost;
  const rows = ids.map(id => P.candMm.get(id));
  for (let i = 0; i < P.pts.length; i++) {
    let a = P.base[i];
    for (const r of rows) if (a === null || r[i] < a) a = r[i];
    if (a === null) { unknown++; continue; }
    const w = P.pts[i].weight;
    wsum += w * a;
    if (a > max) max = a;
    if (a <= P.radiusMm) covered += w;
  }
  const maxMm = unknown === 0 ? max : null;
  return { unknown, wsum, maxMm, covered, cost, ids: ids.slice().sort(cmpStr) };
}

function key(obj, m) {
  const mx = m.maxMm === null ? Infinity : m.maxMm;
  if (obj === 'mean') return [m.unknown, m.wsum, mx, m.cost, m.ids];
  if (obj === 'minimax') return [m.unknown, mx, m.wsum, m.cost, m.ids];
  if (obj === 'coverage') return [-m.covered, m.unknown, m.wsum, mx, m.cost, m.ids];
  throw new Error('bad objective ' + obj);
}

function costOf(P, ids) { let s = 0; for (const id of ids) s += P.byId.get(id).cost; return s; }

function infeasible(P) {
  return P.required.length > P.maxSel || costOf(P, P.required) > P.budget;
}

function addable(P, S) {
  const inS = new Set(S);
  const cS = costOf(P, S);
  return P.cands.filter(c => !inS.has(c.id) && !P.excluded.has(c.id) && cS + c.cost <= P.budget);
}

function G1(P, obj) {
  if (infeasible(P)) return null;
  let S = P.required.slice();
  while (S.length < P.maxSel) {
    const kS = key(obj, metrics(P, S));
    let best = null, bestKey = null;
    for (const c of addable(P, S)) {
      const k = key(obj, metrics(P, S.concat([c.id])));
      if (bestKey === null || cmpKey(k, bestKey) < 0) { best = c; bestKey = k; }
    }
    if (best === null || cmpKey(bestKey, kS) >= 0) break;
    S.push(best.id);
  }
  return S.slice().sort(cmpStr);
}

// primary metric (bigger is better), returns BigInt or undefined
function primary(obj, m) {
  if (obj === 'mean') return -BigInt(m.wsum);
  if (obj === 'minimax') return m.maxMm === null ? undefined : -BigInt(m.maxMm);
  if (obj === 'coverage') return BigInt(m.covered);
  throw new Error('bad objective');
}

function bestSingle(P, obj) {
  // among c not in required, not excluded, cost(required)+cost(c) <= budget
  const req = new Set(P.required);
  const cR = costOf(P, P.required);
  let bestIds = null, bestKey = null;
  for (const c of P.cands) {
    if (req.has(c.id) || P.excluded.has(c.id) || cR + c.cost > P.budget) continue;
    const ids = P.required.concat([c.id]);
    const k = key(obj, metrics(P, ids));
    if (bestKey === null || cmpKey(k, bestKey) < 0) { bestIds = ids; bestKey = k; }
  }
  return bestIds === null ? null : { ids: bestIds, key: bestKey };
}

function G2(P, obj) {
  if (infeasible(P)) return null;
  let S = P.required.slice();
  while (S.length < P.maxSel) {
    const mS = metrics(P, S);
    const adds = addable(P, S);
    let pick = null;
    // phase 1: reduce unknowns
    let bestT = null;
    for (const c of adds) {
      const mC = metrics(P, S.concat([c.id]));
      const du = mS.unknown - mC.unknown;
      if (du > 0) {
        const t = [-du, c.cost, [c.id]];
        if (bestT === null || cmpKey(t, bestT) < 0) { bestT = t; pick = c; }
      }
    }
    if (pick === null) {
      const pS = primary(obj, mS);
      let bestG = null, bestC = null;
      for (const c of adds) {
        const mC = metrics(P, S.concat([c.id]));
        const pC = primary(obj, mC);
        if (pS === undefined || pC === undefined) continue;
        const gain = pC - pS;
        if (gain <= 0n) continue;
        const cc = BigInt(c.cost);
        // gain/cc > bestG/bestC  <=> gain*bestC > bestG*cc
        if (bestG === null || gain * bestC > bestG * cc) { bestG = gain; bestC = cc; pick = c; }
      }
    }
    if (pick === null) break;
    S.push(pick.id);
  }
  if (P.required.length < P.maxSel) {
    const bs = bestSingle(P, obj);
    if (bs !== null) {
      const kS = key(obj, metrics(P, S));
      if (cmpKey(bs.key, kS) < 0) return bs.ids.slice().sort(cmpStr);
    }
  }
  return S.slice().sort(cmpStr);
}

const OBJS = ['mean', 'minimax', 'coverage'];
const input = JSON.parse(fs.readFileSync(IN, 'utf8'));
const out = {};
const diag = {};
for (const task of input.tasks) {
  const P = buildProblem(task);
  const r = { G1: {}, G2: {} };
  for (const o of OBJS) {
    r.G1[o] = G1(P, o);
    r.G2[o] = G2(P, o);
    // sanity: best-single post-step would never change G1
    if (r.G1[o] !== null && P.required.length < P.maxSel) {
      const bs = bestSingle(P, o);
      if (bs && cmpKey(bs.key, key(o, metrics(P, r.G1[o]))) < 0) {
        (diag[task.task_id] = diag[task.task_id] || []).push('G1 ' + o + ' would be improved by best-single');
      }
    }
  }
  out[task.task_id] = r;
}
fs.writeFileSync(OUT, JSON.stringify(out, null, 1) + '\n');
console.log('tasks', Object.keys(out).length, 'written', OUT);
console.log('G1 best-single diagnostics:', JSON.stringify(diag));
