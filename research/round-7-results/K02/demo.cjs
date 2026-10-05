// K02 r7 demo: пример сценария для обоих городов, ru/kk.  node demo.cjs --app-root <prototypes/city-evidence> [--out examples]
const fs = require("fs"), path = require("path"), vm = require("vm");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const APP = arg("--app-root"), OUT = arg("--out");
const c = {}; vm.createContext(c); c.window = c;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(APP, "web", f), "utf8"), c);
const F = require(path.resolve(APP, "web/facts.js")), Calc = require("./whatif_calc.js"), W = require("./whatif_facts.js");
const deps = { sha256hex: F.sha256hex, PlanError: F.PlanError, validatePlan: F.validatePlan, formatValue: F.formatValue };
const at = (city, fx, fy) => { const b = c.CITY_EVIDENCE.cities[city].bbox; return { lon: +(b[0] + (b[2] - b[0]) * fx).toFixed(6), lat: +(b[1] + (b[3] - b[1]) * fy).toFixed(6) }; };
const scenarios = {
  shymkent_school: { city_id: "shymkent", category: "school", control_points: [{ id: "двор-1", ...at("shymkent", 0.15, 0.2) }, { id: "двор-2", ...at("shymkent", 0.8, 0.75) }, { id: "двор-3", ...at("shymkent", 0.5, 0.5) }],
    proposed_object: { id: "новая-школа", ...at("shymkent", 0.18, 0.22), category: "school", kind: "hypothetical" } },
  astana_outpatient_clinic: { city_id: "astana", category: "outpatient_clinic", control_points: [{ id: "A", ...at("astana", 0.1, 0.9) }, { id: "B", ...at("astana", 0.6, 0.4) }],
    proposed_object: { id: "новая-поликлиника", ...at("astana", 0.12, 0.85), category: "outpatient_clinic", kind: "hypothetical" } },
};
for (const [name, s] of Object.entries(scenarios)) {
  const result = Calc.compute(c.CITY_EVIDENCE, s, F.sha256hex), qa = c.CITY_OBS.cities[s.city_id].qa;
  const ru = W.explain(result, "ru", deps, qa), kk = W.explain(result, "kk", deps, qa);
  console.log(`=== ${name} ===\n${ru.text}\n--- kk (черновик) ---\n${kk.text}\n`);
  if (OUT) { fs.mkdirSync(OUT, { recursive: true }); fs.writeFileSync(path.join(OUT, name + ".json"), JSON.stringify({ scenario: s, calc_result: result, digest: ru.digest, explanation_ru: ru.text, explanation_kk: kk.text, facts_used: ru.facts_used }, null, 1) + "\n"); }
}
