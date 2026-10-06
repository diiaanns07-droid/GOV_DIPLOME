// K05 r10: tests of school-compare.js on a PATCHED copy of the BUILD (see run_tests.py).
// Usage: node test_school_compare.cjs <govtech dir with school-compare.js + patched core/> <hand_cases.json> <ref_dump.json>
const fs = require("fs"), path = require("path");
const [gt, handPath, refPath] = process.argv.slice(2);
const SC = require(path.resolve(gt, "school-compare.js"));
const hand = JSON.parse(fs.readFileSync(handPath, "utf8"));
const ref = JSON.parse(fs.readFileSync(refPath, "utf8"));
const FIELDS = hand.metric_fields_order;
let fails = 0, passes = 0;
const check = (name, ok, detail) => { if (ok) passes++; else { fails++; console.log("FAIL " + name + (detail ? " — " + String(detail).slice(0, 300) : "")); } };
const near = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) < 1e-9);
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || "throw:" + e.message; } };
const clone = (o) => JSON.parse(JSON.stringify(o));
const planOf = (out, id) => out.plans.find((p) => p.plan_id === id);
const view = (out) => out.plans.map((p) => ({ id: p.plan_id, sel: p.selected_candidate_ids, m: p.metrics, cost: p.cost,
  rows: p.rows.slice().sort((a, b) => (a.origin_id < b.origin_id ? -1 : 1)) }));
let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const shuffle = (a) => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

for (const h of hand.cases) {
  const name = h.case.case_id, out = SC.compareCase(h.case, h.matrix);
  // 1. hand-written expectations
  for (const [pid, exp] of Object.entries(h.expected)) {
    const p = planOf(out, pid);
    check(`${name} ${pid} present`, !!p);
    if (!p) continue;
    check(`${name} ${pid} ids`, JSON.stringify(p.selected_candidate_ids) === JSON.stringify(exp.ids), JSON.stringify(p.selected_candidate_ids));
    const rows = Object.fromEntries(p.rows.map((r) => [r.origin_id, r]));
    for (const [k, f] of [["after", "after_mm"], ["status", "status"], ["delta", "delta_mm"], ["nearest", "nearest_target_id"]])
      for (const [o, v] of Object.entries(exp[k] || {})) check(`${name} ${pid} ${o} ${f}`, rows[o][f] === v, `${rows[o][f]} vs ${v}`);
    if (exp.metrics) FIELDS.forEach((f, i) => check(`${name} ${pid} ${f}`, near(p.metrics[f], exp.metrics[i]), `${p.metrics[f]} vs ${exp.metrics[i]}`));
  }
  // 2. independent Python reference (all plans, all rows)
  const r = ref[name];
  for (const [pid, rp] of Object.entries(r.plans)) {
    const p = planOf(out, pid);
    check(`${name} ref ${pid} ids`, p && JSON.stringify(p.selected_candidate_ids) === JSON.stringify(rp.selected_candidate_ids));
    if (!p) continue;
    for (const f of FIELDS) check(`${name} ref ${pid} ${f}`, near(p.metrics[f], rp.metrics[f]), `${p.metrics[f]} vs ${rp.metrics[f]}`);
    const js = Object.fromEntries(p.rows.map((x) => [x.origin_id, x]));
    for (const rr of rp.rows) for (const f of ["before_mm", "after_mm", "delta_mm", "status", "nearest_target_id", "nearest_access_eligibility_unknown"])
      check(`${name} ref ${pid} ${rr.origin_id} ${f}`, js[rr.origin_id][f] === rr[f], `${js[rr.origin_id][f]} vs ${rr[f]}`);
  }
  check(`${name} evaluated_sets`, out.evaluated_sets === r.evaluated_sets, `${out.evaluated_sets} vs ${r.evaluated_sets}`);
  // 3. permutations of every array (incl. matrix entries and selected ids) -> same result and same digest
  for (let t = 0; t < 3; t++) {
    const c = clone(h.case), m = clone(h.matrix);
    for (const k of ["schools", "origins", "candidates", "sources", "selected_candidate_ids"]) c[k] = shuffle(c[k]);
    m.entries = shuffle(m.entries);
    const o2 = SC.compareCase(c, m);
    const norm = (o) => view(o).filter((x) => !x.id.startsWith("candidate:")).concat(view(o).filter((x) => x.id.startsWith("candidate:")).sort((a, b) => (a.id < b.id ? -1 : 1)));
    check(`${name} permutation ${t} result`, JSON.stringify(norm(o2)) === JSON.stringify(norm(out)));
    check(`${name} permutation ${t} digest`, o2.case_digest === out.case_digest);
  }
  // 4. facts: unique ids, derived, plan ids exist; total_origins equals input (no point can be dropped)
  const ids = out.facts.map((f) => f.id);
  check(`${name} facts unique`, new Set(ids).size === ids.length);
  check(`${name} facts derived + plan refs`, out.facts.every((f) => f.kind === "derived" && planOf(out, f.plan_id) && Array.isArray(f.source_ids)));
  check(`${name} all origins counted`, out.plans.every((p) => p.metrics.total_origins === h.case.origins.length));
}

