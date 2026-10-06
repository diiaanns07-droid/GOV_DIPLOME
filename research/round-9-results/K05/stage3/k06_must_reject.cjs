/* K06 must_reject (16) через validateResilience модуля K05. Решение (принять/отклонить) должно совпасть;
 * имена кодов сравниваются отдельно (разные имена при одинаковом решении = API_POLICY, не математика).
 *   node k06_must_reject.cjs <app-root с web/resilience.js> <resilience_gold.json> [OUT.json] */
"use strict";
const fs = require("node:fs"), path = require("node:path");
const [app, fx, out] = process.argv.slice(2);
const RS = require(path.resolve(app, "web", "resilience.js"));
const mr = JSON.parse(fs.readFileSync(fx, "utf8")).must_reject, c = mr.context;
const ctx = { city_id: c.city_id, bbox: c.bbox, release: null, source_snapshot: c.source_snapshot,
  places: c.records.map((r) => ({ id: r.id, group: r.group, lon: r.lon, lat: r.lat, name: null })), versions: {} };
const rows = mr.items.map((it) => {
  let got; try { RS.validateResilience(JSON.parse(JSON.stringify(it.envelope)), ctx); got = "accepted"; } catch (e) { got = e.code || String(e); }
  return { case: it.case, k06_code: it.k06_code, k05_code: got, rejected_both: got !== "accepted", same_code: got === it.k06_code };
});
for (const r of rows) console.log(`${r.rejected_both ? "REJECTED" : "ACCEPTED!"} ${r.case}: K06=${r.k06_code} K05=${r.k05_code}${r.same_code ? "" : " (API_POLICY: имя кода)"}`);
const sum = { items: rows.length, rejected_by_k05: rows.filter((r) => r.rejected_both).length, same_code: rows.filter((r) => r.same_code).length };
console.log(JSON.stringify(sum));
if (out) fs.writeFileSync(out, JSON.stringify({ summary: sum, rows }, null, 1) + "\n");
process.exit(sum.rejected_by_k05 === sum.items ? 0 : 1);
