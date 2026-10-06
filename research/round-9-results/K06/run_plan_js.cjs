// K06 round 9 adapter: run the BUILD's real web/plan.js (validatePlanScenario + optimizePlans) on K06 problems.
// Usage: node run_plan_js.cjs <app-root = extracted prototypes/city-evidence> <problems.json> <out.json> [build_sha]
// problems.json: {"cases": {name: {"context": {city_id, bbox, source_snapshot, records:[{id,lon,lat,group}]}, "scenario": {...}}}}
// The adapter only maps the context shape (records -> places); it never edits plan.js or the expectations.
const fs = require("fs"), path = require("path");
const [appRoot, probs, out, sha] = process.argv.slice(2);
const P = require(path.resolve(appRoot, "web", "plan.js"));
const cases = JSON.parse(fs.readFileSync(probs, "utf8")).cases;
const results = {};
for (const [name, { context, scenario }] of Object.entries(cases)) {
  const ctx = { city_id: context.city_id, bbox: context.bbox, release: null, source_snapshot: context.source_snapshot,
    places: context.records.map((r) => ({ id: r.id, group: r.group, lon: r.lon, lat: r.lat, name: null })),
    versions: { schema: "city-plan-v2", metric: "haversine-mm-v1" } };
  let clean;
  try { clean = P.validatePlanScenario(JSON.parse(JSON.stringify(scenario)), ctx); }
  catch (e) { results[name] = { status: "rejected_by_validation", error_code: e.code || null, error: String(e.message || e).slice(0, 200) }; continue; }
  try { results[name] = P.optimizePlans(ctx, clean, {}); }
  catch (e) { results[name] = { status: "error", error_code: e.code || null, error: String(e.message || e).slice(0, 200) }; }
}
fs.writeFileSync(out, JSON.stringify({ implementation: "prototypes/city-evidence/web/plan.js", commit: sha || null, results }));
console.log(`${Object.keys(results).length} results -> ${out}`);
