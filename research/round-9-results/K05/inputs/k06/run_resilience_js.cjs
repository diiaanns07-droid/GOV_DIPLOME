// K06 round 9 adapter for the BUILD's future web/resilience.js (CORE_SPEC r9 API: validateResilience,
// optimizeResilience(ctx, envelope, options)). Usage:
//   node run_resilience_js.cjs <app-root | module.js> <problems.json> <out.json> [build_sha]
// problems.json: {"cases": {name: {"context": {city_id,bbox,source_snapshot,records}, "envelope": {...}}}}
// If <app-root>/web/resilience.js does not exist, writes {"status": "NOT_RUN", ...} and exits 0 (honest, not a PASS).
const fs = require("fs"), path = require("path");
const [target, probs, out, sha] = process.argv.slice(2);
const mod = target.endsWith(".js") ? path.resolve(target) : path.resolve(target, "web", "resilience.js");
if (!fs.existsSync(mod)) {
  fs.writeFileSync(out, JSON.stringify({ status: "NOT_RUN", reason: "web/resilience.js not found in the given BUILD copy", commit: sha || null, results: {} }));
  console.log("NOT_RUN: web/resilience.js not found"); process.exit(0);
}
const M = require(mod);
const optimize = M.optimizeResilience || (M.default && M.default.optimizeResilience);
const validate = M.validateResilience || (M.default && M.default.validateResilience);
const cases = JSON.parse(fs.readFileSync(probs, "utf8")).cases;
const results = {};
for (const [name, { context, envelope }] of Object.entries(cases)) {
  const ctx = { city_id: context.city_id, bbox: context.bbox, release: null, source_snapshot: context.source_snapshot,
    places: context.records.map((r) => ({ id: r.id, group: r.group, lon: r.lon, lat: r.lat, name: null })),
    records: context.records, versions: { schema: "city-plan-v2", metric: "haversine-mm-v1" } };
  try {
    const env = validate ? validate(JSON.parse(JSON.stringify(envelope)), ctx) : envelope;
    results[name] = optimize(ctx, env, {});
  } catch (e) { results[name] = { status: "error", error_code: e.code || null, error: String(e.message || e).slice(0, 200) }; }
}
fs.writeFileSync(out, JSON.stringify({ status: "RUN", implementation: path.basename(mod), commit: sha || null, results }));
console.log(`${Object.keys(results).length} results -> ${out}`);
