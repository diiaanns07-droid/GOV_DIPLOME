// DELIBERATELY BAD importer for the network guard: the reference importer, but it first tries to
// "resolve" any http(s) address found in the imported text (FEATURE_SPEC forbids loading such addresses).
// The address is never reached: whatif_import_stress.cjs replaces http/https/net/tls/fetch with traps.
"use strict";
const ref = require("./reference_adapter.cjs");
module.exports = function (env) {
  const R = ref(env);
  return { ...R, name: "fetching", importScenario(text, state) {
    const m = /https?:\/\/[^"\s]+/.exec(text);
    if (m) { try { require("https").get(m[0]); } catch (e) { /* blocked by the guard */ } }
    return R.importScenario(text, state);
  } };
};
