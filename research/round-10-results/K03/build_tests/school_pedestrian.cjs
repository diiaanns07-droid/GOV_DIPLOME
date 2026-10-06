/* K03 r10: school-access-case-v1 с distance_method = pedestrian-v1 (web/govtech/k03) через compareCase сборки.
 * Проверка против независимого перебора по строкам матрицы: до/после, неизвестные ≠ 0, unknown_targets, метрики, автовыбор;
 * case_digest зависит от политики и графа; матрица другого графа/политики отклоняется; допущения — не «прямая».
 * Run: node tests/govtech/school_pedestrian.cjs   (нужны файлы web/govtech/k03 — install_for_build.py)
 */
"use strict";
const path = require("path"), fs = require("fs"), assert = require("assert");
const root = path.resolve(__dirname, "../../web/govtech");
globalThis.window = globalThis;
require(path.join(root, "core/data.js"));
require(path.join(root, "core/evidence.js"));
const F = require(path.join(root, "core/facts.js"));
const SC = require(path.join(root, "school/case.js"));
const R = require(path.join(root, "k03/routing.js"));
const A = require(path.join(root, "k03/school-access-routing.js"));
const D = globalThis.CITY_EVIDENCE;
let n = 0;
const ok = (c, m) => { assert.ok(c, m); n++; };
const eq = (a, b, m) => { assert.deepStrictEqual(a, b, m); n++; };
const throwsCode = (f, code, m) => { try { f(); } catch (e) { eq(e.code, code, m + " → " + e.message); return; } assert.fail(m + ": no error"); };
const clone = (x) => JSON.parse(JSON.stringify(x));
const summary = {};

// независимый перебор по строкам матрицы (без nearestOf сборки): минимум только по строкам ok, ничья — меньший ID
function brute(c, mx, selected) {
  const tp = c.parameters.target_policy;
  const elig = c.schools.filter((s) => !tp.exclude_ids.includes(s.id) && (tp.include_ids.includes(s.id) || (tp.categories.includes(s.category) && !(s.qa || []).some((q) => tp.exclude_qa.includes(q)))));
  const extra = c.candidates.filter((k) => selected.includes(k.id));
  const row = new Map(mx.rows.map((r) => [r.origin_id + "|" + r.target_id, r]));
  const near = (o, ts) => { let best = null; for (const t of ts) { const r = row.get(o.id + "|" + t.id); if (r && r.status === "ok" && (best === null || r.distance_mm < best.d || (r.distance_mm === best.d && t.id < best.id))) best = { d: r.distance_mm, id: t.id }; } return best; };
  const rows = c.origins.map((o) => { const b = near(o, elig), a = near(o, [...elig, ...extra]);
    const unk = [...elig, ...extra].filter((t) => { const r = row.get(o.id + "|" + t.id); return !r || r.status !== "ok"; }).length;
    return { id: o.id, before: b ? b.d : null, after: a ? a.d : null, unk }; });
  const known = rows.filter((r) => r.after !== null), thr = c.parameters.threshold_m * 1000;
  const sum = known.reduce((s, r) => s + r.after, 0);
  return { rows, unknown: rows.length - known.length, sum: known.length ? sum : null, max: known.length ? Math.max(...known.map((r) => r.after)) : null,
    mean: known.length ? Math.round(sum / known.length) : null, within: known.filter((r) => r.after <= thr).length };
}

