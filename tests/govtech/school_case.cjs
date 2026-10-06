/* school-access-case-v1: checks of web/govtech/school/case.js against an independent brute-force recomputation.
 * Run: node tests/govtech/school_case.cjs
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
const D = globalThis.CITY_EVIDENCE;
let n = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); n++; };
const eq = (a, b, msg) => { assert.deepStrictEqual(a, b, msg); n++; };
const throwsCode = (f, code, msg) => { try { f(); } catch (e) { eq(e.code, code, msg + " → " + e.message); return; } assert.fail(msg + ": no error"); };
const clone = (x) => JSON.parse(JSON.stringify(x));

// independent haversine (same formula, written separately) and nearest search
function hav(lon1, lat1, lon2, lat2) {
  const R = 6371008.8, rad = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lon2 - lon1) * rad / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a))));
}
function brute(c, selected, unknownPairs, mx) {
  const md = mx ? new Map(mx.rows.map((r) => [r.origin_id + ">" + r.target_id, r.distance_mm])) : null;
  const tp = c.parameters.target_policy;
  const elig = c.schools.filter((s) => !tp.exclude_ids.includes(s.id) && (tp.include_ids.includes(s.id) || (tp.categories.includes(s.category) && !s.qa.some((q) => tp.exclude_qa.includes(q)))));
  const extra = c.candidates.filter((k) => selected.includes(k.id));
  const near = (o, ts) => {
    let best = null;
    for (const t of ts) {
      if (unknownPairs && unknownPairs.has(o.id + ">" + t.id)) continue;
      const mm = md ? md.get(o.id + ">" + t.id) : Math.round(hav(o.lon, o.lat, t.lon, t.lat) * 1000);
      if (best === null || mm < best) best = mm;
    }
    return best;
  };
  const rows = c.origins.map((o) => ({ id: o.id, before: near(o, elig), after: near(o, [...elig, ...extra]) }));
  const known = rows.filter((r) => r.after !== null), thr = c.parameters.threshold_m * 1000;
  const sum = known.reduce((s, r) => s + r.after, 0);
  return { rows, unknown: rows.length - known.length, sum: known.length ? sum : null, max: known.length ? Math.max(...known.map((r) => r.after)) : null,
    mean: known.length ? sum / known.length : null, within: known.filter((r) => r.after <= thr).length,
    closer: rows.filter((r) => r.before !== null && r.after !== null && r.after < r.before).length };
}
function checkPlan(c, cmp, id, selected, unknownPairs, label, mx) {
  const p = cmp.plans.find((x) => x.id === id), b = brute(c, selected, unknownPairs, mx);
  eq(p.metrics.unknown_count, b.unknown, label + " unknown");
  eq(p.metrics.sum_distance_mm, b.sum, label + " sum");
  eq(p.metrics.max_distance_mm, b.max, label + " max");
  eq(p.metrics.mean_distance_mm, b.mean, label + " mean");
  eq(p.metrics.within_threshold_count, b.within, label + " within");
  eq(p.closer_count, b.closer, label + " closer");
  for (const r of p.rows) {
    const br = b.rows.find((x) => x.id === r.origin_id);
    eq(r.before_mm, br.before, label + " before " + r.origin_id);
    eq(r.after_mm, br.after, label + " after " + r.origin_id);
    eq(r.delta_mm, br.before === null || br.after === null ? null : br.after - br.before, label + " delta " + r.origin_id);
    if (r.after_mm === null) eq(r.status, "unknown", label + " unknown status");
  }
  ok(Math.abs(p.metrics.within_threshold_share_of_all_points - b.within / c.origins.length) < 1e-12, label + " share uses all points");
}

for (const city of ["shymkent", "astana"]) {
  const c = SC.buildCase(D, city, F.qaOf);
  SC.validateCase(c);
  eq(c.origins.length, 25, city + " 25 grid points");
  ok(c.candidates.length <= SC.LIMITS.candidates, city + " candidate limit");
  ok(c.origins.every((o) => o.kind === "derived" && o.weight === 1), city + " origins derived, equal weights");
  ok(c.candidates.every((k) => k.cost === null && k.land_status === "unknown"), city + " no invented cost/land");
  ok(c.schools.every((s) => s.capacity === null && s.access_eligibility === "unknown"), city + " capacity/eligibility unknown");
  ok(c.sources.every((s) => s.verification_status === "secondary_only"), city + " secondary source");
  // every single variant against brute force
  const mx = SC.geodesicMatrix(c);
  for (const k of c.candidates) {
    const cc = clone(c); cc.variants = { A: k.id, B: null };
    checkPlan(cc, SC.compareCase(cc, mx), "A", [k.id], null, `${city} A=${k.id}`);
  }
  // auto choice = lexicographic minimum over empty + singles, empty on ties
  const cmp = SC.compareCase(c, mx), auto = cmp.plans.find((p) => p.id === "auto");
  const opts = [[], ...c.candidates.map((k) => [k.id])].map((sel) => ({ sel, b: brute(c, sel) }));
  opts.sort((x, y) => x.b.unknown - y.b.unknown || x.b.sum - y.b.sum || x.b.max - y.b.max || x.sel.length - y.sel.length || String(x.sel).localeCompare(String(y.sel)));
  eq(auto.selected_candidate_ids, opts[0].sel, city + " auto choice");
  // digest: order-independent, sensitive to semantics
  const sh = clone(c); sh.schools.reverse(); sh.origins.reverse(); sh.candidates.reverse(); sh.sources.reverse();
  eq(SC.caseDigest(sh), cmp.case_digest, city + " digest ignores order");
  const t2 = clone(c); t2.parameters.threshold_m = 600; ok(SC.caseDigest(t2) !== cmp.case_digest, city + " digest covers threshold");
  const t3 = clone(c); t3.origins[0].lon += 1e-6; ok(SC.caseDigest(t3) !== cmp.case_digest, city + " digest covers coordinates");
  const t4 = clone(c); t4.parameters.target_policy.exclude_ids.push(cmp.eligible_school_ids[0]); ok(SC.caseDigest(t4) !== cmp.case_digest, city + " digest covers manual policy");
  const t5 = clone(c); t5.title = "другое"; eq(SC.caseDigest(t5), cmp.case_digest, city + " title is not semantic");
  // facts are derived from the plans, no hard-coded values
  for (const f of cmp.facts) {
    ok(f.kind === "derived" && Array.isArray(f.assumptions) && f.assumptions.includes("straight_line_not_route"), city + " fact kind/assumptions " + f.id);
    const p = cmp.plans.find((x) => x.id === f.plan_id);
    if (!f.origin_id && f.metric in p.metrics) eq(f.value, p.metrics[f.metric], city + " fact value " + f.id);
  }
  // export → import round trip; tampering and foreign snapshots are refused
  const cv = clone(c); cv.variants = { A: c.candidates[0].id, B: c.candidates[1].id };
  const text = SC.exportCase(cv);
  eq(SC.caseDigest(SC.importCase(text, D)), SC.caseDigest(cv), city + " import round trip");
  throwsCode(() => SC.importCase(text.replace('"threshold_m": 500', '"threshold_m": 650'), D), "import_digest", city + " tampered file");
  const foreign = JSON.parse(text); delete foreign.case_digest; foreign.snapshot_id = "overture-2020-01-01.0-" + city;
  throwsCode(() => SC.importCase(JSON.stringify(foreign), D), "bind_snapshot", city + " other snapshot");
  throwsCode(() => SC.importCase("x".repeat(SC.LIMITS.bytes + 1), D), "import_size", city + " size limit before parsing");
  throwsCode(() => SC.importCase("{", D), "import_json", city + " not JSON");
  const extraField = JSON.parse(text); delete extraField.case_digest; extraField.population = 1000;
  throwsCode(() => SC.importCase(JSON.stringify(extraField), D), "unknown_field", city + " unknown field");
}

// unknown distances stay unknown (never 0); a fully unknown origin does not enter sums or the covered count
{
  const c = SC.buildCase(D, "shymkent", F.qaOf);
  const mx = SC.geodesicMatrix(c), o0 = c.origins[0].id, o1 = c.origins[1].id, unknown = new Set();
  for (const r of mx.rows) {
    if (r.origin_id === o0) { r.status = "disconnected"; r.distance_mm = null; r.geometry = null; unknown.add(r.origin_id + ">" + r.target_id); }
    if (r.origin_id === o1 && !r.target_id.startsWith("m")) { r.status = "outside_coverage"; r.distance_mm = null; unknown.add(r.origin_id + ">" + r.target_id); }
  }
  c.variants = { A: "m1a", B: null };
  const cmp = SC.compareCase(c, mx);
  checkPlan(c, cmp, "current", [], unknown, "unknown current");
  checkPlan(c, cmp, "A", ["m1a"], unknown, "unknown A");
  const cur = cmp.plans[0];
  eq(cur.metrics.unknown_count, 2, "two unknown origins now");
  const a = cmp.plans.find((p) => p.id === "A"), r1 = a.rows.find((r) => r.origin_id === o1);
  eq(r1.before_mm, null, "before unknown"); ok(r1.after_mm !== null, "after known via candidate"); eq(r1.delta_mm, null, "delta null when one side unknown");
  eq(r1.status, "partial", "known path but some targets unknown → partial"); ok(r1.unknown_target_ids.length > 0, "unknown targets listed");
  ok(a.metrics.partial_count >= 1 && a.limitations.includes("some_targets_without_known_path"), "partial counted and limited");
  // a matrix with distance at status != ok is rejected
  const bad = SC.geodesicMatrix(c); bad.rows[0].status = "disconnected";
  throwsCode(() => SC.compareCase(c, bad), "matrix_distance", "distance with non-ok status");
  const wrong = SC.geodesicMatrix(c); wrong.method = "pedestrian-v1";
  throwsCode(() => SC.compareCase(c, wrong), "matrix_method", "matrix method mismatch");
}
// no school eligible: everything unknown, nothing counted as 0
{
  const c = SC.buildCase(D, "astana", F.qaOf);
  c.parameters.target_policy.exclude_ids = c.schools.filter((s) => SC.targetStatus(c, s).eligible).map((s) => s.id);
  const cmp = SC.compareCase(c, SC.geodesicMatrix(c)), cur = cmp.plans[0];
  eq([cur.metrics.unknown_count, cur.metrics.sum_distance_mm, cur.metrics.mean_distance_mm, cur.metrics.max_distance_mm, cur.metrics.within_threshold_count], [25, null, null, null, 0], "all unknown");
  ok(cur.limitations.includes("no_eligible_school"), "limitation no_eligible_school");
}
// validation refusals
{
  const base = SC.buildCase(D, "astana", F.qaOf);
  const bad = (mut, code, msg) => { const c = clone(base); mut(c); throwsCode(() => SC.validateCase(c), code, msg); };
  bad((c) => { c.city_id = "almaty"; }, "city", "unknown city");
  bad((c) => { c.origins[0].lon = c.bbox[2] + 0.01; }, "origin_outside", "origin outside bbox");
  bad((c) => { c.candidates[0].lat = c.bbox[1] - 0.01; }, "candidate_outside", "candidate outside bbox");
  bad((c) => { c.origins.push(...c.origins.slice(0, 1).map((o) => ({ ...o, id: "extra" }))); }, "limit_origins", "26 origins");
  bad((c) => { c.candidates[1].id = c.candidates[0].id; }, "duplicate_id", "duplicate id");
  bad((c) => { c.parameters.threshold_m = 0; }, "threshold", "threshold 0");
  bad((c) => { c.parameters.distance_method = "pedestrian-v1"; }, "policy", "pedestrian needs a routing policy");
  bad((c) => { c.parameters.distance_method = "pedestrian-v1"; c.parameters.routing_policy_id = "pedestrian-v1-strict"; }, "routing", "pedestrian needs graph hashes");
  bad((c) => { c.parameters.distance_method = "walk"; }, "method", "unknown method");
  bad((c) => { c.parameters.max_new_objects = 2; }, "max_new_objects", "max 1 object");
  bad((c) => { c.candidates[0].cost = 0; }, "cost", "cost must be null or object");
  bad((c) => { c.candidates[0].kind = "observed"; }, "bad_kind", "candidate cannot be observed");
  bad((c) => { c.schools[0].capacity = -1; }, "capacity", "negative capacity");
  bad((c) => { c.sources[0].verification_status = "verified"; }, "verification_status", "unknown verification status");
  bad((c) => { c.variants.A = "nope"; }, "variants", "unknown variant");
  bad((c) => { c.origins[0].weight = 3; }, "weight", "equal weights only");
}

// pedestrian-v1 matrices from the installed K03 module (web/govtech/k03): unknown statuses stay unknown, policies never mix
{
  const R = require(path.join(root, "k03/routing.js")), A = require(path.join(root, "k03/school-access-routing.js"));
  let m2 = 0;
  for (const city of ["shymkent", "astana"]) {
    const G = R.prepare(JSON.parse(fs.readFileSync(path.join(root, `k03/${city}.graph.json`), "utf8")), { sha256hex: F.sha256hex });
    for (const pol of SC.ROUTING_POLICIES) {
      const c = SC.buildCase(D, city, F.qaOf);
      c.parameters.distance_method = SC.PEDESTRIAN; c.parameters.routing_policy_id = pol;
      c.parameters.routing = { graph_sha256: G.g.graph_sha256, policy_sha256: G.g.policy_sha256, max_snap_m: G.g.max_snap_m };
      c.variants = { A: c.candidates[0].id, B: c.candidates[5].id };
      SC.validateCase(c);
      const mx = A.distanceMatrix(c, G), unknown = new Set(mx.rows.filter((r) => r.status !== "ok").map((r) => r.origin_id + ">" + r.target_id));
      const cmp = SC.compareCase(c, mx);
      checkPlan(c, cmp, "current", [], unknown, `${city} ${pol} current`, mx);
      checkPlan(c, cmp, "A", [c.candidates[0].id], unknown, `${city} ${pol} A`, mx);
      checkPlan(c, cmp, "B", [c.candidates[5].id], unknown, `${city} ${pol} B`, mx);
      const g = SC.buildCase(D, city, F.qaOf);
      ok(SC.caseDigest(c) !== SC.caseDigest(g), `${city} ${pol} digest differs from geodesic`);
      const other = JSON.parse(JSON.stringify(c)); other.parameters.routing_policy_id = SC.ROUTING_POLICIES.find((x) => x !== pol);
      throwsCode(() => SC.compareCase(other, mx), "matrix_policy", `${city} ${pol} policy mix refused`);
      const wrongGraph = JSON.parse(JSON.stringify(c)); wrongGraph.parameters.routing.graph_sha256 = "0".repeat(64);
      throwsCode(() => SC.compareCase(wrongGraph, mx), "matrix_graph", `${city} ${pol} other graph refused`);
      throwsCode(() => SC.compareCase(c, SC.geodesicMatrix(c)), "matrix_method", `${city} ${pol} geodesic matrix not substituted`);
      m2++;
    }
  }
  eq(m2, 4, "4 pedestrian cases checked");
}
console.log(`all school-case checks passed incl. pedestrian (${n})`);
