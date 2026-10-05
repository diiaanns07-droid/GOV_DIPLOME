/* K11 round 8 — orchestration adapter for optimizePlans (city-plan-v2): keeps the UI responsive, reports progress,
 * cancels, and makes sure a stale answer is never applied.
 *
 *   const runner = CITY_PLAN_RUNNER.createPlanRunner({ engine: CITY_PLAN_CORE, mode: "auto",
 *       workerFactory: CITY_PLAN_RUNNER.urlWorkerFactory("plan_worker.js"), onProgress });
 *   const job = runner.run(context, scenario, { sensitivity: true });
 *   job.request_id, job.problem_digest            // known synchronously
 *   const env = await job.promise;                // {status, request_id, problem_digest, mode, elapsed_ms, result?}
 *   if (runner.isCurrent(env)) applyProposal(env.result);   // the user still presses "Apply"
 *   runner.cancel();  runner.dispose();
 *
 * env.status: "optimal" | "infeasible" | "cancelled" | "superseded" | "error". Never "optimal" unless the whole
 * space was searched. A new run() supersedes the previous one; messages carrying another request_id or
 * problem_digest are ignored. Cancel is cooperative first; a worker that does not acknowledge within
 * cancelGraceMs is terminated (guaranteed release) and recreated lazily on the next run.
 * Modes: "worker" (Web Worker / worker_threads), "chunks" (time-sliced on the calling thread), "auto"
 * (worker if the factory works, otherwise chunks; the fallback reason is reported in env.fallback).
 */
