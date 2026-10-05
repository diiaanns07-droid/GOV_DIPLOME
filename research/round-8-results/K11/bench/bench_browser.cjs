// K11 round 8 stage 2 — browser benchmark (Playwright Chromium) of main-thread responsiveness for 16x25.
// Usage: NODE_PATH="$(npm root -g)" node bench/bench_browser.cjs [--repeat 5] [--out runs/stage2_bench_browser.json]
// Serves research/round-8-results/K11 with its own static server on 127.0.0.1 (stopped at the end).
// Measurements of THIS machine/browser build, not a universal SLA. Exit 3 = playwright not resolvable (not_run).
"use strict";
const fs = require("fs"), path = require("path"), http = require("http"), os = require("os");
const ROOT = path.resolve(__dirname, "..");
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { console.log("NOT_RUN playwright not resolvable"); process.exit(3); }
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const REPEAT = +arg("--repeat", 5);
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8" };
function serve() {
  const srv = http.createServer((req, res) => {
    const p = path.normalize(path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname)));
    if (!p.startsWith(ROOT + path.sep) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(p)] || "application/octet-stream" });
    fs.createReadStream(p).pipe(res);
  });
  return new Promise((r) => srv.listen(0, "127.0.0.1", () => r(srv)));
}

// runs inside the page
async function pageBench(cfg) {
  const CORE = window.CITY_PLAN_CORE, RUN = window.CITY_PLAN_RUNNER;
  const fx = window.K11_EXAMPLE[cfg.fixture];
  const factory = RUN.urlWorkerFactory("../src/plan_worker.js");
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function measure(fn) {
    const longtasks = [];
    const po = new PerformanceObserver((l) => { for (const e of l.getEntries()) longtasks.push(e.duration); });
    po.observe({ type: "longtask" });
    let maxLate = 0, lastTick = performance.now(), frames = 0, maxGap = 0, lastFrame = 0, on = true;
    const iv = setInterval(() => { const t = performance.now(); maxLate = Math.max(maxLate, t - lastTick - 4); lastTick = t; }, 4);
    const raf = (t) => { if (!on) return; if (lastFrame) maxGap = Math.max(maxGap, t - lastFrame); lastFrame = t; frames++; requestAnimationFrame(raf); };
    requestAnimationFrame(raf);
    await sleep(50);
    const t0 = performance.now();
    const out = await fn();
    const elapsed = performance.now() - t0;
    await sleep(60);  // let the observer deliver entries
    on = false; clearInterval(iv); po.disconnect();
    return { status: out && out.status, mode: out && out.mode, elapsed_ms: +elapsed.toFixed(1), longtasks_ms: longtasks.map((x) => Math.round(x)),
      longest_task_ms: longtasks.length ? Math.round(Math.max(...longtasks)) : 0, timer_max_late_ms: +maxLate.toFixed(1),
      raf_max_gap_ms: +maxGap.toFixed(1), frames };
  }
  const res = {};
  for (const sens of [false, true]) {
    const tag = sens ? "with_sensitivity" : "main_only";
    res[tag] = { sync_blocking: [], chunks_8ms: [], worker_cold: [], worker_warm: [] };
    for (let i = 0; i < cfg.repeat; i++) {
      res[tag].sync_blocking.push(await measure(async () => {
        const r = CORE.optimizePlansSync(fx.context, fx.scenario);
        if (sens) for (const b of CORE.sensitivityBudgets(fx.scenario.budget)) CORE.optimizePlansSync(fx.context, fx.scenario, { budget: b });
        return { status: r.status, mode: "sync" };
      }));
      const rc = RUN.createPlanRunner({ engine: CORE, mode: "chunks", sliceMs: 8 });
      res[tag].chunks_8ms.push(await measure(() => rc.run(fx.context, fx.scenario, { sensitivity: sens }).promise));
      rc.dispose();
      const rw = RUN.createPlanRunner({ engine: CORE, mode: "worker", workerFactory: factory });
      res[tag].worker_cold.push(await measure(() => rw.run(fx.context, fx.scenario, { sensitivity: sens }).promise));
      res[tag].worker_warm.push(await measure(() => rw.run(fx.context, fx.scenario, { sensitivity: sens }).promise));
      rw.dispose();
    }
  }
  // cancel latency (worker and chunks), at 10/50/90 %, longest job (with sensitivity)
  const cancel = {};
  for (const mode of ["worker", "chunks"]) {
    cancel[mode] = {};
    for (const at of [0.1, 0.5, 0.9]) {
      const rows = [];
      for (let i = 0; i < cfg.repeat; i++) {
        let tC = null, tAck = null;
        const r = RUN.createPlanRunner({ engine: CORE, mode, sliceMs: 8, chunkMasks: 2048, workerFactory: factory,
          onProgress: (e) => { if (tC === null && e.fraction >= at) { tC = performance.now(); r.cancel(); } },
          onStatus: (e) => { if (e.status === "cancel_ack") tAck = performance.now(); } });
        const env = await r.run(fx.context, fx.scenario, { sensitivity: true }).promise;
        const tRes = performance.now();
        await sleep(mode === "worker" ? 300 : 30);
        const st = r.state();
        rows.push({ status: env.status, resolved_ms: +(tRes - tC).toFixed(2), ack_ms: tAck === null ? null : +(tAck - tC).toFixed(2),
          hard_kill: st.stats.hard_terminations, pending_cancels: st.pending_cancels });
        r.dispose();
      }
      cancel[mode]["at_" + at * 100 + "pct"] = rows;
    }
  }
  // memory + worker balance over repeated create -> run -> dispose
  const mem = {};
  const heap = () => (performance.memory ? performance.memory.usedJSHeapSize : null);
  for (const mode of ["worker", "chunks"]) {
    if (window.gc) { window.gc(); window.gc(); }
    await sleep(50);
    const h0 = heap();
    let created = 0, terminated = 0, leftovers = 0;
    for (let i = 0; i < 20; i++) {
      const r = RUN.createPlanRunner({ engine: CORE, mode, workerFactory: factory });
      const env = await r.run(fx.context, fx.scenario).promise;
      if (env.status !== "optimal") leftovers += 1000;
      r.dispose();
      const s = r.state();
      created += s.stats.workers_created; terminated += s.stats.workers_terminated;
      if (s.worker_alive || s.pending_timers || s.active) leftovers++;
    }
    await sleep(200);
    if (window.gc) { window.gc(); window.gc(); }
    await sleep(50);
    const h1 = heap();
    mem[mode] = { cycles: 20, js_heap_before_mb: h0 && +(h0 / 2 ** 20).toFixed(2), js_heap_after_mb: h1 && +(h1 / 2 ** 20).toFixed(2),
      js_heap_growth_mb: h0 && h1 && +((h1 - h0) / 2 ** 20).toFixed(2), workers_created: created, workers_terminated: terminated, leftovers,
      gc_exposed: !!window.gc };
  }
  return { results: res, cancel, memory: mem, ua: navigator.userAgent, hw_concurrency: navigator.hardwareConcurrency };
}

