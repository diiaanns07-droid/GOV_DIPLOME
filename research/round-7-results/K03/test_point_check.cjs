// K03 round 7: прогон point_check.js на fixtures.json; печатает JSON-массив результатов (сравнивает test_point_check.py).
// node test_point_check.cjs <fixtures.json> [<point_check.js>]
"use strict";
const fs = require("fs");
const path = require("path");
const fxPath = process.argv[2];
const helper = require(path.resolve(process.argv[3] || path.join(__dirname, "point_check.js")));
const doc = JSON.parse(fs.readFileSync(fxPath, "utf8"));
// JSON.parse не принимает NaN/Infinity: подставляем их вручную, как мог бы сделать нестрогий источник
function parseRaw(text) {
  const t = text.replace(/-Infinity\b/g, '"__NINF__"').replace(/\bInfinity\b/g, '"__INF__"').replace(/\bNaN\b/g, '"__NAN__"');
  return JSON.parse(t, (k, v) => (v === "__NAN__" ? NaN : v === "__INF__" ? Infinity : v === "__NINF__" ? -Infinity : v));
}
const out = [];
for (const f of doc.fixtures) {
  const base = doc.slices[f.city];
  const slice = Object.assign({}, base, f.slice_override || {});
  const others = Object.values(doc.slices).filter((s) => s.city_id !== f.city);
  const point = f.raw_json !== null ? parseRaw(f.raw_json) : f.point;
  const r = helper.checkPoint(slice, point, others);
  out.push({ id: f.id, ok: r.ok, code: r.code, point: r.point, on_edge: r.on_edge, other_city_id: r.other_city_id || null });
}
process.stdout.write(JSON.stringify(out));