for (const city of ["shymkent", "astana"]) {
  const g = JSON.parse(fs.readFileSync(path.join(root, `k03/${city}.graph.json`), "utf8"));
  const G = R.prepare(g, { sha256hex: F.sha256hex });
  const base = SC.buildCase(D, city, F.qaOf);
  const geoDigest = SC.caseDigest(base);
  summary[city] = {};
  for (const pol of SC.ROUTING_POLICIES) {
    const c = clone(base);
    c.parameters.distance_method = SC.PEDESTRIAN;
    c.parameters.routing_policy_id = pol;
    c.parameters.routing_snapshot = { graph_sha256: g.graph_sha256, policy_sha256: g.policy_sha256, max_snap_m: g.max_snap_m };
    c.variants = { A: c.candidates[0].id, B: c.candidates[5].id };
    SC.validateCase(c);
    const mx = A.distanceMatrix(c, G);
    const cmp = SC.compareCase(c, mx);
    eq(cmp.method, "pedestrian-v1", `${city} ${pol}: method`);
    eq(cmp.policy_id, pol, `${city} ${pol}: policy`);
    ok(!cmp.limitations.includes("straight_line_not_route") && cmp.facts.every((f) => !f.assumptions.includes("straight_line_not_route")), `${city} ${pol}: не подписано как прямая`);
    for (const p of cmp.plans) {
      const sel = p.selected_candidate_ids, b = brute(c, mx, sel);
      eq(p.metrics.unknown_count, b.unknown, `${city} ${pol} ${p.id} unknown`);
      eq(p.metrics.sum_distance_mm, b.sum, `${city} ${pol} ${p.id} sum`);
      eq(p.metrics.max_distance_mm, b.max, `${city} ${pol} ${p.id} max`);
      eq(p.metrics.mean_distance_mm, b.mean, `${city} ${pol} ${p.id} mean`);
      eq(p.metrics.within_threshold_count, b.within, `${city} ${pol} ${p.id} within`);
      for (const r of p.rows) {
        const br = b.rows.find((x) => x.id === r.origin_id);
        eq([r.before_mm, r.after_mm, r.unknown_targets], [br.before, br.after, br.unk], `${city} ${pol} ${p.id} row ${r.origin_id}`);
        if (r.after_mm === null) eq(r.status, "unknown", `${city} ${pol} unknown ≠ 0`);
      }
      if (b.rows.some((r) => r.unk)) ok(p.limitations.includes("targets_with_unknown_distance"), `${city} ${pol} ${p.id}: неполнота показана`);
    }
    // автовыбор = минимум по правилу среди пустого набора и каждого места
    const opts = [[], ...c.candidates.map((k) => [k.id])].map((sel) => { const b = brute(c, mx, sel); return { sel, k: [b.unknown, b.sum === null ? Infinity : b.sum, b.max === null ? Infinity : b.max] }; })
      .sort((x, y) => { for (let i = 0; i < 3; i++) if (x.k[i] !== y.k[i]) return x.k[i] - y.k[i]; return x.sel.length - y.sel.length || (x.sel.join() < y.sel.join() ? -1 : x.sel.join() > y.sel.join() ? 1 : 0); });
    eq(cmp.plans.find((p) => p.id === "auto").selected_candidate_ids, opts[0].sel, `${city} ${pol}: автовыбор`);
    // отпечаток графа/политики в digest; несовпадающая матрица отклоняется
    ok(cmp.case_digest !== geoDigest, `${city} ${pol}: digest отличается от прямой`);
    const c2 = clone(c); c2.parameters.routing_snapshot.graph_sha256 = "0".repeat(64);
    ok(SC.caseDigest(c2) !== cmp.case_digest, `${city} ${pol}: digest зависит от graph_sha256`);
    throwsCode(() => SC.compareCase(c2, mx), "matrix_snapshot", `${city} ${pol}: матрица другого графа`);
    const other = SC.ROUTING_POLICIES.find((x) => x !== pol), c3 = clone(c); c3.parameters.routing_policy_id = other;
    throwsCode(() => SC.compareCase(c3, mx), "matrix_snapshot", `${city} ${pol}: матрица другой политики`);
    const c4 = clone(c); delete c4.parameters.routing_snapshot;
    throwsCode(() => SC.validateCase(c4), "routing_snapshot", `${city} ${pol}: без отпечатка графа`);
    const c5 = clone(c); c5.parameters.routing_policy_id = null;
    throwsCode(() => SC.validateCase(c5), "policy", `${city} ${pol}: без политики`);
    const st = {}; for (const r of mx.rows) st[r.status] = (st[r.status] || 0) + 1;
    const cur = cmp.plans[0];
    summary[city][pol] = { matrix_statuses: st, current_unknown_origins: cur.metrics.unknown_count, current_mean_m: cur.metrics.mean_distance_mm === null ? null : cur.metrics.mean_distance_mm / 1000,
      origins_with_unknown_targets: cur.rows.filter((r) => r.unknown_targets).length, auto: cmp.plans.find((p) => p.id === "auto").selected_candidate_ids };
  }
  // прямая не изменилась: прежняя матрица и digest
  const cg = SC.compareCase(base, SC.geodesicMatrix(base));
  ok(cg.limitations[0] === "straight_line_not_route" && cg.plans[0].rows.every((r) => r.unknown_targets === 0), `${city}: прямая без изменений`);
}
console.log(JSON.stringify(summary));
console.log(`school_pedestrian: ${n} checks PASS`);
