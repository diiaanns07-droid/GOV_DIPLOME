// K12 round 9, stage 3: ID order at exact ties — JS string order (UTF-16 code units; plan.js / resilience.js `a < b`)
// vs Python sorted() (code points), for IDs that BUILD accepts (\p{L}, NFC). Only IDs from U+E000–U+FFFF compared with
// IDs above U+FFFF differ: "ﬀ" (ﬀ) < "\u{1D538}" (𝔸) by code points, but "\u{1D538}" < "ﬀ" in UTF-16.
// Runs the ACTUAL build's JS and the build's own Python oracles (tools/plan_oracle.py, tools/resilience_oracle.py —
// pure solve() functions, read before use) plus the K12 oracles on the same SYNTHETIC tie (two identical candidates).
//   node id_order_probe.cjs --app-root <copy> [--python python3] [--out r.json]
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const { spawnSync } = require("child_process");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const APP = path.resolve(opt("--app-root", "")), PY = opt("--python", "python3"), OUT = opt("--out");
const HERE = __dirname, W = path.join(APP, "web");
const c0 = {}; vm.createContext(c0); c0.window = c0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), c0, { filename: f });
const D = c0.CITY_EVIDENCE, F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js"));
const RS = fs.existsSync(path.join(W, "resilience.js")) ? require(path.join(W, "resilience.js")) : null;
const ctx = PL.makeContext(D, "shymkent", F), bb = ctx.bbox;
const A = "ﬀ", B = "\u{1D538}";                       // both \p{L}, NFC; same position, same cost -> exact tie
const at = [+(bb[0] + 0.4 * (bb[2] - bb[0])).toFixed(6), +(bb[1] + 0.5 * (bb[3] - bb[1])).toFixed(6)];
const plan = { schema_version: "city-plan-v2", city_id: "shymkent", source_snapshot: ctx.source_snapshot, category: "school",
  control_points: [{ id: "p1", lon: +(at[0] + 0.0004).toFixed(6), lat: at[1], weight: 1 }],
  candidates: [A, B].map((id) => ({ id, lon: at[0], lat: at[1], category: "school", kind: "hypothetical", cost: 100 })),
  budget: 100, max_selected: 1, coverage_radius_m: 500, required_ids: [], excluded_ids: [], selected_ids: [] };
const src = ctx.places.filter((p) => p.group === "school").map((p) => p.id).sort();
const cases = [{ id: `${A}1`, label: "Случай ﬀ", disabled_source_ids: src.slice() }, { id: `${B}1`, label: "Случай 𝔸", disabled_source_ids: src.slice() }];
const env = { schema_version: "city-resilience-v1", plan, cases };

const js = { v2_mean: PL.optimizePlans(ctx, plan, { F }).objectives.mean.ids };
if (RS) { const r = RS.optimizeResilience(ctx, env, { F }); Object.assign(js, { rs_nominal: r.nominal.selected_ids, rs_robust: r.robust.selected_ids, rs_worst_case_ids: r.robust.worst_case_ids }); }
const places = ctx.places.map((p) => ({ id: p.id, group: p.group, lon: p.lon, lat: p.lat }));
const pyScript = `
import importlib.util, json, sys
inp = json.loads(sys.stdin.read())
def load(name, file):                       # explicit paths: BUILD and K12 oracles share module names
    spec = importlib.util.spec_from_file_location(name, file); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m
BP = load("build_plan_oracle", inp["app_tools"] + "/plan_oracle.py")
out = {"build_plan_oracle_v2_mean": BP.solve(inp["places"], inp["plan"])["optimize"]["objectives"]["mean"]["ids"]}
import os
if os.path.exists(inp["app_tools"] + "/resilience_oracle.py"):
    BR = load("build_rs_oracle", inp["app_tools"] + "/resilience_oracle.py")
    r = BR.solve(inp["places"], inp["plan"], inp["cases"])["optimize"]
    out.update(build_rs_oracle_nominal=r["nominal"]["ids"], build_rs_oracle_robust=r["robust"]["ids"], build_rs_oracle_worst_case_ids=r["robust"]["worst_case_ids"])
K8 = load("k12_r8_plan_oracle", inp["k12_r8"] + "/plan_v2_oracle.py")
out["k12_r8_oracle_v2_mean"] = K8.solve(dict(inp["plan"]), inp["places"])["objectives"]["mean"]["selected_ids"]
print(json.dumps(out, ensure_ascii=True))
`;
const r = spawnSync(PY, ["-c", pyScript], { input: JSON.stringify({ app_tools: path.join(APP, "tools"), k12_r8: path.join(HERE, "..", "..", "round-8-results", "K12", "oracle"),
  k12_r9: path.join(HERE, "oracle"), places, plan, cases }), encoding: "utf8", timeout: 60000 });
if (r.status !== 0) { console.error(String(r.stderr).slice(0, 600)); process.exit(1); }
const py = JSON.parse(r.stdout);
// K12 r9 resilience oracle (UTF-16 order) through its stdin mode
const k9 = spawnSync(PY, [path.join(HERE, "oracle", "resilience_oracle.py"), "--app-root", APP, "--stdin", "solve"],
  { input: JSON.stringify({ ...env, plan: { ...plan, source_snapshot: "__SNAPSHOT__" } }), encoding: "utf8", timeout: 60000 });
const k9r = JSON.parse(k9.stdout).result;
py.k12_r9_oracle_nominal = k9r.nominal.ids; py.k12_r9_oracle_robust = k9r.robust.ids; py.k12_r9_oracle_worst_case_ids = k9r.robust.worst_case_ids;
const esc = (x) => JSON.stringify(x).replace(/[\u007f-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
const rows = [
  ["v2 mean", js.v2_mean, py.build_plan_oracle_v2_mean, py.k12_r8_oracle_v2_mean],
  ["resilience nominal", js.rs_nominal, py.build_rs_oracle_nominal, py.k12_r9_oracle_nominal],
  ["resilience robust", js.rs_robust, py.build_rs_oracle_robust, py.k12_r9_oracle_robust],
  ["resilience worst_case_ids", js.rs_worst_case_ids, py.build_rs_oracle_worst_case_ids, py.k12_r9_oracle_worst_case_ids],
].map(([what, jsv, buildPy, k12]) => ({ what, build_js: jsv, build_python_oracle: buildPy, k12_oracle: k12,
  build_js_eq_build_oracle: JSON.stringify(jsv) === JSON.stringify(buildPy), build_js_eq_k12_oracle: JSON.stringify(jsv) === JSON.stringify(k12) }));
for (const x of rows) console.log(`${x.what.padEnd(26)} JS ${esc(x.build_js)}  BUILD-py ${esc(x.build_python_oracle)}  K12 ${esc(x.k12_oracle)}  JS=BUILD-py:${x.build_js_eq_build_oracle} JS=K12:${x.build_js_eq_k12_oracle}`);
const summary = { app_root: path.basename(APP), ids: { A: "U+FB00", B: "U+1D538" }, rows,
  note: "exact tie (same place, same cost); differences are ordering conventions, not wrong distances" };
if (OUT) fs.writeFileSync(OUT, JSON.stringify(summary, null, 1) + "\n");
