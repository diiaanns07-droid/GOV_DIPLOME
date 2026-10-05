// K11 round 8 stage 2 — Node benchmark of the plan runner on 16 candidates x 25 points.
// Usage: node --expose-gc bench/bench_node.cjs [--repeat 7] [--out runs/stage2_bench_node.json]
// Numbers are measurements of THIS machine and Node version, not a universal SLA.
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");
const { performance, monitorEventLoopDelay } = require("perf_hooks");
const ROOT = path.resolve(__dirname, "..");
const CORE = require(path.join(ROOT, "src/plan_core.js"));
const R = require(path.join(ROOT, "src/plan_runner.js"));
const WORKER = path.join(ROOT, "src/plan_worker.js");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const REPEAT = +arg("--repeat", 7);
const load = (d, f) => JSON.parse(fs.readFileSync(path.join(ROOT, "fixtures", d, f), "utf8"));
const WORK = { synthetic_16x25: load("synthetic", "syn_bench_16x25.json"), real_shymkent_16x25: load("real", "real_shymkent_school_16x25.json") };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const stat = (a) => { const s = a.slice().sort((x, y) => x - y); const q = (p) => s[Math.min(s.length - 1, Math.floor(p * (s.length - 1) + 0.5))];
  return { n: s.length, min: +s[0].toFixed(2), median: +q(0.5).toFixed(2), max: +s[s.length - 1].toFixed(2) }; };
const gc = () => { if (global.gc) { global.gc(); global.gc(); } };
const handles = () => (process._getActiveHandles ? process._getActiveHandles().length : -1);

async function loopDelayDuring(fn) {
  const h = monitorEventLoopDelay({ resolution: 1 });
  h.enable();
  // a 1 ms timer armed before the work: its lateness is the longest uninterrupted block even for fully
  // synchronous work, which monitorEventLoopDelay cannot sample while the thread is busy
  const armed = performance.now();
  const late = new Promise((r) => setTimeout(() => r(performance.now() - armed - 1), 1));
  const t0 = performance.now();
  const out = await fn();
  const elapsed = performance.now() - t0;
  const timerLate = await late;
  h.disable();
  return { out, elapsed, loop_max_ms: Math.max(h.max / 1e6, timerLate), loop_p99_ms: h.percentile(99) / 1e6 };
}

