// web/whatif.js vs Python reference (tests/expected_whatif.json) + city-whatif-v1 import/export/explain rules.
// Usage: node tests/whatif.cjs   (no dependencies)
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = path.join(__dirname, "..", "web");
const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx, { filename: f });
const F = require(path.join(W, "facts.js"));
const X = require(path.join(W, "whatif.js"));
const D = ctx.CITY_EVIDENCE;
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + detail : "")); };
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || e.message; } };
const close = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) <= 1e-6);

// 1. same numbers as the Python reference (both cities, both categories, project none / near / far / same point)
const exp = JSON.parse(fs.readFileSync(path.join(__dirname, "expected_whatif.json"), "utf8"));
for (const c of exp.cases) {
  const r = X.compute(D.cities[c.city].places, c.category, c.points, c.proposed);
  const ok = r.candidates === c.result.candidates && r.rows.length === c.result.rows.length && r.rows.every((row, i) => {
    const e = c.result.rows[i];
    return row.id === e.id && close(row.before, e.before) && close(row.after, e.after) && close(row.delta, e.delta)
      && close(row.proposed_distance, e.proposed_distance) && row.nearest_before === e.nearest_before && row.nearest_after === e.nearest_after;
  });
  check(`JS = Python ${c.city} ${c.category} ${c.name}`, ok, JSON.stringify(r.rows[0]));
}

// 2. hand geometry and edge cases
const DEG = 2 * Math.PI * X.R_EARTH / 360;
check("1° on the equator = 111195.08 m", Math.abs(X.haversine(0, 0, 1, 0) - DEG) < 1e-6 && Math.abs(DEG - 111195.0802) < 1e-3);
check("antipodes finite (clamp)", Math.abs(X.haversine(0, 0, 180, 0) - Math.PI * X.R_EARTH) < 1e-6);
const P = [{ id: "b", group: "school", lon: 1, lat: 0 }, { id: "a", group: "school", lon: -1, lat: 0 }, { id: "c", group: "outpatient_clinic", lon: 0, lat: 0.5 }];
const pr = (lon, lat, category = "school") => ({ id: "X", lon, lat, category, kind: "hypothetical" });
const one = (places, cat, proposed) => X.compute(places, cat, [{ id: "P", lon: 0, lat: 0 }], proposed).rows[0];
let r = one(P, "school", null);
check("no project: after = before, delta 0, tie -> smaller ID", r.after === r.before && r.delta === 0 && r.nearest_before === "a" && r.nearest_after === "source");
r = one(P, "school", pr(0.25, 0));
check("nearer project: after = project distance", close(r.after, DEG / 4) && close(r.delta, DEG * 0.75) && r.nearest_after === "proposed");
r = one(P, "school", pr(0, 2));
check("farther project: after = before, delta 0", r.after === r.before && r.delta === 0 && r.nearest_after === "source");
r = one(P, "school", pr(0, 0));
check("project at the point: after = 0 (honest zero)", r.after === 0 && close(r.delta, DEG));
r = one(P.filter((p) => p.group !== "school"), "school", pr(0, 1));
check("empty category: before null, delta null, after = project", r.before === null && r.delta === null && close(r.after, DEG));
r = one(P.filter((p) => p.group !== "school"), "school", null);
check("empty category without project: all null", r.before === null && r.after === null && r.delta === null);
check("project of another category rejected", code(() => one(P, "school", pr(0, 0, "outpatient_clinic"))) === "bad_category");
check("unknown category rejected", code(() => one(P, "hospital", null)) === "bad_category");
// move = recompute with the new position; remove = baseline restored exactly
const pts = [{ id: "P", lon: 0, lat: 0 }];
const base = X.compute(P, "school", pts, null).rows[0], moved = X.compute(P, "school", pts, pr(0.5, 0)).rows[0], back = X.compute(P, "school", pts, null).rows[0];
check("move recomputes, remove restores baseline", close(moved.after, DEG / 2) && JSON.stringify(base) === JSON.stringify(back));
// QA coordinates: a colocated Shymkent record is still a candidate (QA flag does not delete it)
const sh = D.cities.shymkent;
const coloc = (ctx.CITY_OBS.cities.shymkent.qa.colocated || [])[0];
if (coloc) {
  const qaSchool = sh.places.find((p) => coloc.ids.includes(p.id) && p.group === "school");
  const rr = X.compute(sh.places, "school", [{ id: "Q", lon: coloc.lon, lat: coloc.lat }], null).rows[0];
  check("QA-colocated school stays a candidate (distance 0)", !!qaSchool && rr.before === 0 && coloc.ids.includes(rr.nearest_before));
} else check("QA-colocated group present in Shymkent", false);

// 3. scenario contract city-whatif-v1
const city = "shymkent", bb = sh.bbox, snap = X.sourceSnapshot(D, city, F);
const cx = (bb[0] + bb[2]) / 2, cy = (bb[1] + bb[3]) / 2;
const sc = () => ({ schema_version: X.SCHEMA, city_id: city, source_snapshot: snap, category: "school",
  control_points: [{ id: "P1", lon: cx, lat: cy }, { id: "P2", lon: bb[0] + 0.001, lat: bb[1] + 0.001 }],
  proposed_object: { id: "X1", lon: cx + 0.002, lat: cy, category: "school", kind: "hypothetical" } });
