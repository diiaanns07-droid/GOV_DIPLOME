// K07 round 8: write the SYNTHETIC demo scenarios (city-plan-v2) for both cities and both categories to fixtures/.
// Usage: node make_fixtures.cjs --app-root <BUILD extraction with web/data.js, web/facts.js>
// Real parts: city_id, bbox and source_snapshot of the BUILD slice. SYNTHETIC parts: control points, weights, sites,
// costs, budget (web/plan_demo.js). Provenance goes to fixtures/MANIFEST.json, not into the scenarios (strict schema).
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const K = path.join(__dirname, ".."), argv = process.argv.slice(2), root = path.resolve(argv[argv.indexOf("--app-root") + 1]);
const W = fs.existsSync(path.join(root, "web")) ? path.join(root, "web") : root;
const C = require(path.join(K, "web", "plan_calc.js")), DEMO = require(path.join(K, "web", "plan_demo.js")), F = require(path.join(W, "facts.js"));
const box = {}; vm.createContext(box); box.window = box;
const dataText = fs.readFileSync(path.join(W, "data.js"), "utf8");
vm.runInContext(dataText, box, { filename: "data.js" });
const D = box.CITY_EVIDENCE, outDir = path.join(K, "fixtures"), files = [];
fs.mkdirSync(outDir, { recursive: true });
for (const city of ["shymkent", "astana"]) {
  const ctx = C.makeContext(D, city, F);
  for (const cat of ["school", "outpatient_clinic"]) {
    const d = DEMO.syntheticDemo(ctx.bbox, cat);
    const sc = { schema_version: C.SCHEMA, city_id: city, source_snapshot: ctx.source_snapshot, category: cat, control_points: d.control_points,
      candidates: d.candidates, budget: d.budget, max_selected: d.max_selected, coverage_radius_m: d.coverage_radius_m,
      required_ids: d.required_ids, excluded_ids: d.excluded_ids, selected_ids: d.selected_ids };
    const v = C.validatePlanScenario(sc, ctx);
    if (!v.ok) throw new Error(JSON.stringify(v.error));
    const r = C.optimizePlans(ctx, v.scenario);
    const name = `synthetic_demo_${city}_${cat}.json`, text = JSON.stringify(sc, null, 1) + "\n";
    fs.writeFileSync(path.join(outDir, name), text);
    files.push({ file: name, sha256: crypto.createHash("sha256").update(text).digest("hex"), city, category: cat, source_snapshot: ctx.source_snapshot,
      problem_digest: r.problem_digest, status: r.status, feasible_count: r.feasible_count, baseline_records: ctx.places.filter((p) => p.group === cat).length });
  }
}
const manifest = { kind: "K07 r8 SYNTHETIC demo scenarios (city-plan-v2)", synthetic: true, label: DEMO.LABEL,
  real_parts: "city_id, bbox (positions are a grid inside it), source_snapshot — from the BUILD slice data.js",
  synthetic_parts: "control points, weights, candidate sites, costs, budget, max_selected, radius — made up for checking the interface; not city statistics, not addresses, not prices",
  generated_by: "research/round-8-results/K07/scripts/make_fixtures.cjs", calc_version: C.CALC_VERSION, metric_version: C.METRIC_VERSION,
  data_js_sha256: crypto.createHash("sha256").update(dataText).digest("hex"), data_generated_by: D.generated_by || null, files };
fs.writeFileSync(path.join(outDir, "MANIFEST.json"), JSON.stringify(manifest, null, 1) + "\n");
console.log(`${files.length} fixtures written to fixtures/`);