(async () => {
  const report = { tool: "bench/bench_node.cjs", note: "measured on this machine; not an SLA", machine: { node: process.version,
    platform: `${os.platform()} ${os.release()}`, cpus: os.cpus().length, cpu_model: os.cpus()[0] && os.cpus()[0].model, gc_exposed: !!global.gc },
    repeat: REPEAT, workloads: {}, cancel: {}, memory: {}, resources: {} };

  for (const [name, fx] of Object.entries(WORK)) {
    const w = {};
    for (const sens of [false, true]) {
      const tag = sens ? "with_sensitivity" : "main_only";
      const sync = [], syncLoop = [];
      for (let i = 0; i < REPEAT; i++) {
        const m = await loopDelayDuring(async () => {
          const r = CORE.optimizePlansSync(fx.context, fx.scenario);
          if (sens) for (const b of CORE.sensitivityBudgets(fx.scenario.budget)) CORE.optimizePlansSync(fx.context, fx.scenario, { budget: b });
          return r;
        });
        sync.push(m.elapsed); syncLoop.push(m.loop_max_ms);
      }
      const modes = { sync_blocking: { elapsed_ms: stat(sync), loop_max_ms: stat(syncLoop) } };
      for (const sliceMs of [4, 8, 16]) {
        const el = [], lm = [], p99 = [];
        for (let i = 0; i < REPEAT; i++) {
          const runner = R.createPlanRunner({ engine: CORE, mode: "chunks", sliceMs });
          const m = await loopDelayDuring(() => runner.run(fx.context, fx.scenario, { sensitivity: sens }).promise);
          if (m.out.status !== "optimal") throw new Error("chunks run not optimal");
          el.push(m.elapsed); lm.push(m.loop_max_ms); p99.push(m.loop_p99_ms);
          runner.dispose();
        }
        modes[`chunks_slice_${sliceMs}ms`] = { elapsed_ms: stat(el), loop_max_ms: stat(lm), loop_p99_ms: stat(p99) };
      }
      for (const warm of [false, true]) {
        const el = [], lm = [];
        const shared = warm ? R.createPlanRunner({ engine: CORE, mode: "worker", workerFactory: R.nodeWorkerFactory(WORKER) }) : null;
        if (shared) await shared.run(fx.context, fx.scenario).promise;  // warm-up: worker created and JIT-warm
        for (let i = 0; i < REPEAT; i++) {
          const runner = shared || R.createPlanRunner({ engine: CORE, mode: "worker", workerFactory: R.nodeWorkerFactory(WORKER) });
          const m = await loopDelayDuring(() => runner.run(fx.context, fx.scenario, { sensitivity: sens }).promise);
          if (m.out.status !== "optimal") throw new Error("worker run not optimal");
          el.push(m.elapsed); lm.push(m.loop_max_ms);
          if (!shared) runner.dispose();
        }
        if (shared) shared.dispose();
        modes[warm ? "worker_warm" : "worker_cold"] = { elapsed_ms: stat(el), loop_max_ms: stat(lm) };
      }
      w[tag] = modes;
    }
    report.workloads[name] = w;
  }

  // cancel latency at 10/50/90 % (synthetic 16x25 with sensitivity = 4 searches, longest job)
  const fx = WORK.synthetic_16x25;
  for (const mode of ["worker", "chunks"]) {
    const res = {};
    for (const at of [0.1, 0.5, 0.9]) {
      const resolve = [], ack = [], lastSlice = [];
      for (let i = 0; i < REPEAT; i++) {
        let tCancel = null, tAck = null, lastStepEnd = 0;
        const engine = Object.assign({}, CORE, { stepSearch: (st, n) => { const r = CORE.stepSearch(st, n); lastStepEnd = performance.now(); return r; } });
        const runner = R.createPlanRunner({ engine, mode, sliceMs: 8, chunkMasks: 2048, workerFactory: R.nodeWorkerFactory(WORKER),
          onProgress: (e) => { if (tCancel === null && e.fraction >= at) { tCancel = performance.now(); runner.cancel(); } },
          onStatus: (e) => { if (e.status === "cancel_ack") tAck = performance.now(); } });
        const env = await runner.run(fx.context, fx.scenario, { sensitivity: true }).promise;
        const tResolved = performance.now();
        await sleep(mode === "worker" ? 300 : 30);
        if (env.status !== "cancelled") throw new Error("expected cancelled, got " + env.status);
        resolve.push(tResolved - tCancel);
        if (mode === "worker") { if (tAck === null) throw new Error("no cancel ack"); ack.push(tAck - tCancel); }
        else lastSlice.push(Math.max(0, lastStepEnd - tCancel));
        runner.dispose();
      }
      res[`at_${at * 100}pct`] = mode === "worker" ? { promise_resolved_ms: stat(resolve), worker_ack_ms: stat(ack) }
        : { promise_resolved_ms: stat(resolve), compute_after_cancel_ms: stat(lastSlice) };
    }
    report.cancel[mode] = res;
  }

  // memory and resource release over repeated create -> run -> dispose cycles
  for (const mode of ["worker", "chunks"]) {
    gc(); await sleep(50); gc();
    const h0 = handles(), heap0 = process.memoryUsage().heapUsed, rss0 = process.memoryUsage().rss;
    let created = 0, terminated = 0, peakRss = rss0;
    const sampler = setInterval(() => { peakRss = Math.max(peakRss, process.memoryUsage().rss); }, 5);
    for (let i = 0; i < 30; i++) {
      const runner = R.createPlanRunner({ engine: CORE, mode, workerFactory: R.nodeWorkerFactory(WORKER) });
      const env = await runner.run(fx.context, fx.scenario).promise;
      if (env.status !== "optimal") throw new Error("not optimal");
      runner.dispose();
      const s = runner.state();
      created += s.stats.workers_created; terminated += s.stats.workers_terminated;
      if (s.worker_alive || s.pending_timers || s.active) throw new Error("resources left after dispose");
    }
    clearInterval(sampler);
    await sleep(200); gc(); await sleep(50); gc();
    const h1 = handles(), heap1 = process.memoryUsage().heapUsed, rss1 = process.memoryUsage().rss;
    report.memory[mode] = { cycles: 30, heap_used_before_mb: +(heap0 / 2 ** 20).toFixed(2), heap_used_after_mb: +(heap1 / 2 ** 20).toFixed(2),
      heap_growth_mb: +((heap1 - heap0) / 2 ** 20).toFixed(2), rss_before_mb: +(rss0 / 2 ** 20).toFixed(1), rss_peak_mb: +(peakRss / 2 ** 20).toFixed(1),
      rss_after_mb: +(rss1 / 2 ** 20).toFixed(1) };
    report.resources[mode] = { workers_created: created, workers_terminated: terminated, active_handles_before: h0, active_handles_after: h1 };
  }
  // one search's own memory: problem matrices + Pareto map at the end of a search (heap delta, approximate)
  gc(); const hb = process.memoryUsage().heapUsed;
  const pb = CORE.prepareProblem(fx.context, CORE.validatePlanScenario(fx.scenario, fx.context));
  const st = CORE.createSearch(pb); while (!st.done) CORE.stepSearch(st, 65536);
  gc(); report.memory.single_search_state_heap_mb = +((process.memoryUsage().heapUsed - hb) / 2 ** 20).toFixed(2);
  report.memory.single_search_pareto_entries = st.pareto.size;

  const out = arg("--out", null);
  if (out) fs.writeFileSync(out, JSON.stringify(report, null, 1) + "\n");
  console.log(JSON.stringify(report, null, 1));
})().catch((e) => { console.error(e); process.exitCode = 1; });
