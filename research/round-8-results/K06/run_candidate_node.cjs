// K06 round 8: run another implementation's optimizePlans over exported problems and write --candidate-json.
// Usage: node run_candidate_node.cjs <module.js> <problems_for_js.json> <out.json> [commit_sha]
// <module.js> must export optimizePlans(context, scenario) (sync or returning a Promise), JSON-compatible result.
// The harness never edits the module; a throw is recorded as {"status": "error"} and will be a FAIL in comparison.
const fs = require("fs"), path = require("path");
(async () => {
  const [mod, probs, out, commit] = process.argv.slice(2);
  const impl = require(path.resolve(mod));
  const optimize = impl.optimizePlans || (impl.default && impl.default.optimizePlans);
  if (typeof optimize !== "function") throw new Error("module does not export optimizePlans");
  const cases = JSON.parse(fs.readFileSync(probs, "utf8")).cases;
  const results = {};
  for (const [name, { context, scenario }] of Object.entries(cases)) {
    try { results[name] = await optimize(context, scenario); }
    catch (e) { results[name] = { status: "error", error: String(e && e.message || e) }; }
  }
  fs.writeFileSync(out, JSON.stringify({ implementation: path.basename(mod), commit: commit || null, results }));
  console.log(`${Object.keys(results).length} results -> ${out}`);
})().catch((e) => { console.error(e); process.exit(2); });
