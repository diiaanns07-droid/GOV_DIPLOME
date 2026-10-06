// K05 r10: build school-access-case-v1 packages for Shymkent and Astana from the BUILD's committed data.js
// (REAL Overture/OSM school records, observed_secondary) with SYNTHETIC analysis points and HYPOTHETICAL candidates A/B,
// a geodesic matrix (BUILD haversine-mm-v1: whatif.haversine + plan.mmOf), and run compareCase.
// Usage: node make_city_cases.cjs <patched govtech dir (school-compare.js + core/)> <out dir> <code_sha>
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const [gt, outDir, sha] = process.argv.slice(2);
const core = path.join(gt, "core");
const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(core, f), "utf8"), ctx, { filename: f });
const X = require(path.join(core, "whatif.js")), PL = require(path.join(core, "plan.js")), SC = require(path.resolve(gt, "school-compare.js"));
const dataSha = crypto.createHash("sha256").update(fs.readFileSync(path.join(core, "data.js"))).digest("hex");
const D = ctx.CITY_EVIDENCE, E = ctx.CITY_OBS;

for (const city of ["shymkent", "astana"]) {
  const C = D.cities[city], bb = C.bbox, qa = E.cities[city].qa;
  const qaOf = (id) => [
    ...(qa.colocated || []).filter((g) => g.ids.includes(id)).map(() => "COLOCATED"),
    ...(qa.possible_duplicates || []).filter((p) => p.a === id || p.b === id).map(() => "POSSIBLE_DUPLICATE"),
    ...(qa.category_doubt && qa.category_doubt[id] ? ["CATEGORY_DOUBT:" + qa.category_doubt[id].rule] : [])];
  const srcData = { id: `src:${city}:overture-places-${C.release}`, url: null, publisher: "Overture Maps Foundation (агрегат OSM/Meta/Foursquare и др.)",
    title: `places_social ${city}, срез K10 2×2 км, выпуск ${C.release}`, published_at: null, data_period: C.release,
    retrieved_at: C.retrieved_utc, verification_status: "secondary_only", license: "per record: " + [...new Set(C.places.flatMap((p) => p.sources.map((s) => s.license)))].sort().join(", "),
    content_sha256: C.files.places_social.sha256 };
  const srcBuild = { id: "src:build-data-js", url: null, publisher: "GOV_DIPLOME BUILD", title: "web/govtech/core/data.js @ " + sha, published_at: null, data_period: null,
    retrieved_at: null, verification_status: "secondary_only", license: "derived from the records above", content_sha256: dataSha };
  const srcK05 = { id: "src:k05-synthetic", url: null, publisher: "K05 round 10", title: "synthetic analysis points and hypothetical candidate sites", published_at: null,
    data_period: null, retrieved_at: null, verification_status: "not_fetched", license: "unknown" };
  const schools = C.places.filter((p) => p.group === "school").map((p) => ({ id: p.id, label: p.name || "Без названия", lon: p.lon, lat: p.lat,
    kind: "observed_secondary", source_ids: [srcData.id, srcBuild.id], field_provenance: { lon: "Overture geometry (OSM/вторичные)", lat: "Overture geometry (OSM/вторичные)",
      label: "Overture names.primary — не официальное название", category: "Overture taxonomy → правило K10 social_group" },
    qa: qaOf(p.id), category: "school", access_eligibility: "unknown", capacity: null, capacity_source_ids: [] }));
  // SYNTHETIC analysis points: 3 x 4 grid of cell centres inside the bbox (not homes, not residents)
  const origins = [];
  for (let r = 0; r < 3; r++) for (let q = 0; q < 4; q++) origins.push({ id: `pt-${r}${q}`, label: `Точка ${r * 4 + q + 1}`,
    lon: +(bb[0] + (q + 0.5) / 4 * (bb[2] - bb[0])).toFixed(6), lat: +(bb[1] + (r + 0.5) / 3 * (bb[3] - bb[1])).toFixed(6),
    kind: "synthetic", source_ids: [srcK05.id], field_provenance: { lon: "центр ячейки сетки 3×4 участка", lat: "центр ячейки сетки 3×4 участка" }, qa: [] });
  const dmm = (a, b) => PL.mmOf(X.haversine(a.lon, a.lat, b.lon, b.lat));
  const nearestNow = (o) => Math.min(...schools.map((s) => dmm(o, s)));
  const worst = origins.slice().sort((a, b) => nearestNow(b) - nearestNow(a) || (a.id < b.id ? -1 : 1))[0];
  const cand = (id, label, lon, lat, rule) => ({ id, label, lon, lat, kind: "hypothesis", source_ids: [srcK05.id],
    field_provenance: { lon: rule, lat: rule }, qa: [], cost: null, land_status: "unknown" });
  const candidates = [
    cand("cand-A", "Вариант A (гипотеза)", worst.lon, worst.lat, `правило K05: точка анализа ${worst.id}, сейчас дальше всех от известных школ`),
    cand("cand-B", "Вариант B (гипотеза)", +((bb[0] + bb[2]) / 2).toFixed(6), +((bb[1] + bb[3]) / 2).toFixed(6), "правило K05: центр участка")];
  const kase = { schema_version: "school-access-case-v1", case_id: `${city}-schools-k05-r10`, city_id: city,
    title: `Доступность школ: участок ${city === "shymkent" ? "Шымкента" : "Астаны"} (демо K05)`, bbox: bb, snapshot_id: `k10-r3:${C.files.places_social.sha256.slice(0, 16)}@${C.release}`,
    sources: [srcData, srcBuild, srcK05], schools, origins, candidates, selected_candidate_ids: ["cand-A", "cand-B"],
    parameters: { distance_method: "geodesic", routing_policy_id: null, threshold_m: 500, max_new_objects: 1 },
    model_assumptions: ["Расстояние по прямой (geodesic, haversine-mm-v1), не пеший маршрут",
      "Школы — записи Overture внутри участка; буфер за краем участка НЕ включён: у точек у края ближайшая школа может быть снаружи",
      "Точки анализа — синтетическая сетка 3×4, равновесные; не жители и не ученики",
      "Кандидаты A/B — гипотетические места по правилу K05, статус земли неизвестен, стоимость неизвестна",
      "Порог 500 м — параметр анализа, не норматив", "Доступ (общедоступная/ограниченная) у всех школ неизвестен"] };
  const entries = [];
  for (const o of origins) for (const t of [...schools, ...candidates]) entries.push({ origin_id: o.id, target_id: t.id, distance_mm: dmm(o, t), status: "ok",
    method: "geodesic", policy_id: null, route_edge_ids: [], geometry: null, assumptions: ["прямая линия"] });
  const matrix = { method: "geodesic", policy_id: null, entries };
  const out = SC.compareCase(kase, matrix);
  out.code_sha = sha; out.generated_by = "research/round-10-results/K05/cases/make_city_cases.cjs";
  const dir = path.join(outDir, city); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "case.json"), JSON.stringify(kase, null, 1) + "\n");
  fs.writeFileSync(path.join(dir, "matrix.json"), JSON.stringify(matrix) + "\n");
  fs.writeFileSync(path.join(dir, "compare.json"), JSON.stringify(out, null, 1) + "\n");
  fs.writeFileSync(path.join(dir, "facts.json"), JSON.stringify({ case_id: kase.case_id, case_digest: out.case_digest, code_sha: sha, facts: out.facts }, null, 1) + "\n");
  const s = (id) => out.plans.find((p) => p.plan_id === id);
  const fm = (v) => (v === null ? "нет данных" : Math.round(v / 1000) + " м");
  console.log(city, "schools", schools.length, "| current mean", fm(s("current").metrics.mean_distance_mm), "max", fm(s("current").metrics.max_distance_mm),
    "within", s("current").metrics.within_threshold_count, "| A mean", fm(s("candidate:cand-A").metrics.mean_distance_mm), "max", fm(s("candidate:cand-A").metrics.max_distance_mm),
    "within", s("candidate:cand-A").metrics.within_threshold_count, "| B mean", fm(s("candidate:cand-B").metrics.mean_distance_mm), "max", fm(s("candidate:cand-B").metrics.max_distance_mm),
    "within", s("candidate:cand-B").metrics.within_threshold_count, "| auto", s("auto:contract-lex").selected_candidate_ids, "minimax", s("auto:minimax").selected_candidate_ids);
}
