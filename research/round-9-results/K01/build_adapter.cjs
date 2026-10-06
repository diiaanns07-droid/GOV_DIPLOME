// K01 round 9: headless adapter to the REAL BUILD modules (no DOM). Loads web/data.js, facts.js, whatif.js, plan.js
// (and resilience.js if the BUILD has it) from an extracted app root. Nothing of the BUILD is modified.
const fs = require("fs"), vm = require("vm"), path = require("path");
function loadBuild(appRoot) {
  const web = path.join(path.resolve(appRoot), "web");
  const sandbox = {}; sandbox.window = sandbox; vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(web, "data.js"), "utf8"), sandbox);
  const F = require(path.join(web, "facts.js"));
  const X = require(path.join(web, "whatif.js"));
  const PL = require(path.join(web, "plan.js"));
  const R = fs.existsSync(path.join(web, "resilience.js")) ? require(path.join(web, "resilience.js")) : null;
  const D = sandbox.CITY_EVIDENCE;
  const ctxCache = {};
  const ctxFor = (city) => ctxCache[city] || (ctxCache[city] = PL.makeContext(D, city, F));
  // Browser File.text() decodes UTF-8 with replacement characters (never throws); emulate that for byte inputs.
  const browserText = (bytes) => new TextDecoder("utf-8").decode(bytes);
  function importV2(bytesOrText) {
    const text = typeof bytesOrText === "string" ? bytesOrText : browserText(bytesOrText);
    try { const r = PL.importPlanScenario(text, ctxFor, F); return { ok: true, scenario: r.scenario, city: r.ctx.city_id }; }
    catch (e) { if (e && e.code) return { ok: false, code: e.code, detail: String(e.detail || "").slice(0, 160) }; throw e; }
  }
  function importV1(text) {
    try { const r = X.importScenario(text, D, F); return { ok: true, scenario: r.scenario }; }
    catch (e) { if (e && e.code) return { ok: false, code: e.code }; throw e; }
  }
  return { D, F, X, PL, R, ctxFor, importV2, importV1, browserText };
}
module.exports = { loadBuild };