(async () => {
  const srv = await serve();
  const browser = await chromium.launch({ args: ["--js-flags=--expose-gc", "--enable-precise-memory-info"] });
  let out;
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e.message)));
    await page.goto(`http://127.0.0.1:${srv.address().port}/example/index.html`);
    await page.waitForFunction(() => !!window.K11_DEMO);
    const fixtures = ["syn_bench_16x25.json", "real_shymkent_school_16x25.json"];
    out = { tool: "bench/bench_browser.cjs", note: "measured on this machine/browser; not an SLA", browser_version: browser.version(),
      machine: { platform: `${os.platform()} ${os.release()}`, cpus: os.cpus().length, cpu_model: os.cpus()[0] && os.cpus()[0].model }, repeat: REPEAT, by_fixture: {} };
    for (const f of fixtures) out.by_fixture[f] = await page.evaluate(pageBench, { fixture: f, repeat: REPEAT });
    out.page_errors = errors;
  } finally {
    await browser.close();
    await new Promise((r) => srv.close(r));
  }
  const o = arg("--out", null);
  if (o) fs.writeFileSync(o, JSON.stringify(out, null, 1) + "\n");
  console.log(JSON.stringify(out, null, 1).slice(0, 2000));
})().catch((e) => { console.error(e); process.exitCode = 1; });
