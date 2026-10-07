/* Minimal same-origin api.request for the stand's `?api=real` mode (R02 read-only run).
 * Mirrors the R01 shell semantics that matter to CivicMap: relative path under
 * /api/civic/v1, envelope unwrapping, errors as {status, code}, optional {signal}.
 * GET only: the public map never writes. Not a replacement for R01's api.request.
 */
(function () {
  "use strict";
  window.R03CreateFetchApi = function (base) {
    const calls = [];
    async function request(method, path, body, options) {
      calls.push({ method, path });
      if (method !== "GET") throw Object.assign(new Error("read-only"), { status: 0, code: "bad_method" });
      let res;
      try {
        res = await fetch(base + path, { method, headers: { Accept: "application/json" }, credentials: "same-origin",
          cache: "no-store", redirect: "error", signal: options && options.signal });
      } catch (e) {
        throw Object.assign(new Error("network"), { status: 0, code: e && e.name === "AbortError" ? "aborted" : "network" });
      }
      let env = null;
      try { env = await res.json(); } catch (e) { env = null; }
      if (!env || typeof env.ok !== "boolean") throw Object.assign(new Error("bad response"), { status: res.status, code: "bad_response" });
      if (!env.ok || !res.ok) {
        const er = env.error && typeof env.error === "object" ? env.error : {};
        throw Object.assign(new Error(typeof er.message === "string" ? er.message : "error"), { status: res.status, code: String(er.code || "error") });
      }
      return env.data;
    }
    return { request, calls, options: { slow: {} } };
  };
})();
