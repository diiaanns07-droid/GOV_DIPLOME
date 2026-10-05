// K03 r8: headless-прогон geo_v2.js (без DOM). node node_runner.cjs <request.json> [<geo_v2.js>]
// request = {app_root, cases: [{id, op: context|validate|table|after, city, category, places?, allow_empty?, selected?}]}
// Печатает JSON-массив [{id, ok, result|error:{code,path}}]. data.js/evidence.js читаются из app_root/web.
"use strict";
const fs = require("fs");
const path = require("path");
const req = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const G = require(path.resolve(process.argv[3] || path.join(__dirname, "geo_v2.js")));
const load = (f) => { const t = fs.readFileSync(path.join(req.app_root, "web", f), "utf8"); return JSON.parse(t.slice(t.indexOf("{"), t.trimEnd().lastIndexOf(";"))); };
const data = req.data || load("data.js"), evidence = req.evidence || load("evidence.js");
const ctxCache = new Map();
const ctxOf = (city, cat) => {
  const k = city + "|" + cat;
  if (!ctxCache.has(k)) ctxCache.set(k, G.buildGeoContext(data, evidence, city, cat));
  return ctxCache.get(k);
};
// NaN/Infinity не выражаются в JSON: в запросе они закодированы {"$num": "NaN" | "Infinity" | "-Infinity"}
const revive = (v) => Array.isArray(v) ? v.map(revive) : v && typeof v === "object"
  ? ("$num" in v && Object.keys(v).length === 1 ? Number(v.$num) : Object.fromEntries(Object.entries(v).map(([k, x]) => [k, revive(x)]))) : v;
const out = [];
for (const c of req.cases) {
  try {
    const ctx = ctxOf(c.city, c.category);
    let result;
    if (c.op === "context") result = ctx;
    else {
      const v = G.validatePlaces(ctx, revive(c.places), { allowEmptyPoints: !!c.allow_empty });
      if (c.op === "validate") result = v;
      else {
        const t = G.distanceTable(ctx, v.control_points, v.candidates);
        result = c.op === "table" ? t : v.control_points.map((_, i) => G.nearestAfter(t, i, c.selected || [], v.candidates));
      }
    }
    out.push({ id: c.id, ok: true, result });
  } catch (e) {
    if (!(e instanceof G.GeoError)) { out.push({ id: c.id, ok: false, crash: String(e && e.stack || e) }); continue; }
    out.push({ id: c.id, ok: false, error: { code: e.code, path: e.path } });
  }
}
process.stdout.write(JSON.stringify(out));