(function (root) {
  "use strict";
  const now = () => (typeof performance !== "undefined" && performance.now ? performance.now() : Date.now());

  function defaultYield() {
    if (typeof MessageChannel !== "undefined" && typeof window !== "undefined") {
      return new Promise((r) => { const ch = new MessageChannel(); ch.port1.onmessage = () => { ch.port1.close(); r(); }; ch.port2.postMessage(0); });
    }
    return new Promise((r) => setTimeout(r, 0));
  }

  function createPlanRunner(opts) {
    const o = Object.assign({ mode: "auto", chunkMasks: 4096, sliceMs: 10, cancelGraceMs: 250, yieldFn: defaultYield,
      onProgress: null, onStatus: null }, opts || {});
    const CORE = o.engine;
    if (!CORE || typeof CORE.createSearch !== "function") throw new Error("plan runner: engine with createSearch/stepSearch/finalizeSearch required");
    let seq = 0, active = null, worker = null, workerBroken = null, disposed = false;
    const timers = new Set();
    const pendingCancels = new Map();  // request_id -> grace timer; cleared by the worker's "cancelled" ack
    const stats = { workers_created: 0, workers_terminated: 0, hard_terminations: 0, stale_messages_ignored: 0,
      cancel_acks: 0, redispatched: 0 };

    const status = (s, extra) => { if (o.onStatus) try { o.onStatus(Object.assign({ status: s }, extra)); } catch (_) { /* UI callback */ } };
    function settle(job, env) {
      if (job.settled) return;
      job.settled = true;
      if (active === job) active = null;
      job.resolve(Object.assign({ request_id: job.request_id, problem_digest: job.problem_digest, mode: job.mode,
        elapsed_ms: Math.round((now() - job.t0) * 10) / 10 }, env));
      status(env.status, { request_id: job.request_id });
    }
    function later(fn, ms) { const t = setTimeout(() => { timers.delete(t); fn(); }, ms); timers.add(t); return t; }

    function ensureWorker() {
      if (worker) return worker;
      if (!o.workerFactory) throw new Error("no workerFactory");
      const w = o.workerFactory();
      stats.workers_created++;
      w.onmessage = (e) => onWorkerMessage(e && "data" in e ? e.data : e);
      w.onerror = (e) => {
        const job = active;
        if (job && job.mode === "worker") {
          killWorker(false);
          if (o.mode === "auto" && !job.started) { workerBroken = String((e && e.message) || e); job.fallback = workerBroken; runChunks(job); }
          else settle(job, { status: "error", code: "worker_error", detail: String((e && e.message) || e) });
        }
      };
      worker = w;
      return w;
    }
    function killWorker(hard) {
      if (!worker) return;
      try { worker.terminate(); } catch (_) { /* already gone */ }
      worker = null;
      stats.workers_terminated++;
      for (const t of pendingCancels.values()) { clearTimeout(t); timers.delete(t); }
      pendingCancels.clear();
      if (hard) {
        stats.hard_terminations++;
        const job = active;  // a newer job queued on the killed worker is restarted on a fresh one
        if (job && job.mode === "worker" && !job.settled && !disposed) { stats.redispatched++; dispatch(job); }
      }
    }
    function dispatch(job) {
      const w = ensureWorker();
      job.mode = "worker";
      w.postMessage({ type: "start", request_id: job.request_id, context: job.context, scenario: job.sc,
        options: { chunk_masks: o.chunkMasks, sensitivity: !!job.options.sensitivity } });
    }
    function onWorkerMessage(m) {
      if (m && m.type === "cancelled") {  // acknowledgement of any earlier cancel, whoever is active now
        const t = pendingCancels.get(m.request_id);
        if (t !== undefined) { clearTimeout(t); timers.delete(t); pendingCancels.delete(m.request_id); stats.cancel_acks++; }
        return;
      }
      const job = active;
      if (!m || !job || m.request_id !== job.request_id || (m.problem_digest && m.problem_digest !== job.problem_digest)) {
        stats.stale_messages_ignored++;
        return;
      }
      if (m.type === "accepted") { job.started = true; return; }
      if (m.type === "progress") { if (o.onProgress) o.onProgress(progressEvent(job, m)); return; }
      if (m.type === "result") { settle(job, { status: m.result.status, result: m.result, fallback: job.fallback || null }); return; }
      if (m.type === "error") settle(job, { status: "error", code: m.code, detail: m.detail });
    }
    function progressEvent(job, m) {
      return { request_id: job.request_id, problem_digest: job.problem_digest, phase: m.phase,
        fraction: m.all_masks ? m.done_masks / m.all_masks : 1, done_masks: m.done_masks, all_masks: m.all_masks };
    }

    async function runChunks(job) {
      job.mode = "chunks";
      const sc = job.sc, pb = CORE.prepareProblem(job.context, sc);
      const budgets = job.options.sensitivity ? CORE.sensitivityBudgets(sc.budget) : [];
      const phases = [{ phase: "main", budget: sc.budget }].concat(budgets.map((b) => ({ phase: "budget:" + b, budget: b })));
      const allMasks = phases.length * 2 ** pb.n;
      let doneMasks = 0;
      const results = [];
      job.started = true;
      for (const ph of phases) {
        const st = CORE.createSearch(pb, { budget: ph.budget });
        while (!st.done) {
          if (job.settled) return;  // cancelled or superseded: stop touching state
          const sliceEnd = now() + o.sliceMs;
          do {
            const before = st.next;
            CORE.stepSearch(st, Math.min(o.chunkMasks, 1024));
            doneMasks += st.next - before;
          } while (!st.done && now() < sliceEnd);
          if (o.onProgress) o.onProgress(progressEvent(job, { phase: ph.phase, done_masks: doneMasks, all_masks: allMasks }));
          await o.yieldFn();
        }
        doneMasks += st.total - st.next;
        results.push(CORE.finalizeSearch(st));
      }
      if (job.settled) return;
      const result = results[0];
      if (budgets.length) result.sensitivity = results.slice(1).map((r) => ({ budget: r.budget, status: r.status, reasons: r.reasons || [],
        feasible_count: r.feasible_count, objectives: r.objectives && Object.fromEntries(Object.entries(r.objectives).map(([k, v]) => [k, { selected_ids: v.selected_ids, metrics: v.metrics }])) }));
      settle(job, { status: result.status, result, fallback: job.fallback || null });
    }

    function run(context, scenario, options) {
      if (disposed) throw new Error("plan runner disposed");
      if (active) cancelJob(active, "superseded");
      const job = { request_id: "req-" + (++seq), context, options: options || {}, t0: now(), settled: false, started: false };
      job.promise = new Promise((res) => { job.resolve = res; });
      try {
        job.sc = CORE.validatePlanScenario(scenario, context);  // typed error before any work; state unchanged
        job.problem_digest = CORE.problemDigest(job.sc);
      } catch (e) {
        job.mode = "none";
        settle(job, { status: "error", code: e.code || "invalid", detail: e.detail || String(e.message || e) });
        return { request_id: job.request_id, problem_digest: null, promise: job.promise };
      }
      active = job;
      status("running", { request_id: job.request_id });
      const wantWorker = o.mode === "worker" || (o.mode === "auto" && o.workerFactory && !workerBroken);
      if (wantWorker) {
        try {
          dispatch(job);
        } catch (e) {
          if (o.mode === "worker") { settle(job, { status: "error", code: "worker_unavailable", detail: String(e.message || e) }); return pub(job); }
          workerBroken = String(e.message || e);
          job.fallback = workerBroken;
          runChunks(job);
        }
      } else {
        if (o.mode === "auto" && workerBroken) job.fallback = workerBroken;
        runChunks(job);
      }
      return pub(job);
    }
    const pub = (job) => ({ request_id: job.request_id, problem_digest: job.problem_digest, promise: job.promise });

    function cancelJob(job, why) {
      if (job.settled) return;
      if (job.mode === "worker" && worker) {
        const w = worker;
        try { w.postMessage({ type: "cancel", request_id: job.request_id }); } catch (_) { /* gone */ }
        pendingCancels.set(job.request_id, later(() => {
          pendingCancels.delete(job.request_id);
          if (worker === w) killWorker(true);  // no acknowledgement in time: guaranteed release
        }, o.cancelGraceMs));
      }
      settle(job, { status: why });
    }
    function cancel() { if (active) cancelJob(active, "cancelled"); }
    function isCurrent(env) {
      return !!env && env.status !== "superseded" && env.status !== "cancelled" && active === null && env.request_id === "req-" + seq;
    }
    function dispose() {
      cancel();
      killWorker(false);
      for (const t of timers) clearTimeout(t);
      timers.clear();
      disposed = true;
    }
    function state() {
      return { active: active ? active.request_id : null, worker_alive: !!worker, pending_timers: timers.size,
        pending_cancels: pendingCancels.size,
        worker_broken: workerBroken, disposed, stats: Object.assign({}, stats) };
    }
    return { run, cancel, dispose, isCurrent, state };
  }

  // ---------- worker factories ----------
  function urlWorkerFactory(url) { return () => new Worker(url); }
  /* For file:// pages: browsers refuse new Worker("file:///...") but accept a Blob URL built from sources that were
   * loaded with ordinary <script> tags (window.CITY_PLAN_WORKER_SOURCES, see tools/make_worker_bundle.py). */
  function blobWorkerFactory(sources) {
    return () => {
      const url = URL.createObjectURL(new Blob(sources, { type: "text/javascript" }));
      try { return new Worker(url); } finally { setTimeout(() => URL.revokeObjectURL(url), 0); }
    };
  }
  /* Node: worker_threads Worker wrapped to the Web Worker shape (onmessage receives {data}). */
  function nodeWorkerFactory(workerPath) {
    return () => {
      const { Worker } = require("worker_threads");
      const w = new Worker(workerPath);
      const shim = { onmessage: null, onerror: null, postMessage: (m) => w.postMessage(m), terminate: () => w.terminate(), _w: w };
      w.on("message", (d) => shim.onmessage && shim.onmessage({ data: d }));
      w.on("error", (e) => shim.onerror && shim.onerror(e));
      return shim;
    };
  }

  const api = { createPlanRunner, urlWorkerFactory, blobWorkerFactory, nodeWorkerFactory, VERSION: "k11-plan-runner/1" };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CITY_PLAN_RUNNER = api;
})(typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : globalThis);