const txt = X.exportScenario(sc(), D, F);
const imp = X.importScenario(txt, D, F);
check("export -> import round trip", JSON.stringify(imp.scenario) === JSON.stringify(X.validateScenario(sc(), D, F)) && imp.result.rows.length === 2);
check("snapshots differ between cities", X.sourceSnapshot(D, "astana", F) !== snap && /^sha256:[0-9a-f]{64}$/.test(snap));
const tamper = JSON.parse(txt); tamper.derived_results.rows[0].after_m = 1; tamper.derived_results.rows[0].delta_m = 99999;
const imp2 = X.importScenario(JSON.stringify(tamper), D, F);
check("derived values in file ignored, recomputed", JSON.stringify(imp2.result) === JSON.stringify(imp.result));
const rej = (name, mut, want) => {
  const o = sc(); const t = typeof mut === "function" ? JSON.stringify(mut(o) || o) : mut;
  check(`import rejects ${name} (${want})`, code(() => X.importScenario(t, D, F)) === want);
};
rej("NaN", txt.replace(/"lon": [0-9.]+/, '"lon": NaN'), "bad_json");
rej("Infinity", txt.replace(/"lat": [0-9.]+/, '"lat": Infinity'), "bad_json");
rej("1e999", txt.replace(/"lat": [0-9.]+/, '"lat": 1e999'), "bad_json");
rej("-1e999", txt.replace(/"lon": [0-9.]+/, '"lon": -1e999'), "bad_json");
rej("duplicate key", txt.replace('"category": "school",', '"category": "school", "category": "outpatient_clinic",'), "bad_json");
rej("trailing data", txt + "{}", "bad_json");
rej("oversize (>256 KiB)", txt.replace('"schema_version"', `"pad": "${"x".repeat(X.MAX_BYTES)}", "schema_version"`), "too_large");
rej("unknown version", (o) => { o.schema_version = "city-whatif-v2"; }, "bad_version");
rej("unknown city", (o) => { o.city_id = "almaty"; }, "bad_city");
rej("foreign snapshot", (o) => { o.source_snapshot = "sha256:" + "0".repeat(64); }, "foreign_snapshot");
rej("Astana snapshot with Shymkent city", (o) => { o.source_snapshot = X.sourceSnapshot(D, "astana", F); }, "foreign_snapshot");
rej("duplicate point ID", (o) => { o.control_points[1].id = "P1"; }, "duplicate_id");
rej("project ID = point ID", (o) => { o.proposed_object.id = "P1"; }, "duplicate_id");
rej("two projects (array)", (o) => { o.proposed_object = [o.proposed_object, { ...o.proposed_object, id: "X2" }]; }, "too_many_proposed");
rej("unknown field", (o) => { o.url = "https://example.com/x.js"; }, "unknown_field");
rej("extra field in point", (o) => { o.control_points[0].href = "javascript:alert(1)"; }, "bad_shape");
rej("ID with code", (o) => { o.control_points[0].id = "<img src=x onerror=1>"; }, "bad_id");
rej("long ID", (o) => { o.control_points[0].id = "x".repeat(33); }, "bad_id");
rej("point outside bbox", (o) => { o.control_points[0].lon = bb[2] + 0.01; }, "outside_bbox");
rej("project outside bbox", (o) => { o.proposed_object.lat = bb[1] - 0.01; }, "outside_bbox");
rej("coordinate as string", (o) => { o.control_points[0].lat = String(cy); }, "bad_coord");
rej("0 points", (o) => { o.control_points = []; }, "bad_points");
rej("11 points", (o) => { o.control_points = Array.from({ length: 11 }, (_, k) => ({ id: "P" + k, lon: cx, lat: cy })); }, "bad_points");
rej("project category ≠ scenario", (o) => { o.proposed_object.category = "outpatient_clinic"; }, "bad_category");
rej("kind ≠ hypothetical", (o) => { o.proposed_object.kind = "observed"; }, "bad_kind");
rej("missing proposed_object", (o) => { delete o.proposed_object; }, "missing_field");
rej("not an object", "[1,2]", "bad_shape");
check("proposed_object null accepted", code(() => X.importScenario(JSON.stringify({ ...sc(), proposed_object: null }), D, F)) === "accepted");
check("export has no local paths or tokens", !/[A-Za-z]:\\|\/home\/|\/tmp\/|token|secret/i.test(txt));

// 4. explanation: template, digest covers inputs and values, stale request rejected
const s1 = imp.scenario, r1 = imp.result, d1 = X.scenarioDigest(s1, r1, F);
const names = Object.fromEntries(sh.places.map((p) => [p.id, p.name]));
const ex = X.explain(s1, r1, names, d1, F);
check("explanation is a template with units", ex.text.startsWith("Шаблонное объяснение (не LLM)") && / м/.test(ex.text) && !/мин|пешком за/.test(ex.text.replace("не время пешком", "")));
const s2 = { ...s1, proposed_object: { ...s1.proposed_object, lon: s1.proposed_object.lon + 0.001 } };
const r2 = X.compute(sh.places, "school", s2.control_points, s2.proposed_object);
check("digest changes when project moves", X.scenarioDigest(s2, r2, F) !== d1);
check("stale explanation rejected", code(() => X.explain(s2, r2, names, d1, F)) === "stale_scenario");
const s3 = { ...s1, category: "outpatient_clinic", proposed_object: { ...s1.proposed_object, category: "outpatient_clinic" } };
check("digest changes with category", X.scenarioDigest(s3, X.compute(sh.places, s3.category, s3.control_points, s3.proposed_object), F) !== d1);

console.log(fails ? `${fails} FAILED` : "all what-if checks passed");
process.exit(fails ? 1 : 0);
