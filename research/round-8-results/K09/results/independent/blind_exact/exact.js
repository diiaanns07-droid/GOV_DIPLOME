'use strict';
// Independent blind exact optimizer for city-plan-v2 (written from CORE_SPEC text only).
// Usage: node exact.js <inputs.json> <out.json>
const fs = require('fs');

const R = 6371008.8;
const DEG = Math.PI / 180;

function haversineM(lon1, lat1, lon2, lat2) {
  const p1 = lat1 * DEG, p2 = lat2 * DEG;
  const dp = (lat2 - lat1) * DEG;
  const dl = (lon2 - lon1) * DEG;
  const s1 = Math.sin(dp / 2), s2 = Math.sin(dl / 2);
  let a = s1 * s1 + Math.cos(p1) * Math.cos(p2) * s2 * s2;
  if (a < 0) a = 0;
  if (a > 1) a = 1;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function distMm(lon1, lat1, lon2, lat2) {
  const d = haversineM(lon1, lat1, lon2, lat2);
  return Math.floor(d * 1000 + 0.5);
}

// Code-point string comparison (not UTF-16 code unit).
function cmpStr(a, b) {
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
function cmpNum(x, y) { return x < y ? -1 : (x > y ? 1 : 0); }
// Compare key arrays whose last element is the sorted ids array.
function cmpKey(k1, k2) {
  for (let i = 0; i < k1.length - 1; i++) {
    const c = cmpNum(k1[i], k2[i]);
    if (c !== 0) return c;
  }
  return cmpIds(k1[k1.length - 1], k2[k2.length - 1]);
}

function keyOf(obj, m) {
  const mx = m.max_mm === null ? Infinity : m.max_mm;
  if (obj === 'mean') return [m.unknown_count, m.weighted_sum_mm, mx, m.cost, m.ids];
  if (obj === 'minimax') return [m.unknown_count, mx, m.weighted_sum_mm, m.cost, m.ids];
  if (obj === 'coverage') return [-m.covered_weight, m.unknown_count, m.weighted_sum_mm, mx, m.cost, m.ids];
  throw new Error('bad objective');
}

function prepare(task) {
  const ctx = task.context, sc = task.scenario;
  const pts = sc.control_points;
  const cands = sc.candidates;
  // baseline nearest per point (null if no sources)
  const base = pts.map(p => {
    let best = null;
    for (const s of ctx.sources) {
      const d = distMm(p.lon, p.lat, s.lon, s.lat);
      if (best === null || d < best) best = d;
    }
    return best;
  });
  // candidate distance matrix [cand][pt]
  const cd = cands.map(c => pts.map(p => distMm(p.lon, p.lat, c.lon, c.lat)));
  return { pts, cands, base, cd };
}

function evalMask(prep, mask, radiusMm) {
  const { pts, cands, base, cd } = prep;
  let unknown = 0, wsum = 0, mx = -1, covered = 0, cost = 0;
  const ids = [];
  for (let j = 0; j < cands.length; j++) if (mask & (1 << j)) { cost += cands[j].cost; ids.push(cands[j].id); }
  ids.sort(cmpStr);
  for (let i = 0; i < pts.length; i++) {
    let best = base[i];
    for (let j = 0; j < cands.length; j++) {
      if (mask & (1 << j)) {
        const d = cd[j][i];
        if (best === null || d < best) best = d;
      }
    }
    if (best === null) { unknown++; continue; }
    wsum += pts[i].weight * best;
    if (best > mx) mx = best;
    if (best <= radiusMm) covered += pts[i].weight;
  }
  return {
    ids, cost, unknown_count: unknown, weighted_sum_mm: wsum,
    max_mm: unknown > 0 ? null : (pts.length ? mx : null),
    covered_weight: covered,
  };
}

function popcount(x) { let c = 0; while (x) { x &= x - 1; c++; } return c; }

function optimize(prep, sc, budget) {
  const cands = prep.cands;
  const idx = new Map(cands.map((c, j) => [c.id, j]));
  const req = sc.required_ids || [], exc = sc.excluded_ids || [];
  let reqMask = 0, excMask = 0, reqCost = 0;
  for (const id of req) { const j = idx.get(id); if (j === undefined) throw new Error('unknown required ' + id); reqMask |= 1 << j; reqCost += cands[j].cost; }
  for (const id of exc) { const j = idx.get(id); if (j === undefined) throw new Error('unknown excluded ' + id); excMask |= 1 << j; }
  if (req.length > sc.max_selected) return { status: 'infeasible', reason: 'required_count_exceeds_max_selected', feasible_count: 0 };
  if (reqCost > budget) return { status: 'infeasible', reason: 'required_cost_exceeds_budget', feasible_count: 0 };
  const radiusMm = sc.coverage_radius_m * 1000;
  const n = cands.length;
  const feasible = [];
  for (let mask = 0; mask < (1 << n); mask++) {
    if ((mask & reqMask) !== reqMask) continue;
    if (mask & excMask) continue;
    if (popcount(mask) > sc.max_selected) continue;
    let cost = 0;
    for (let j = 0; j < n; j++) if (mask & (1 << j)) cost += cands[j].cost;
    if (cost > budget) continue;
    feasible.push(evalMask(prep, mask, radiusMm));
  }
  if (feasible.length === 0) return { status: 'infeasible', reason: 'no_feasible_plan', feasible_count: 0 };
  const objectives = {};
  for (const ob of ['mean', 'minimax', 'coverage']) {
    let best = null, bk = null;
    for (const m of feasible) {
      const k = keyOf(ob, m);
      if (best === null || cmpKey(k, bk) < 0) { best = m; bk = k; }
    }
    objectives[ob] = {
      selected_ids: best.ids, weighted_sum_mm: best.weighted_sum_mm, max_mm: best.max_mm,
      covered_weight: best.covered_weight, unknown_count: best.unknown_count, cost: best.cost,
    };
  }
  // Pareto among fully known plans
  const known = feasible.filter(m => m.unknown_count === 0);
  // collapse equal (cost,wsum) pairs to lexicographically smallest ids
  const rep = new Map();
  for (const m of known) {
    const key = m.cost + '|' + m.weighted_sum_mm;
    const cur = rep.get(key);
    if (!cur || cmpIds(m.ids, cur.ids) < 0) rep.set(key, m);
  }
  const reps = [...rep.values()];
  const pareto = reps.filter(p => !reps.some(q => q !== p &&
    q.cost <= p.cost && q.weighted_sum_mm <= p.weighted_sum_mm &&
    (q.cost < p.cost || q.weighted_sum_mm < p.weighted_sum_mm)))
    .sort((a, b) => cmpNum(a.cost, b.cost) || cmpNum(a.weighted_sum_mm, b.weighted_sum_mm) || cmpIds(a.ids, b.ids))
    .map(p => ({ cost: p.cost, weighted_sum_mm: p.weighted_sum_mm, selected_ids: p.ids }));
  return { status: 'optimal', reason: null, feasible_count: feasible.length, objectives, pareto };
}

function runTask(task) {
  const sc = task.scenario;
  const prep = prepare(task);
  const main = optimize(prep, sc, sc.budget);
  const B = sc.budget;
  const budgets = [...new Set([0, Math.floor(B / 2), B])].sort((a, b) => a - b);
  const sens = budgets.map(b => {
    const r = optimize(prep, sc, b);
    return {
      budget: b, status: r.status,
      objectives: r.status === 'optimal'
        ? { mean: r.objectives.mean.selected_ids, minimax: r.objectives.minimax.selected_ids, coverage: r.objectives.coverage.selected_ids }
        : { mean: null, minimax: null, coverage: null },
    };
  });
  const out = { status: main.status, reason: main.reason, feasible_count: main.feasible_count };
  if (main.status === 'optimal') { out.objectives = main.objectives; out.pareto = main.pareto; }
  out.budget_sensitivity = sens;
  return out;
}

if (require.main === module) {
  const inp = process.argv[2], outp = process.argv[3];
  const data = JSON.parse(fs.readFileSync(inp, 'utf8'));
  const result = {};
  for (const t of data.tasks) result[t.task_id] = runTask(t);
  fs.writeFileSync(outp, JSON.stringify(result, null, 1) + '\n');
  console.log('tasks', data.tasks.length, '->', outp);
}

module.exports = { haversineM, distMm, runTask, cmpIds, cmpStr };