// 5. digest sensitivity
const H2 = hand.cases.find((h) => h.case.case_id === "H2_lex_vs_minimax");
const d0 = SC.compareCase(H2.case, H2.matrix).case_digest;
for (const [what, f] of [["threshold", (c) => (c.parameters.threshold_m = 2.5)], ["coordinate", (c) => (c.origins[0].lon += 0.0001)],
  ["school kind", (c) => (c.schools[0].kind = "observed_secondary")], ["snapshot", (c) => (c.snapshot_id = "other")]]) {
  const c = clone(H2.case); f(c);
  check(`digest changes with ${what}`, SC.compareCase(c, H2.matrix).case_digest !== d0);
}
{ const m = clone(H2.matrix); m.entries[0].distance_mm += 1; check("digest changes with a matrix distance", SC.compareCase(H2.case, m).case_digest !== d0); }

// 6. no fake cost: null costs -> no_cost_data, plan.cost null; costs never change the geographic choice
{
  const o = SC.compareCase(H2.case, H2.matrix);
  check("no_cost_data mode", o.cost_mode === "no_cost_data" && o.plans.every((p) => p.cost === null));
  const c = clone(H2.case);
  c.candidates.forEach((k, i) => (k.cost = { value: i === 0 ? 900 : 1, currency: "KZT", period: "2026", kind: "estimate", source_ids: [] }));
  const o2 = SC.compareCase(c, H2.matrix);
  check("homogeneous cost shown, choice unchanged", o2.cost_mode === "homogeneous" && planOf(o2, "auto:contract-lex").selected_candidate_ids[0] === "A" && planOf(o2, "candidate:A").cost.value === 900);
  c.candidates[1].cost.currency = "USD";
  check("mixed cost units not comparable", SC.compareCase(c, H2.matrix).cost_mode === "mixed_units_not_comparable");
}

// 7. strict validation (atomic typed errors)
const H1 = hand.cases.find((h) => h.case.case_id === "H1_unknowns_restricted");
const bad = [
  ["missing matrix pair", (c, m) => m.entries.pop(), "matrix_incomplete"],
  ["duplicate matrix pair", (c, m) => m.entries.push(clone(m.entries[0])), "matrix_duplicate_pair"],
  ["distance with non-ok status", (c, m) => { const e = m.entries.find((x) => x.status !== "ok"); e.distance_mm = 5; }, "matrix_bad_distance"],
  ["ok with null distance", (c, m) => { const e = m.entries.find((x) => x.status === "ok"); e.distance_mm = null; }, "matrix_bad_distance"],
  ["negative distance", (c, m) => { m.entries[0].distance_mm = -1; }, "matrix_bad_distance"],
  ["fractional distance", (c, m) => { m.entries[0].distance_mm = 10.5; }, "matrix_bad_distance"],
  ["unknown status", (c, m) => { m.entries[0].status = "maybe"; }, "matrix_bad_status"],
  ["method mismatch", (c, m) => { m.method = "pedestrian-v1"; }, "matrix_method_mismatch"],
  ["entry method mixed", (c, m) => { m.entries[0].method = "pedestrian-v1"; }, "matrix_mixed_method"],
  ["unknown ref", (c, m) => { m.entries[0].origin_id = "ZZ"; }, "matrix_unknown_ref"],
  ["unknown field", (c) => { c.budget = 100; }, "unknown_field"],
  ["duplicate id across kinds", (c) => { c.candidates[0].id = "S1"; }, "duplicate_id"],
  ["origin outside bbox", (c) => { c.origins[0].lon = 70.5; }, "outside_bbox"],
  ["NaN coordinate", (c) => { c.origins[0].lat = NaN; }, "bad_coordinate"],
  ["candidate observed kind", (c) => { c.candidates[0].kind = "observed"; }, "bad_candidate_kind"],
  ["selected unknown candidate", (c) => { c.selected_candidate_ids = ["Q"]; }, "bad_selection"],
  ["pedestrian without policy", (c, m) => { c.parameters.distance_method = "pedestrian-v1"; m.method = "pedestrian-v1"; }, "bad_policy"],
  ["threshold zero", (c) => { c.parameters.threshold_m = 0; }, "bad_threshold"],
  ["26 origins", (c) => { c.origins = Array.from({ length: 26 }, (_, i) => ({ ...c.origins[0], id: "o" + i })); }, "too_many_origins"],
  ["other city", (c) => { c.city_id = "almaty"; }, "bad_city"],
  ["unknown source ref", (c) => { c.schools[0].source_ids = ["nope"]; }, "unknown_source"],
];
for (const [name, f, want] of bad) {
  const c = clone(H1.case), m = clone(H1.matrix); f(c, m);
  const got = code(() => SC.compareCase(c, m));
  check(`reject ${name}`, got === want, got);
}
// input objects are not mutated
{ const c = clone(H1.case), m = clone(H1.matrix), s1 = JSON.stringify(c), s2 = JSON.stringify(m); SC.compareCase(c, m);
  check("inputs not mutated", JSON.stringify(c) === s1 && JSON.stringify(m) === s2); }

console.log(`${passes} passed, ${fails} failed`);
process.exit(fails ? 1 : 0);
