// K02 r9: адаптер к НАСТОЯЩЕЙ сборке (web/plan.js) — фикстуры K02 r8 → ctx/scenario BUILD. Без DOM.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const APP = arg("--app-root");
if (!APP) { console.error("нужен --app-root <prototypes/city-evidence>"); process.exit(2); }
const HERE = path.resolve(__dirname, "..");
const F = require(path.resolve(APP, "web/facts.js")), PL = require(path.resolve(APP, "web/plan.js"));
const box = {}; vm.createContext(box); box.window = box;
vm.runInContext(fs.readFileSync(path.join(APP, "web/data.js"), "utf8"), box);
const DATA = box.CITY_EVIDENCE;
const r8 = (n) => JSON.parse(fs.readFileSync(path.join(HERE, "inputs/r8/fixtures", n + ".json"), "utf8"));
const r8exp = (n) => JSON.parse(fs.readFileSync(path.join(HERE, "inputs/r8/expected", n + ".json"), "utf8"));
const variants = () => JSON.parse(fs.readFileSync(path.join(HERE, "inputs/r8/variants.json"), "utf8")).variants;

// Реальные фикстуры — data.js сборки; синтетические — отдельный объект данных (НЕ данные города), тот же формат.
function ctxFor(fx) {
  if (fx.provenance.kind === "synthetic") {
    const c = fx.context, data = { cities: { [c.city]: { bbox: c.bbox, release: "synthetic", files: null,
      places: c.sources.map((s) => ({ id: s.id, lon: s.lon, lat: s.lat, group: c.category, name: s.name })) } } };
    return PL.makeContext(data, c.city, F);
  }
  return PL.makeContext(DATA, fx.context.city, F);
}
function scenarioFor(fx, patch) {
  const ctx = ctxFor(fx);
  const sc = PL.validatePlanScenario({ ...fx.scenario, ...(patch || {}), source_snapshot: ctx.source_snapshot }, ctx);
  return { ctx, sc };
}
function solve(fx, patch) {
  const { ctx, sc } = scenarioFor(fx, patch);
  const man = PL.evaluatePlan(ctx, sc, sc.selected_ids), res = PL.optimizePlans(ctx, sc, { F }), sens = PL.sensitivity(ctx, sc, { F });
  const digest = PL.explanationDigest(sc, man, res, sens, F);
  return { ctx, sc, man, res, sens, digest, text: () => PL.explainPlans(sc, man, res, sens, digest, F).text };
}
const results = [];
function test(id, title, fn) {
  let r; try { r = fn(); } catch (e) { r = { pass: false, observed: "исключение: " + (e.code || "") + " " + e.message }; }
  const status = r.status || (r.pass ? "PASS" : "FAIL");
  results.push({ id, title, status, observed: r.observed });
  console.log(`${status} ${id} — ${title}` + (status === "PASS" ? "" : "\n     observed: " + JSON.stringify(r.observed).slice(0, 500)));
}
function finish(suite, target) {
  const failed = results.filter((r) => r.status === "FAIL").length;
  console.log(`${results.filter((r) => r.status === "PASS").length} PASS, ${failed} FAIL, ${results.filter((r) => !["PASS", "FAIL"].includes(r.status)).length} other of ${results.length}`);
  const out = arg("--json"); if (out) fs.writeFileSync(out, JSON.stringify({ suite, target, node: process.version, results }, null, 1) + "\n");
  process.exit(failed ? 1 : 0);
}
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || "error:" + e.message; } };
module.exports = { F, PL, DATA, r8, r8exp, variants, ctxFor, scenarioFor, solve, test, finish, code, arg, HERE, APP };
