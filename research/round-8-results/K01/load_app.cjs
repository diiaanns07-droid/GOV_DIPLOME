// Headless (no DOM) loader of the prototype slice: web/data.js + web/facts.js from an extracted app root.
const fs = require("fs"), vm = require("vm"), path = require("path");
function loadApp(appRoot) {
  const sandbox = {}; sandbox.window = sandbox; vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(appRoot, "web", "data.js"), "utf8"), sandbox);
  const F = require(path.join(path.resolve(appRoot), "web", "facts.js"));
  return { data: sandbox.CITY_EVIDENCE, F };
}
module.exports = { loadApp };
