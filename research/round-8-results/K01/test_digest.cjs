// K01 round 8 stage 3: canonical problem/scenario digests. Every variant is checked in JS and in the Python oracle.
//   node test_digest.cjs
const fs = require("fs"), os = require("os"), path = require("path"), crypto = require("crypto"), cp = require("child_process");
const P = require("./planv2.js");
const FX = path.join(__dirname, "fixtures");
const sha256hex = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
const ctxPath = path.join(FX, "real", "context_shymkent.json");
const cx = JSON.parse(fs.readFileSync(ctxPath, "utf8"));
const CTX = { city_id: "shymkent", bbox: cx.bbox, source_snapshot: cx.source_snapshot, sha256hex };
const BASE_TXT = fs.readFileSync(path.join(FX, "synthetic", "shy_valid_clinic_constraints.json"), "utf8");
const base = () => JSON.parse(BASE_TXT);
const rev = (a) => a.slice().reverse();
const shuffleKeys = (o) => Array.isArray(o) ? o.map(shuffleKeys) : o && typeof o === "object"
  ? Object.fromEntries(Object.keys(o).reverse().map((k) => [k, shuffleKeys(o[k])])) : o;

// name -> [text, expectation]; expectation: "same" (both digests equal base), "selected" (problem same, scenario differs),
// "problem" (problem digest differs), or {code}
const V = {};
const J = (o) => JSON.stringify(o, null, 1);
V.base = [BASE_TXT, "same"];
V.perm_points = [J(Object.assign(base(), { control_points: rev(base().control_points) })), "same"];
V.perm_candidates = [J(Object.assign(base(), { candidates: rev(base().candidates) })), "same"];
V.perm_selected = [J(Object.assign(base(), { selected_ids: rev(base().selected_ids) })), "same"];
V.perm_all_keys = [J(shuffleKeys(Object.assign(base(), { control_points: rev(base().control_points), candidates: rev(base().candidates) }))), "same"];
V.compact_whitespace = [JSON.stringify(base()), "same"];
V.bom_prefix = ["﻿" + BASE_TXT, "same"];
V.escaped_keys = [BASE_TXT.replace('"coverage_radius_m"', '"coverage_\\u0072adius_m"').replace('"weight"', '"w\\u0065ight"'), "same"];
V.escaped_id_chars = [BASE_TXT.replace('"cand-02"', '"cand\\u002d02"'), "same"];
V.number_forms = [BASE_TXT.replace('"budget": 12000', '"budget": 1.2e4').replace(/"weight": 1,/, '"weight": 1.0,'), "same"];
V.coord_forms = [BASE_TXT.replace(/"lon": (\d+\.\d+)/, (m, x) => `"lon": ${x}000`), "same"];
V.forged_derived = [J(Object.assign(base(), { derived_results: { status: "optimal", objectives: { mean: { ids: ["cand-04"] } }, problem_digest: "pd1:" + "f".repeat(64) } })), "same"];
V.selected_changed = [J(Object.assign(base(), { selected_ids: ["cand-02"] })), "selected"];
V.selected_empty = [J(Object.assign(base(), { selected_ids: [] })), "selected"];
const ch = (f) => { const o = base(); f(o); return J(o); };
V.budget_changed = [ch((o) => { o.budget += 1; }), "problem"];
V.weight_changed = [ch((o) => { o.control_points[2].weight += 1; }), "problem"];
V.cost_changed = [ch((o) => { o.candidates[3].cost += 1; }), "problem"];
V.radius_changed = [ch((o) => { o.coverage_radius_m += 1; }), "problem"];
V.max_selected_changed = [ch((o) => { o.max_selected = 3; }), "problem"];
V.required_changed = [ch((o) => { o.required_ids = []; }), "problem"];
V.excluded_changed = [ch((o) => { o.excluded_ids = ["cand-04"]; }), "problem"];
V.coord_1e7_changed = [ch((o) => { o.control_points[0].lon = Number((o.control_points[0].lon + 1e-7).toFixed(7)); }), "problem"];
V.point_id_renamed = [ch((o) => { o.control_points[0].id = "cp-00"; }), "problem"];
V.point_added = [ch((o) => { o.control_points.push({ id: "cp-new", lon: o.control_points[0].lon, lat: o.control_points[0].lat, weight: 1 }); }), "problem"];
V.cyrillic_id = [BASE_TXT.replace('"cp-01"', '"тчк-01"'), { code: "bad_id" }];
V.lone_surrogate_id = [BASE_TXT.replace('"cp-01"', '"cp\\ud800"'), { code: "bad_id" }];
V.zero_width_id = [BASE_TXT.replace('"cp-01"', '"cp-01\\u200b"'), { code: "bad_id" }];
V.dup_key_escaped = [BASE_TXT.replace('"budget": 12000', '"budget": 12000, "\\u0062udget": 1'), { code: "duplicate_key" }];
V.proto_key = [BASE_TXT.replace('"budget": 12000', '"budget": 12000, "__proto__": {"x": 1}'), { code: "unknown_field" }];

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "k01r8d-"));
let pass = 0, fail = 0;
try {
  for (const [n, [txt]] of Object.entries(V)) fs.writeFileSync(path.join(tmp, n + ".json"), txt, "utf8");
  const py = JSON.parse(cp.execFileSync("python3", [path.join(__dirname, "planv2_ref.py"), "batch-dir", tmp, ctxPath], { encoding: "utf8" }));
  const js = {};
  for (const [n, [txt]] of Object.entries(V)) {
    try { const r = P.importPlan(new Uint8Array(Buffer.from(txt, "utf8")), CTX); js[n] = { valid: true, problem_digest: P.problemDigest(r.scenario, CTX), scenario_digest: P.scenarioDigest(r.scenario, CTX) }; }
    catch (e) { if (!(e instanceof P.PlanV2Error)) throw e; js[n] = { valid: false, code: e.code }; }
  }
  const b = js.base;
  for (const [n, [, exp]] of Object.entries(V)) {
    const g = js[n]; let ok, why = "";
    if (JSON.stringify(g) !== JSON.stringify(py[n + ".json"])) { ok = false; why = `JS ${JSON.stringify(g)} != Python ${JSON.stringify(py[n + ".json"])}`; }
    else if (exp === "same") ok = g.valid && g.problem_digest === b.problem_digest && g.scenario_digest === b.scenario_digest;
    else if (exp === "selected") ok = g.valid && g.problem_digest === b.problem_digest && g.scenario_digest !== b.scenario_digest;
    else if (exp === "problem") ok = g.valid && g.problem_digest !== b.problem_digest && g.scenario_digest !== b.scenario_digest;
    else ok = !g.valid && g.code === exp.code;
    if (!ok && !why) why = JSON.stringify(g);
    ok ? pass++ : fail++;
    console.log(ok ? "PASS" : "FAIL", `digest ${n} (${typeof exp === "string" ? exp : exp.code})`, why);
  }
  // snapshot / city / category always enter the problem digest
  const sc = P.importPlan(BASE_TXT, CTX).scenario;
  const d0 = P.problemDigest(sc, CTX);
  const other = [Object.assign({}, sc, { source_snapshot: "sha256:" + "1".repeat(64) }), Object.assign({}, sc, { city_id: "astana" }), Object.assign({}, sc, { category: "school" })];
  const okOther = other.every((s) => P.problemDigest(s, CTX) !== d0);
  okOther ? pass++ : fail++; console.log(okOther ? "PASS" : "FAIL", "digest covers source_snapshot, city_id, category");
  const okFmt = /^pd1:[0-9a-f]{64}$/.test(d0) && /^sd1:[0-9a-f]{64}$/.test(P.scenarioDigest(sc, CTX));
  okFmt ? pass++ : fail++; console.log(okFmt ? "PASS" : "FAIL", "digest format pd1:/sd1: + sha256 hex");
} finally { fs.rmSync(tmp, { recursive: true }); }
console.log(`\n${pass} passed, ${fail} failed, 0 skipped`);
process.exitCode = fail ? 1 : 0;
