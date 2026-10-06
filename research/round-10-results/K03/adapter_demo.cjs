// K03 r10: пример для BUILD — school-access-case-v1 (synthetic точки и кандидаты, школы из data.js) → матрица и слой маршрутов.
//   node adapter_demo.cjs → runs/adapter_demo.json, examples/<city>_case.json, examples/<city>_routes.geojson
// Это иллюстрация адаптера, не compareCase и не оценка доступности города.
"use strict";
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const R = require("./routing.js"), A = require("./school-access-routing.js");
const sha256hex = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
const fx = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/city_pairs.json"), "utf8"));
fs.mkdirSync(path.join(__dirname, "examples"), { recursive: true });
const out = { note: "origins и candidates — synthetic; schools — Overture/OSM observed_secondary (data.js d2ff344); не прогноз и не оценка доступности", cities: {} };
for (const city of ["shymkent", "astana"]) {
  const g = JSON.parse(fs.readFileSync(path.join(__dirname, `graph/${city}.graph.json`), "utf8"));
  const G = R.prepare(g, { sha256hex });
  const F = fx.cities[city];
  const src = { id: `overture-k10-${city}`, url: null, publisher: "Overture Maps Foundation / OpenStreetMap", title: `K10 segments/connectors ${city}`,
    data_period: g.release, retrieved_at: null, verification_status: "secondary_only", license: "ODbL-1.0", content_sha256: g.inputs.segments.sha256 };
  const kase = {
    schema_version: "school-access-case-v1", case_id: `k03-demo-${city}`, city_id: city, title: `K03 демо: пешеходные расстояния (${city})`,
    bbox: g.bbox, snapshot_id: `graph:${g.graph_sha256.slice(0, 16)}`, sources: [src],
    schools: F.targets.filter((t) => t.kind === "observed_secondary").map((t) => ({ id: t.id, label: t.name, lon: t.lon, lat: t.lat, kind: "observed_secondary",
      source_ids: ["data.js:" + city], field_provenance: { lon: "Overture place geometry", lat: "Overture place geometry" }, qa: [], category: "school",
      access_eligibility: "unknown", capacity: null, capacity_source_ids: [] })),
    origins: F.origins.slice(0, 6).map((o) => ({ id: o.id, label: o.id, lon: o.lon, lat: o.lat, kind: "synthetic", source_ids: [], field_provenance: {}, qa: [] })),
    candidates: F.targets.filter((t) => t.kind === "synthetic").map((t) => ({ id: t.id, label: t.id, lon: t.lon, lat: t.lat, kind: "synthetic", cost: null,
      land_status: "unknown", source_ids: [], field_provenance: {}, qa: [] })),
    selected_candidate_ids: [], parameters: { distance_method: "pedestrian-v1", routing_policy_id: "pedestrian-v1-exploratory", threshold_m: 800, max_new_objects: 1 },
    model_assumptions: ["точки анализа synthetic — не жители и не здания", "маршрут по неполным данным OSM/Overture"],
  };
  fs.writeFileSync(path.join(__dirname, `examples/${city}_case.json`), JSON.stringify(kase, null, 1) + "\n");
  const res = {};
  for (const [method, pol] of [["geodesic", null], ["pedestrian-v1", "pedestrian-v1-strict"], ["pedestrian-v1", "pedestrian-v1-exploratory"]]) {
    const m = A.distanceMatrix({ ...kase, parameters: { ...kase.parameters, distance_method: method, routing_policy_id: pol } }, G);
    const st = {}; for (const r of m.rows) st[r.status] = (st[r.status] || 0) + 1;
    // иллюстрация: ближайшая ШКОЛА для первой точки по строкам ok (unknown не превращается в 0)
    const o0 = kase.origins[0].id, ok = m.rows.filter((r) => r.origin_id === o0 && r.target_role === "school" && r.status === "ok");
    const best = ok.reduce((b, r) => (b === null || r.distance_mm < b.distance_mm ? r : b), null);
    res[pol || method] = { rows: m.rows.length, statuses: st, graph_sha256: m.graph_sha256, policy_sha256: m.policy_sha256,
      first_origin_nearest_school: best ? { target_id: best.target_id, distance_mm: best.distance_mm, text: A.explainRow(best) } : null,
      first_origin_unknown_schools: m.rows.filter((r) => r.origin_id === o0 && r.target_role === "school" && r.status !== "ok").length };
    if (pol === "pedestrian-v1-exploratory")
      fs.writeFileSync(path.join(__dirname, `examples/${city}_routes.geojson`), JSON.stringify(A.routeLayers(m, { origin_id: o0 })) + "\n");
  }
  // отказы адаптера: другой город, лишние точки
  const errs = {};
  for (const [name, bad] of [["other_city", { ...kase, city_id: city === "shymkent" ? "astana" : "shymkent" }],
    ["too_many_points", { ...kase, origins: Array.from({ length: 26 }, (_, i) => ({ ...kase.origins[0], id: "o" + i })) }],
    ["bad_policy", { ...kase, parameters: { ...kase.parameters, routing_policy_id: "pedestrian-v2" } }]]) {
    try { A.distanceMatrix(bad, G); errs[name] = "принято"; } catch (e) { errs[name] = e.code; }
  }
  out.cities[city] = { results: res, adapter_rejects: errs };
}
fs.writeFileSync(path.join(__dirname, "runs/adapter_demo.json"), JSON.stringify(out, null, 1) + "\n");
console.log(JSON.stringify(out, null, 1));
