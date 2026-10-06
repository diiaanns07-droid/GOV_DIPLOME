// Bounded benchmark of city-resilience-v1 at the maximum size: 12 candidates × 25 points × 8 cases (7 user + base), both slices.
// Node: optimizeResilience median of 7; browser (headless Chromium, file://): chunked search through the real UI —
// total time, longest gap between timer callbacks (event-loop responsiveness), long tasks, cancel latency.
// Usage: NODE_PATH="$(npm root -g)" node tools/bench_resilience.cjs [out.json]
// Numbers describe THIS machine only. Inputs are SYNTHETIC (points, weights, sites, costs, case choices).
const fs = require("fs"), path = require("path"), vm = require("vm"), os = require("os");
const { pathToFileURL } = require("url");
const APP = path.resolve(__dirname, ".."), W = path.join(APP, "web");
const c0 = {}; vm.createContext(c0); c0.window = c0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), c0);
const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js")), RS = require(path.join(W, "resilience.js")), D = c0.CITY_EVIDENCE;

function maxEnvelope(city) {
  const ctx = PL.makeContext(D, city, F), [w, s, e, n] = ctx.bbox, g = (x, y) => [w + (e - w) * x, s + (n - s) * y];
  const src = ctx.places.filter((p) => p.group === "school").map((p) => p.id).sort();
  const plan = { schema_version: PL.SCHEMA, city_id: city, source_snapshot: ctx.source_snapshot, category: "school",
    control_points: Array.from({ length: 25 }, (_, k) => { const [lon, lat] = g(0.05 + 0.9 * (k % 5) / 4, 0.05 + 0.9 * Math.floor(k / 5) / 4); return { id: `P${k + 1}`, lon, lat, weight: 1 + (k * 7) % 100 }; }),
    candidates: Array.from({ length: 12 }, (_, k) => { const [lon, lat] = g(0.1 + 0.8 * (k % 4) / 3, 0.15 + 0.7 * Math.floor(k / 4) / 2); return { id: `K${String(k + 1).padStart(2, "0")}`, lon, lat, category: "school", kind: "hypothetical", cost: 100 + (k * 37) % 300 }; }),
    budget: 1000000, max_selected: 5, coverage_radius_m: 400, required_ids: [], excluded_ids: [], selected_ids: [] };
  const cases = Array.from({ length: 7 }, (_, k) => ({ id: `c${k + 1}`, label: `Синтетический случай ${k + 1}`, disabled_source_ids: src.filter((_, i) => (i + k) % (k + 2) === 0) }));
  return { ctx, env: { schema_version: RS.SCHEMA, plan, cases } };
}
const median = (a) => a.slice().sort((x, y) => x - y)[Math.floor(a.length / 2)];
const node = [];
for (const city of ["shymkent", "astana"]) {
  const { ctx, env } = maxEnvelope(city), times = []; let r;
  for (let i = 0; i < 7; i++) { const t = process.hrtime.bigint(); r = RS.optimizeResilience(ctx, env, { F }); times.push(Number(process.hrtime.bigint() - t) / 1e6); }
  const tv = process.hrtime.bigint(); let code = null;
  try { RS.validateResilience({ ...env, plan: { ...env.plan, candidates: [...env.plan.candidates, { ...env.plan.candidates[0], id: "K13" }] } }, ctx); } catch (e) { code = e.code; }
  node.push({ city, candidates: 12, points: 25, cases: 8, status: r.status, subsets: r.evaluated, feasible: r.feasible_count, median_ms: +median(times).toFixed(2), max_ms: +Math.max(...times).toFixed(2),
    same_plan: r.same_plan, price_of_robustness_m: r.price_of_robustness_m, refuse_13_candidates: { code, ms: +(Number(process.hrtime.bigint() - tv) / 1e6).toFixed(3) } });
}
(async () => {
  let chromium = null; try { ({ chromium } = require("playwright")); } catch (e) { chromium = null; }
  const browser = { status: "NOT_RUN", reason: "playwright not installed", runs: [] };
  if (chromium) {
    const b = await chromium.launch(); browser.status = "RUN"; browser.reason = undefined; browser.browser = `Chromium ${b.version()} (Playwright, headless)`;
    for (const city of ["shymkent", "astana"]) {
      const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
      await page.goto(pathToFileURL(path.join(W, "index.html")).href);
      const { env } = maxEnvelope(city);
      const r = await page.evaluate(async ({ env, city }) => {
        if (CITY_APP.state.city !== city) CITY_APP.switchCity(city);
        CITY_APP.setTool("v2");
        if (!CITY_RESILIENCE_UI.importText(JSON.stringify(env))) return { error: document.getElementById("rsMsg").textContent };
        await new Promise((r) => setTimeout(r, 100));
        const lt = []; const po = new PerformanceObserver((l) => { for (const e of l.getEntries()) lt.push(e.duration); }); po.observe({ entryTypes: ["longtask"] });
        let last = performance.now(), gap = 0, on = true; const probe = () => { const t = performance.now(); gap = Math.max(gap, t - last); last = t; if (on) setTimeout(probe, 0); }; setTimeout(probe, 0);
        const t0 = performance.now(); CITY_RESILIENCE_UI.start();
        while (CITY_RESILIENCE_UI.state.status === "running") await new Promise((r) => setTimeout(r, 5));
        const total = performance.now() - t0; on = false;
        // cancel latency: start again, cancel after ~20 ms, measure until the UI reports cancelled and stays so
        CITY_RESILIENCE_UI.start(); await new Promise((r) => setTimeout(r, 20));
        const examinedAtCancel = CITY_RESILIENCE_UI.state.examined, tc = performance.now(); CITY_RESILIENCE_UI.cancel(); const cancelMs = performance.now() - tc;
        await new Promise((r) => setTimeout(r, 200));
        po.disconnect();
        return { status: CITY_RESILIENCE_UI.state.status, total_ms_incl_render: +total.toFixed(1), longest_event_loop_gap_ms: +gap.toFixed(1), long_tasks_over_50ms: lt.length,
          longest_task_ms: lt.length ? +Math.max(...lt).toFixed(1) : 0, cancel_call_ms: +cancelMs.toFixed(2), examined_before_cancel: examinedAtCancel, after_cancel_status: CITY_RESILIENCE_UI.state.status,
          js_heap_mb: performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null };
      }, { env, city });
      browser.runs.push({ city, ...r });
      await page.close();
    }
    await b.close();
  }
  const out = { generated_utc: new Date().toISOString(), note: "this machine only; synthetic 12×25×8 inputs on the real slices; not a promise for other devices",
    environment: { os: `${os.type()} ${os.release()} ${os.arch()}`, cpus: `${os.cpus().length} × ${os.cpus()[0] && os.cpus()[0].model}`, node: process.version }, node, browser };
  console.log(JSON.stringify(out, null, 1));
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(out, null, 1) + "\n");
})().catch((e) => { console.error(e); process.exit(2); });
