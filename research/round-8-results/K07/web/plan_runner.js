/* K07 round 8 — chunked runner for optimizePlans (CORE_SPEC «UI не блокируется»).
 * Runs engine.createSearch(ctx, scenario).step(chunk) between event-loop turns (setTimeout), reports progress from the
 * number of examined subsets, supports cancel. Every run has a request_id and the problem_digest of its input; the UI
 * applies a result only if both still match (a newer run or changed parameters make it stale).
 * A Worker is not used: the viewer runs from file://, where Chromium refuses module/worker scripts from disk.
 * An engine without createSearch is run by one optimizePlans() call (no intermediate progress; said in the result).
 * Browser: window.CITY_PLAN_RUNNER; Node: module.exports.
 */
(function (root) {
  "use strict";
  let seq = 0;
  // opts: chunk (subsets per turn, default 2048), delayMs (pause between turns, default 0; tests slow it down),
  // onProgress({request_id, evaluated, total}), onDone(result + request_id). Returns {request_id, problem_digest, cancel}.
  function start(engine, ctx, scenario, opts = {}) {
    const request_id = "req-" + (++seq), chunk = opts.chunk || 2048, delay = opts.delayMs || 0;
    const later = (fn) => setTimeout(fn, delay);
    let cancelled = false, finished = false;
    const search = typeof engine.createSearch === "function" ? engine.createSearch(ctx, scenario) : null;
    const problem_digest = search ? search.problem_digest : (engine.problemDigest ? engine.problemDigest(ctx, scenario) : null);
    const done = (r) => { if (finished) return; finished = true; if (opts.onDone) opts.onDone({ ...r, request_id }); };
    const h = {
      request_id, problem_digest,
      get finished() { return finished; },
      cancel() {
        if (finished) return false;
        cancelled = true;
        done(search ? search.result("cancelled") : { status: "cancelled", problem_digest, evaluated: null, total_subsets: null });
        return true;
      },
    };
    function tick() {
      if (cancelled || finished) return;
      search.step(chunk);
      if (opts.onProgress) opts.onProgress({ request_id, evaluated: search.evaluated, total: search.total });
      if (search.done) done(search.result());
      else later(tick);
    }
    if (search) later(tick);
    else later(() => { if (!cancelled) done({ ...engine.optimizePlans(ctx, scenario), note: "engine without createSearch: no intermediate progress" }); });
    return h;
  }
  const api = { start };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CITY_PLAN_RUNNER = api;
})(typeof window !== "undefined" ? window : globalThis);
