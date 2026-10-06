/* Differential check: the BUILD school-case adapter (web/govtech/school/case.js) against the independent K05 round-10
 * comparison module (tests/govtech/k05/, vendored byte-identical; core/plan.js there = pinned plan.js + K05 patch
 * plan_matrix.patch, used only in this test). Same case, same matrix → same rows, metrics and automatic choice.
 * Run: node tests/govtech/school_vs_k05.cjs
 */
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");
const root = path.resolve(__dirname, "../../web/govtech");
globalThis.window = globalThis;
require(path.join(root, "core/data.js"));
require(path.join(root, "core/evidence.js"));
const F = require(path.join(root, "core/facts.js"));
const SC = require(path.join(root, "school/case.js"));
const K05 = require("./k05/school-compare.js");
const D = globalThis.CITY_EVIDENCE;
let n = 0;
const eq = (a, b, msg) => { assert.deepStrictEqual(a, b, msg); n++; };

// K05 accepts exactly the contract keys; package records may carry extra provenance fields, which are not semantic here.
const BASE = ["id", "label", "lon", "lat", "kind", "source_ids", "field_provenance", "qa"];
// K05 uses the plan.js ID pattern, which has no ':'; K01 package IDs look like "overture:<uuid>" (interop finding, see
// research/round-10-results/BUILD/INTEGRATION.json). For K05 only, IDs are renamed reversibly.
const toK = (id) => id.replace(/:/g, "__"), fromK = (id) => (id === null ? null : id.replace(/__/g, ":"));
const pick = (o, keys) => Object.fromEntries(keys.filter((k) => k in o).map((k) => [k, o[k]]));
function forK05(c) {
  const x = SC.toContract(c);
  x.sources = x.sources.map((s) => pick(s, ["id", "url", "publisher", "title", "retrieved_at", "verification_status", "license", "published_at", "data_period", "content_sha256"]));
  x.schools = x.schools.map((s) => ({ ...pick(s, [...BASE, "category", "access_eligibility", "capacity", "capacity_source_ids"]), field_provenance: s.field_provenance || {}, qa: s.qa || [] }));
  x.origins = x.origins.map((o) => ({ ...pick(o, [...BASE, "parent_source_id", "method"]), field_provenance: o.field_provenance || {}, qa: o.qa || [] }));
  x.candidates = x.candidates.map((k) => ({ ...pick(k, [...BASE, "cost", "land_status"]), field_provenance: k.field_provenance || {}, qa: k.qa || [] }));
  for (const arr of [x.schools, x.origins, x.candidates]) for (const e of arr) e.id = toK(e.id);
  x.selected_candidate_ids = x.candidates.map((k) => k.id);   // K05 compares each listed candidate as its own variant
  return x;
}
function compare(c, mx, label) {
  const mine = SC.compareCase(c, mx);
  const x = forK05(c), targets = new Set([...x.schools, ...x.candidates].map((t) => t.id));
  const entries = mx.rows.map((r) => ({ ...pick(r, ["distance_mm", "status", "method", "policy_id", "route_edge_ids", "geometry", "assumptions"]),
    origin_id: toK(r.origin_id), target_id: toK(r.target_id) })).filter((r) => targets.has(r.target_id));
  const theirs = K05.compareCase(x, { method: mx.method, policy_id: mx.policy_id, entries });
  const cur = theirs.plans.find((p) => p.plan_id === "current");
  const same = (m, t, what) => {
    for (const k of ["total_origins", "known_count", "unknown_count", "partial_count", "max_distance_mm", "within_threshold_count", "within_threshold_share_of_all_points"]) eq(m.metrics[k], t.metrics[k], `${label} ${what} ${k}`);
    eq(m.metrics.sum_distance_mm, t.metrics.known_count ? t.metrics.sum_distance_mm : null, `${label} ${what} sum (K05: 0 when nothing known, BUILD: null)`);
    eq(m.metrics.mean_distance_mm, t.metrics.mean_distance_mm, `${label} ${what} mean`);
    const tr = new Map(t.rows.map((r) => [fromK(r.origin_id), { ...r, nearest_target_id: fromK(r.nearest_target_id), unknown_target_ids: r.unknown_target_ids.map(fromK).sort() }]));
    for (const r of m.rows) {
      const q = tr.get(r.origin_id);
      eq([r.before_mm, r.after_mm, r.delta_mm, r.status, r.nearest_target_id], [q.before_mm, q.after_mm, q.delta_mm, q.status, q.nearest_target_id], `${label} ${what} row ${r.origin_id}`);
      eq(r.unknown_target_ids, q.unknown_target_ids, `${label} ${what} unknown targets ${r.origin_id}`);
    }
  };
  same(mine.plans[0], cur, "current");
  for (const k of c.candidates) {
    const cc = JSON.parse(JSON.stringify(c)); cc.variants = { A: k.id, B: null };
    same(SC.compareCase(cc, mx).plans.find((p) => p.id === "A"), theirs.plans.find((p) => p.plan_id === "candidate:" + toK(k.id)), "candidate " + k.id);
  }
  eq(mine.plans.find((p) => p.id === "auto").selected_candidate_ids, theirs.plans.find((p) => p.plan_id === "auto:contract-lex").selected_candidate_ids.map(fromK), label + " auto choice");
}

const cases = [];
for (const city of ["shymkent", "astana"]) cases.push([city + " slice grid", SC.buildCase(D, city, F.qaOf)]);
const pkg = SC.normalizeCase(JSON.parse(fs.readFileSync(path.join(root, "school/cases/shymkent.case.json"), "utf8")));
cases.push(["shymkent K01 package", pkg]);
for (const [label, c] of cases) {
  compare(c, SC.geodesicMatrix(c), label + " geodesic");
  // unknown paths: whole origin unknown, some schools unknown for another origin, one candidate unreachable
  const mx = SC.geodesicMatrix(c), o = c.origins.map((x) => x.id).sort();
  for (const r of mx.rows) {
    const kill = r.origin_id === o[0] || (r.origin_id === o[1] && !c.candidates.some((k) => k.id === r.target_id)) || (r.origin_id === o[2] && r.target_id === c.candidates[0].id);
    if (kill) { r.status = "disconnected"; r.distance_mm = null; r.geometry = null; }
  }
  compare(c, mx, label + " with unknown paths");
}
// pedestrian-v1 matrices of the installed K03 module, both policies
const R = require(path.join(root, "k03/routing.js")), A = require(path.join(root, "k03/school-access-routing.js"));
let ped = 0;
for (const [label, c0] of cases) {
  const G = R.prepare(JSON.parse(fs.readFileSync(path.join(root, `k03/${c0.city_id}.graph.json`), "utf8")), { sha256hex: F.sha256hex });
  for (const pol of SC.ROUTING_POLICIES) {
    const c = JSON.parse(JSON.stringify(c0));
    Object.assign(c.parameters, { distance_method: SC.PEDESTRIAN, routing_policy_id: pol, routing: { graph_sha256: G.g.graph_sha256, policy_sha256: G.g.policy_sha256, max_snap_m: G.g.max_snap_m } });
    compare(c, A.distanceMatrix(c, G), `${label} ${pol}`); ped++;
  }
}
console.log(`BUILD school case = K05 compare on ${cases.length} cases × (geodesic, unknown paths) + ${ped} pedestrian matrices (${n} checks)`);
