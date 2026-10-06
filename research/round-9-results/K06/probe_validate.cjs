// K06 r9: run plan.js validatePlanScenario on probe inputs. node probe_validate.cjs <app-root> <probes.json> <out.json>
const fs = require("fs"), path = require("path");
const [appRoot, inp, out] = process.argv.slice(2);
const P = require(path.resolve(appRoot, "web", "plan.js"));
const probes = JSON.parse(fs.readFileSync(inp, "utf8"));
const res = {};
for (const [name, { context, scenario }] of Object.entries(probes)) {
  const ctx = { city_id: context.city_id, bbox: context.bbox, release: null, source_snapshot: context.source_snapshot,
    places: context.records.map((r) => ({ id: r.id, group: r.group, lon: r.lon, lat: r.lat, name: null })) };
  try { P.validatePlanScenario(scenario, ctx); res[name] = { accepted: true }; }
  catch (e) { res[name] = { accepted: false, code: e.code || null }; }
}
fs.writeFileSync(out, JSON.stringify(res, null, 1));
