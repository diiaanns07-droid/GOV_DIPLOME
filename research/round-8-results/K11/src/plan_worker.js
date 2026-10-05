/* K11 round 8 — worker side of the city-plan-v2 orchestration protocol (one file for a browser Web Worker,
 * a Blob-URL worker built from inlined sources, and Node worker_threads).
 *
 * in : {type:"start", request_id, context, scenario, options:{chunk_masks, sensitivity}} | {type:"cancel", request_id}
 * out: {type:"accepted", request_id, problem_digest, total}
 *      {type:"progress", request_id, problem_digest, phase, evaluated, total, done_masks, all_masks}
 *      {type:"result", request_id, problem_digest, result}
 *      {type:"cancelled", request_id} | {type:"error", request_id, code, detail}
 * The search runs in chunks and yields to the worker's event loop between chunks, so a "cancel" message is seen
 * within one chunk. The main thread additionally terminates the worker if no acknowledgement arrives in time.
 */
(function () {
  "use strict";
  let post, CORE;
  const isNode = typeof process !== "undefined" && process.versions && process.versions.node && typeof importScripts !== "function";
  if (isNode) {
    const { parentPort } = require("worker_threads");
    CORE = require("./plan_core.js");
    post = (m) => parentPort.postMessage(m);
    parentPort.on("message", (m) => handle(m));
  } else {
    if (typeof self.CITY_PLAN_CORE === "undefined" && typeof importScripts === "function") importScripts("plan_core.js");
    CORE = self.CITY_PLAN_CORE;
    post = (m) => self.postMessage(m);
    self.onmessage = (e) => handle(e.data);
  }

  const cancelled = new Set();   // cancels for requests that are still running
  const running = new Set();
  let current = null;
  const now = () => (typeof performance !== "undefined" && performance.now ? performance.now() : Date.now());
  // Yield to the worker's event loop so "cancel" messages are processed. setTimeout(0) is clamped to >= 4 ms after
  // nesting in browsers (measured in bench: 4x slower job), so use setImmediate (Node) or a MessageChannel (browser).
  const tick = typeof setImmediate === "function" ? () => new Promise((r) => setImmediate(r))
    : typeof MessageChannel !== "undefined" ? () => new Promise((r) => { const ch = new MessageChannel(); ch.port1.onmessage = () => { ch.port1.close(); r(); }; ch.port2.postMessage(0); })
    : () => new Promise((r) => setTimeout(r, 0));

  function handle(m) {
    if (!m || typeof m !== "object") return;
    if (m.type === "cancel") {
      // a cancel for a request that already finished (or never started here) is acknowledged at once, so the main
      // thread never has to hard-kill a healthy worker that simply completed before reading the cancel
      if (running.has(m.request_id)) cancelled.add(m.request_id);
      else post({ type: "cancelled", request_id: m.request_id });
      return;
    }
    if (m.type === "start") run(m).catch((e) => post({ type: "error", request_id: m.request_id, code: e.code || "internal", detail: String(e.message || e) }));
  }

  async function run(m) {
    const rid = m.request_id;
    if (current !== null) cancelled.add(current);  // a newer start supersedes an older one inside the worker too
    current = rid;
    running.add(rid);
    try { await search(m, rid); } finally { running.delete(rid); cancelled.delete(rid); if (current === rid) current = null; }
  }

  async function search(m, rid) {
    const opt = m.options || {};
    const chunk = Math.max(64, Math.min(1 << 16, opt.chunk_masks | 0 || 4096));
    const sliceMs = Math.max(1, Math.min(100, Number(opt.slice_ms) || 8));  // work per slice before yielding
    const sc = CORE.validatePlanScenario(m.scenario, m.context);
    const pb = CORE.prepareProblem(m.context, sc);
    const budgets = opt.sensitivity ? CORE.sensitivityBudgets(sc.budget) : [];
    const phases = [{ phase: "main", budget: sc.budget }].concat(budgets.map((b) => ({ phase: "budget:" + b, budget: b })));
    const allMasks = phases.length * 2 ** pb.n;
    post({ type: "accepted", request_id: rid, problem_digest: pb.problem_digest, total: allMasks });
    let doneMasks = 0;
    const results = [];
    for (const ph of phases) {
      const st = CORE.createSearch(pb, { budget: ph.budget });
      while (!st.done) {
        if (cancelled.has(rid)) { st.cancelled = true; post({ type: "cancelled", request_id: rid }); cancelled.delete(rid); if (current === rid) current = null; return; }
        const before = st.next, sliceEnd = now() + sliceMs;
        do { CORE.stepSearch(st, Math.min(chunk, 1024)); } while (!st.done && now() < sliceEnd);
        doneMasks += st.next - before;
        post({ type: "progress", request_id: rid, problem_digest: pb.problem_digest, phase: ph.phase,
          evaluated: st.evaluated, total: st.total, done_masks: doneMasks, all_masks: allMasks });
        await tick();
      }
      if (st.total === 0 || st.next < st.total) doneMasks += st.total - st.next;  // pre-infeasible phase skipped
      results.push({ phase: ph.phase, result: CORE.finalizeSearch(st) });
    }
    if (cancelled.has(rid)) { post({ type: "cancelled", request_id: rid }); cancelled.delete(rid); if (current === rid) current = null; return; }
    const result = results[0].result;
    if (budgets.length) result.sensitivity = results.slice(1).map((r) => ({ budget: r.result.budget, status: r.result.status,
      reasons: r.result.reasons || [], feasible_count: r.result.feasible_count,
      objectives: r.result.objectives && Object.fromEntries(Object.entries(r.result.objectives).map(([k, v]) => [k, { selected_ids: v.selected_ids, metrics: v.metrics }])) }));
    post({ type: "result", request_id: rid, problem_digest: pb.problem_digest, result });
    if (current === rid) current = null;
  }
})();
