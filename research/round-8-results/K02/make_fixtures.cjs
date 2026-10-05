// K02 r8: генерация фикстур city-plan-v2. Реальные срезы — из data.js сборки (provenance), кандидаты/стоимости — synthetic.
//   node make_fixtures.cjs --app-root <prototypes/city-evidence> --build-sha <sha>
// Каждая фикстура: {provenance, context (city, category, bbox, source_snapshot, sources), scenario}.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const APP = arg("--app-root"), SHA = arg("--build-sha") || "unknown";
const c = {}; vm.createContext(c); c.window = c;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(APP, "web", f), "utf8"), c);
const F = require(path.resolve(APP, "web/facts.js")), X = require(path.resolve(APP, "web/whatif.js")), E = require("./plan_engine.js");
const deps = { F, whatif: X };
const sha = (p) => crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
const OUT = path.join(__dirname, "fixtures"); fs.mkdirSync(OUT, { recursive: true });

function at(bbox, fx, fy) { return { lon: +(bbox[0] + (bbox[2] - bbox[0]) * fx).toFixed(6), lat: +(bbox[1] + (bbox[3] - bbox[1]) * fy).toFixed(6) }; }
function real(name, city, category, pts, cands, rest) {
  const ctx = E.contextFromData(c.CITY_EVIDENCE, city, category, deps);
  const sc = { schema_version: E.SCHEMA, city_id: city, source_snapshot: ctx.source_snapshot, category,
    control_points: pts.map(([id, fx, fy, w]) => ({ id, ...at(ctx.bbox, fx, fy), weight: w })),
    candidates: cands.map(([id, fx, fy, cost]) => ({ id, ...at(ctx.bbox, fx, fy), category, kind: "hypothetical", cost })), ...rest };
  const prov = { kind: "real_slice_with_synthetic_candidates", build_branch: "claude/beautiful-clarke-sbzomj", build_sha: SHA,
    data_js_sha256: sha(path.join(APP, "web/data.js")), whatif_js_sha256: sha(path.join(APP, "web/whatif.js")), release: ctx.release,
    note: "Исходные записи — Overture places среза сборки (не полный реестр города). Кандидаты, веса, стоимости и бюджет — synthetic demo, не тенге и не население." };
  write(name, prov, ctx, sc);
}
function synthetic(name, city, category, sources, pts, cands, rest) {
  const bbox = [10, 10, 10.02, 10.02];
  const sourceRecs = sources.map(([id, fx, fy]) => ({ id, ...at(bbox, fx, fy), name: "synthetic " + id }));
  const snap = "sha256:" + crypto.createHash("sha256").update(JSON.stringify(["synthetic", name, bbox, sourceRecs])).digest("hex");
  const ctx = { city, category, bbox, release: "synthetic", source_snapshot: snap, sources: sourceRecs,
    versions: { schema: E.SCHEMA, metric: E.METRIC, formula: X.FORMULA } };
  const sc = { schema_version: E.SCHEMA, city_id: city, source_snapshot: snap, category,
    control_points: pts.map(([id, fx, fy, w]) => ({ id, ...at(bbox, fx, fy), weight: w })),
    candidates: cands.map(([id, fx, fy, cost]) => ({ id, ...at(bbox, fx, fy), category, kind: "hypothetical", cost })), ...rest };
  write(name, { kind: "synthetic", note: "Полностью синтетическая геометрия в условном квадрате [10,10,10.02,10.02]; city_id нужен схеме, это НЕ данные города." }, ctx, sc);
}
function write(name, provenance, ctx, scenario) {
  E.validatePlanScenario(scenario, ctx);  // фикстура обязана быть валидной
  fs.writeFileSync(path.join(OUT, name + ".json"), JSON.stringify({ name, provenance, context: ctx, scenario }, null, 1) + "\n");
  console.log("wrote", name, "sources", ctx.sources.length);
}

