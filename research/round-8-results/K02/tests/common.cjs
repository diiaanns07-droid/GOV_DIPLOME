// Общая загрузка: модули сборки (--app-root) + модули K02 + фикстуры. Без DOM.
const fs = require("fs"), path = require("path");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const APP = arg("--app-root");
if (!APP) { console.error("нужен --app-root <prototypes/city-evidence>"); process.exit(2); }
const HERE = path.resolve(__dirname, "..");
const F = require(path.resolve(APP, "web/facts.js")), X = require(path.resolve(APP, "web/whatif.js"));
const E = require(path.join(HERE, "plan_engine.js")), P = require(path.join(HERE, "plan_facts.js"));
const deps = { F, whatif: X };
const fixture = (n) => JSON.parse(fs.readFileSync(path.join(HERE, "fixtures", n + ".json"), "utf8"));
function solve(fx, patch) {
  const ctx = fx.context, sc = E.validatePlanScenario({ ...fx.scenario, ...(patch || {}) }, ctx);
  const opt = E.optimizePlans(ctx, sc, deps), man = E.evaluatePlan(ctx, sc, sc.selected_ids, deps), base = E.evaluatePlan(ctx, sc, [], deps);
  return { ctx, sc, opt, man, base, built: P.buildPlanCatalog(ctx, sc, man, base, opt, deps) };
}
const results = [];
function test(id, title, fn) {
  let r; try { r = fn(); } catch (e) { r = { pass: false, observed: "исключение: " + (e.code || "") + " " + e.message }; }
  results.push({ id, title, pass: !!r.pass, observed: r.observed });
  console.log(`${r.pass ? "PASS" : "FAIL"} ${id} — ${title}` + (r.pass ? "" : "\n     observed: " + JSON.stringify(r.observed).slice(0, 400)));
}
function finish(name) {
  const failed = results.filter((r) => !r.pass).length;
  console.log(failed ? `${failed} FAILED of ${results.length}` : `all ${results.length} passed`);
  const out = arg("--json"); if (out) fs.writeFileSync(out, JSON.stringify({ suite: name, app_root: "<" + path.basename(path.resolve(APP)) + ">", node: process.version, results }, null, 1) + "\n");
  process.exit(failed ? 1 : 0);
}
function attempt(fn) { try { return { status: "accepted", value: fn() }; } catch (e) { return { status: e.code || "error", message: e.message }; } }
module.exports = { F, X, E, P, deps, fixture, solve, test, finish, attempt, APP, HERE };
