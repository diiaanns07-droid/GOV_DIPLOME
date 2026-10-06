// K08 R9: CLI отчёта устойчивости поверх BUILD. Usage:
//   node resilience_cli.cjs --app-root APP --in ENVELOPE.json --out-dir DIR   -> DIR/report.json, DIR/report.html
//   node resilience_cli.cjs --app-root APP --in ENVELOPE.json --check          -> только валидация (exit 2 при отказе)
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const arg = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };
const APP = path.resolve(arg("--app-root")), W = path.join(APP, "web");
const c0 = {}; vm.createContext(c0); c0.window = c0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), c0, { filename: f });
const deps = { PL: require(path.join(W, "plan.js")), F: require(path.join(W, "facts.js")), X: require(path.join(W, "whatif.js")),
  data: c0.CITY_EVIDENCE, obs: c0.CITY_OBS || null };
const RR = require("./resilience_report.js");
const text = fs.readFileSync(arg("--in"));
let env;
try { env = RR.validateResilience(text.toString("utf8"), deps); }
catch (e) { console.log(JSON.stringify({ status: "rejected", code: e.code || "exception", detail: String(e.detail || e.message).slice(0, 300) })); process.exit(2); }
if (process.argv.includes("--check")) { console.log(JSON.stringify({ status: "valid", cases: env.cases.length })); process.exit(0); }
const rep = RR.buildResilienceReport(env, deps);
const out = arg("--out-dir"); fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(path.join(out, "report.json"), JSON.stringify(rep, null, 1) + "\n");
fs.writeFileSync(path.join(out, "report.html"), RR.renderResilienceHtml(rep));
console.log(JSON.stringify({ status: rep.search.status, nominal: rep.plans.nominal && rep.plans.nominal.selected_ids, robust: rep.plans.robust && rep.plans.robust.selected_ids,
  price_m: rep.price_of_robustness_m, reason: rep.price_reason, robust_worst: rep.plans.robust && rep.plans.robust.worst_case_ids }));