const C = { budget: 0, max_selected: 0, coverage_radius_m: 300, required_ids: [], excluded_ids: [], selected_ids: [] };
real("real_shymkent_school", "shymkent", "school",
  [["двор-север", 0.2, 0.85, 3], ["двор-центр", 0.5, 0.5, 1], ["двор-юг", 0.3, 0.1, 2], ["рынок", 0.8, 0.2, 1], ["парк", 0.9, 0.9, 1], ["остановка", 0.6, 0.7, 2]],
  [["c-sev", 0.22, 0.8, 90], ["c-yug", 0.32, 0.15, 70], ["c-vost", 0.85, 0.25, 60], ["c-park", 0.88, 0.85, 50], ["c-centr", 0.52, 0.55, 120], ["c-zap", 0.05, 0.5, 40]],
  { ...C, budget: 200, max_selected: 3, coverage_radius_m: 300, selected_ids: ["c-centr", "c-zap"] });
real("real_astana_clinic", "astana", "outpatient_clinic",
  [["p1", 0.1, 0.1, 1], ["p2", 0.9, 0.1, 2], ["p3", 0.5, 0.5, 1], ["p4", 0.1, 0.9, 4], ["p5", 0.9, 0.9, 1]],
  [["k-a", 0.12, 0.12, 80], ["k-b", 0.88, 0.12, 60], ["k-c", 0.12, 0.88, 90], ["k-d", 0.88, 0.88, 40], ["k-e", 0.5, 0.45, 30]],
  { ...C, budget: 150, max_selected: 2, coverage_radius_m: 400, required_ids: ["k-d"], excluded_ids: ["k-e"], selected_ids: ["k-a", "k-c"] });
synthetic("synthetic_empty_sources", "shymkent", "school", [],
  [["a", 0.1, 0.1, 1], ["b", 0.9, 0.9, 1], ["c", 0.5, 0.5, 2]],
  [["x", 0.1, 0.12, 10], ["y", 0.9, 0.88, 10], ["z", 0.5, 0.52, 25]],
  { ...C, budget: 30, max_selected: 2, coverage_radius_m: 500, selected_ids: [] });
synthetic("synthetic_infeasible_required", "astana", "school", [["s1", 0.5, 0.5]],
  [["a", 0.2, 0.2, 1], ["b", 0.8, 0.8, 1]],
  [["big", 0.2, 0.2, 500], ["small", 0.8, 0.8, 10]],
  { ...C, budget: 100, max_selected: 2, coverage_radius_m: 200, required_ids: ["big"], selected_ids: ["small"] });
synthetic("synthetic_tie_same_winners", "shymkent", "outpatient_clinic", [["s1", 0.0, 0.0]],
  [["a", 0.5, 0.5, 1]],
  [["t1", 0.45, 0.5, 10], ["t2", 0.55, 0.5, 10]],
  { ...C, budget: 10, max_selected: 1, coverage_radius_m: 1000, selected_ids: ["t2"] });
// Граница радиуса: точка ровно в 300 м к северу от записи (один меридиан) и radius = 300 → after_mm = 300000 должно входить в охват (<=).
(() => {
  const bbox = [10, 10, 10.02, 10.02], src = { id: "s-edge", lon: 10.01, lat: 10.005, name: "synthetic s-edge" };
  const lat = src.lat + (300 / 6371008.8) * 180 / Math.PI;
  const ctx = { city: "astana", category: "outpatient_clinic", bbox, release: "synthetic", sources: [src],
    source_snapshot: "sha256:" + crypto.createHash("sha256").update(JSON.stringify(["synthetic", "radius_boundary", bbox, [src]])).digest("hex"),
    versions: { schema: E.SCHEMA, metric: E.METRIC, formula: X.FORMULA } };
  const sc = { schema_version: E.SCHEMA, city_id: "astana", source_snapshot: ctx.source_snapshot, category: "outpatient_clinic",
    control_points: [{ id: "edge", lon: src.lon, lat, weight: 1 }, { id: "far", lon: 10.019, lat: 10.019, weight: 1 }],
    candidates: [{ id: "k1", lon: 10.018, lat: 10.018, category: "outpatient_clinic", kind: "hypothetical", cost: 5 }],
    budget: 5, max_selected: 1, coverage_radius_m: 300, required_ids: [], excluded_ids: [], selected_ids: [] };
  write("synthetic_radius_boundary", { kind: "synthetic", note: "Точка ровно на расстоянии радиуса: проверка правила <= coverage_radius_m*1000." }, ctx, sc);
})();

