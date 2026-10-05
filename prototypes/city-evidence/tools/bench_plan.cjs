// Benchmark of the city-plan-v2 exact search at the maximum size (16 candidates × 25 points), Node and headless Chromium.
// Usage: NODE_PATH="$(npm root -g)" node tools/bench_plan.cjs [out.json]
// Numbers describe THIS machine only; they are not a promise for another device. Synthetic inputs (invented sites/costs/weights).
const fs = require("fs"), path = require("path"), vm = require("vm"), os = require("os");
const { pathToFileURL } = require("url");
const APP = path.resolve(__dirname, ".."), W = path.join(APP, "web");
const ctx0 = {}; vm.createContext(ctx0); ctx0.window = ctx0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx0);
const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js")), D = ctx0.CITY_EVIDENCE;

function maxScenario(city, maxSel, required) {
  const ctx = PL.makeContext(D, city, F), [w, s, e, n] = ctx.bbox, g = (fx, fy) => [w + (e - w) * fx, s + (n - s) * fy];
  const cps = Array.from({ length: 25 }, (_, k) => { const [lon, lat] = g(0.05 + 0.9 * ((k % 5) / 4), 0.05 + 0.9 * (Math.floor(k / 5) / 4)); return { id: `P${k + 1}`, lon, lat, weight: 1 + (k * 7) % 100 }; });
  const cands = Array.from({ length: 16 }, (_, k) => { const [lon, lat] = g(0.1 + 0.8 * ((k % 4) / 3), 0.1 + 0.8 * (Math.floor(k / 4) / 3)); return { id: `K${String(k + 1).padStart(2, "0")}`, lon, lat, category: "school", kind: "hypothetical", cost: 1 + (k * 7919) % 1000 }; });
  const sc = PL.validatePlanScenario({ schema_version: PL.SCHEMA, city_id: city, source_snapshot: ctx.source_snapshot, category: "school", control_points: cps, candidates: cands,
    budget: 1000000, max_selected: maxSel, coverage_radius_m: 500, required_ids: required, excluded_ids: [], selected_ids: [] }, ctx);
  return { ctx, sc };
}
const median = (a) => a.slice().sort((x, y) => x - y)[Math.floor(a.length / 2)];
const node = [];
for (const city of ["shymkent", "astana"]) for (const maxSel of [1, 3, 5]) for (const req of [[], ["K01", "K02"]]) {
  const { ctx, sc } = maxScenario(city, maxSel, req);
  const times = []; let r;
  global.gc && global.gc();
  const h0 = process.memoryUsage().heapUsed;
  for (let i = 0; i < 7; i++) { const t = process.hrtime.bigint(); r = PL.optimizePlans(ctx, sc, { F }); times.push(Number(process.hrtime.bigint() - t) / 1e6); }
  const h1 = process.memoryUsage().heapUsed;
  const ts = process.hrtime.bigint(); PL.sensitivity(ctx, sc, { F }); const tSens = Number(process.hrtime.bigint() - ts) / 1e6;
  node.push({ city, candidates: 16, points: 25, max_selected: maxSel, required: req.length, status: r.status, subsets_examined: r.evaluated, feasible: r.feasible_count,
    median_ms: +median(times).toFixed(2), max_ms: +Math.max(...times).toFixed(2), sensitivity_3_budgets_ms: +tSens.toFixed(2), heap_delta_mb_7_runs: +((h1 - h0) / 1048576).toFixed(2) });
}
// validation happens before any search: an oversized problem is rejected immediately
const { ctx: vctx, sc: vsc } = maxScenario("shymkent", 5, []);
const tv = process.hrtime.bigint(); let vcode = null;
try { PL.validatePlanScenario({ ...vsc, candidates: [...vsc.candidates, { ...vsc.candidates[0], id: "K17" }] }, vctx); } catch (e) { vcode = e.code; }
const validationMs = Number(process.hrtime.bigint() - tv) / 1e6;

(async () => {
  let browser = null, chromium = null;
  try { ({ chromium } = require("playwright")); } catch (e) { chromium = null; }
  let br = { status: "SKIP", reason: "playwright not installed" };
  if (chromium) {
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto(pathToFileURL(path.join(W, "index.html")).href);
    br = await page.evaluate(async () => {
      const lt = []; const po = new PerformanceObserver((l) => { for (const e of l.getEntries()) lt.push(e.duration); }); po.observe({ entryTypes: ["longtask"] });
      CITY_APP.setTool("v2");
      const U = CITY_PLAN_UI, b = CITY_EVIDENCE.cities.shymkent.bbox, g = (fx, fy) => [b[0] + (b[2] - b[0]) * fx, b[1] + (b[3] - b[1]) * fy];
      U.setMode("points"); for (let k = 0; k < 25; k++) U.place(g(0.05 + 0.9 * ((k % 5) / 4), 0.05 + 0.9 * (Math.floor(k / 5) / 4)));
      U.setMode("cands"); for (let k = 0; k < 16; k++) U.place(g(0.1 + 0.8 * ((k % 4) / 3), 0.1 + 0.8 * (Math.floor(k / 4) / 3)));
      U.setMode("cands");
      U.setNumber("Бюджет", "1000000", 0, 1000000, (v) => { U.state.budget = v; }); U.setNumber("Максимум", "5", 0, 5, (v) => { U.state.max_selected = v; });
      await new Promise((r) => setTimeout(r, 200)); lt.length = 0;
      // responsiveness: gaps between timer callbacks while the search runs
      let last = performance.now(), maxGap = 0, ticks = 0, on = true;
      const probe = () => { const t = performance.now(); maxGap = Math.max(maxGap, t - last); last = t; ticks++; if (on) setTimeout(probe, 0); };
      setTimeout(probe, 0);
      const t0 = performance.now(); U.startSearch();
      while (U.opt.status === "running") await new Promise((r) => setTimeout(r, 5));
      const total = performance.now() - t0; on = false;
      await new Promise((r) => setTimeout(r, 100)); po.disconnect();
      const mem = performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null;
      return { status: U.opt.status, result_status: U.opt.result && U.opt.result.status, examined_incl_sensitivity: U.opt.examined, total_ms_incl_sensitivity_and_render: +total.toFixed(1),
        longest_main_thread_gap_ms: +maxGap.toFixed(1), long_tasks_over_50ms: lt.length, longest_task_ms: lt.length ? +Math.max(...lt).toFixed(1) : 0, js_heap_mb_after: mem };
    });
    br.browser = `Chromium ${browser.version()} (Playwright, headless)`;
    await browser.close();
  }
  const out = { generated_utc: new Date().toISOString(), note: "this machine only; synthetic 16×25 inputs; not a promise for other devices",
    environment: { os: `${os.type()} ${os.release()} ${os.arch()}`, cpus: `${os.cpus().length} × ${os.cpus()[0] && os.cpus()[0].model}`, node: process.version },
    validation_before_work: { case: "17 candidates", code: vcode, ms: +validationMs.toFixed(3) }, node, browser: br };
  console.log(JSON.stringify(out, null, 1));
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(out, null, 1) + "\n");
})().catch((e) => { console.error(e); process.exit(2); });
