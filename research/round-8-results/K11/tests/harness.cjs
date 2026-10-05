// K11 round 8 — headless Node harness (no DOM) for plan_core + plan_runner + plan_worker.
// Usage: node tests/harness.cjs [--out report.json]      exit 0 = all checks pass
"use strict";
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const CORE = require(path.join(ROOT, "src/plan_core.js"));
const R = require(path.join(ROOT, "src/plan_runner.js"));
const WORKER = path.join(ROOT, "src/plan_worker.js");

const results = [];
function check(name, ok, detail) { results.push({ name, ok: !!ok, detail: detail === undefined ? null : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (ok || detail === undefined ? "" : " :: " + JSON.stringify(detail).slice(0, 300))); }
const load = (d, f) => JSON.parse(fs.readFileSync(path.join(ROOT, "fixtures", d, f), "utf8"));
const FIX = [];
for (const d of ["synthetic", "real"]) for (const f of fs.readdirSync(path.join(ROOT, "fixtures", d)).sort())
  if (f.endsWith(".json") && f !== "expected_oracle.json") FIX.push({ d, f, fx: load(d, f) });
const EXP = { synthetic: load("synthetic", "expected_oracle.json"), real: load("real", "expected_oracle.json") };
const strip = (r) => JSON.parse(JSON.stringify(r, (k, v) => (k === "elapsed_ms" ? undefined : v)));
const bench = FIX.find((x) => x.f === "syn_bench_16x25.json").fx;

function sameAsOracle(r, o) {
  if (r.status !== o.status || r.feasible_count !== o.feasible_count) return false;
  if (o.status !== "optimal") return JSON.stringify(r.reasons) === JSON.stringify(o.reasons);
  for (const k of ["mean", "minimax", "coverage"]) {
    const a = r.objectives[k], b = o.objectives[k];
    if (JSON.stringify(a.selected_ids) !== JSON.stringify(b.selected_ids)) return false;
    for (const m of ["cost", "unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "weighted_mean_mm"]) if (a.metrics[m] !== b[m]) return false;
  }
  return JSON.stringify(r.pareto) === JSON.stringify(o.pareto);
}
function sensitivitySync(fx) {
  const r = CORE.optimizePlansSync(fx.context, fx.scenario);
  const budgets = CORE.sensitivityBudgets(fx.scenario.budget);
  r.sensitivity = budgets.map((b) => { const x = CORE.optimizePlansSync(fx.context, fx.scenario, { budget: b });
    return { budget: x.budget, status: x.status, reasons: x.reasons || [], feasible_count: x.feasible_count,
      objectives: x.objectives && Object.fromEntries(Object.entries(x.objectives).map(([k, v]) => [k, { selected_ids: v.selected_ids, metrics: v.metrics }])) }; });
  return r;
}
const shuffle = (a, s) => { const b = a.slice(); let x = s; for (let i = b.length - 1; i > 0; i--) { x = (x * 1103515245 + 12345) % 2147483648; const j = x % (i + 1); [b[i], b[j]] = [b[j], b[i]]; } return b; };

(async () => {
  // 1. core vs independent Python oracle
  let mism = [];
  for (const { d, f, fx } of FIX) {
    const e = EXP[d][f];
    if (!sameAsOracle(CORE.optimizePlansSync(fx.context, fx.scenario), e.main)) mism.push(f + ":main");
    for (const [b, o] of Object.entries(e.sensitivity)) if (!sameAsOracle(CORE.optimizePlansSync(fx.context, fx.scenario, { budget: +b }), o)) mism.push(f + ":" + b);
  }
  check("core = Python oracle on all fixtures (main + sensitivity budgets)", mism.length === 0, mism);

  // 2-3. runner chunks and worker_threads give exactly the synchronous result, with sensitivity
  for (const mode of ["chunks", "worker"]) {
    const runner = R.createPlanRunner({ engine: CORE, mode, workerFactory: R.nodeWorkerFactory(WORKER), chunkMasks: 2048 });
    const bad = [];
    for (const { f, fx } of FIX) {
      const env = await runner.run(fx.context, fx.scenario, { sensitivity: true }).promise;
      const want = sensitivitySync(fx);
      if (env.mode !== mode || JSON.stringify(strip(env.result)) !== JSON.stringify(strip(want))) bad.push({ f, mode: env.mode, status: env.status });
    }
    check(`runner mode=${mode}: result identical to synchronous search on ${FIX.length} fixtures (with sensitivity)`, bad.length === 0, bad);
    runner.dispose();
    const s = runner.state();
    check(`runner mode=${mode}: dispose releases worker and timers`, !s.worker_alive && s.pending_timers === 0 && s.active === null, s);
  }

  // 4. progress events: monotone, tagged, end at 1
  for (const mode of ["chunks", "worker"]) {
    const ev = [];
    const runner = R.createPlanRunner({ engine: CORE, mode, workerFactory: R.nodeWorkerFactory(WORKER), chunkMasks: 4096, onProgress: (e) => ev.push(e) });
    const job = runner.run(bench.context, bench.scenario, { sensitivity: true });
    const env = await job.promise;
    const mono = ev.every((e, i) => i === 0 || e.fraction >= ev[i - 1].fraction);
    const tagged = ev.every((e) => e.request_id === job.request_id && e.problem_digest === job.problem_digest);
    check(`progress mode=${mode}: ${ev.length} events, monotone, tagged with request_id/problem_digest, reaches 1`,
      env.status === "optimal" && ev.length >= 4 && mono && tagged && Math.abs(ev[ev.length - 1].fraction - 1) < 1e-12, { n: ev.length, last: ev[ev.length - 1] });
    runner.dispose();
  }

  // 5. cancel mid-run: no result, acknowledgement or hard kill, runner reusable afterwards
  for (const mode of ["chunks", "worker"]) {
    let fired = false;
    const runner = R.createPlanRunner({ engine: CORE, mode, workerFactory: R.nodeWorkerFactory(WORKER), chunkMasks: 1024,
      onProgress: (e) => { if (!fired && e.fraction > 0.2) { fired = true; runner.cancel(); } } });
    const env = await runner.run(bench.context, bench.scenario, { sensitivity: true }).promise;
    await new Promise((r) => setTimeout(r, 400));  // > cancelGraceMs: either ack or hard termination has happened
    const s = runner.state();
    const again = await runner.run(bench.context, bench.scenario).promise;
    const want = CORE.optimizePlansSync(bench.context, bench.scenario);
    check(`cancel mode=${mode}: status cancelled without result, no pending cancel/timers, next run correct`,
      env.status === "cancelled" && !env.result && s.pending_cancels === 0 && s.active === null && s.pending_timers === 0 &&
      again.status === "optimal" && JSON.stringify(strip(again.result)) === JSON.stringify(strip(want)),
      { env: env.status, state: s });
    if (mode === "worker") check("cancel mode=worker: worker acknowledged within the grace period (no hard kill needed)",
      s.stats.cancel_acks === 1 && s.stats.hard_terminations === 0, s.stats);
    runner.dispose();
  }

  // 6. supersede: a newer run invalidates the older one; stale result never applies
  for (const mode of ["chunks", "worker"]) {
    const runner = R.createPlanRunner({ engine: CORE, mode, workerFactory: R.nodeWorkerFactory(WORKER), chunkMasks: 2048 });
    const a = runner.run(bench.context, bench.scenario);
    const scB = Object.assign({}, bench.scenario, { budget: 500000 });
    const b = runner.run(bench.context, scB);
    const [ea, eb] = await Promise.all([a.promise, b.promise]);
    await new Promise((r) => setTimeout(r, 400));
    const want = CORE.optimizePlansSync(bench.context, scB);
    check(`supersede mode=${mode}: old run 'superseded', new run optimal and equal to sync, isCurrent only for the new one`,
      ea.status === "superseded" && !ea.result && eb.status === "optimal" && a.problem_digest !== b.problem_digest &&
      JSON.stringify(strip(eb.result)) === JSON.stringify(strip(want)) && runner.isCurrent(eb) && !runner.isCurrent(ea),
      { ea: ea.status, eb: eb.status, stats: runner.state().stats });
    runner.dispose();
  }

  // 7. a worker that never acknowledges cancel is terminated after the grace period; a queued job is re-dispatched
  {
    const fakes = [];
    const stuckFactory = () => { const w = { onmessage: null, onerror: null, terminated: false, posted: [],
      postMessage(m) { this.posted.push(m.type); }, terminate() { this.terminated = true; } }; fakes.push(w); return w; };
    const runner = R.createPlanRunner({ engine: CORE, mode: "worker", workerFactory: stuckFactory, cancelGraceMs: 50 });
    const job = runner.run(bench.context, bench.scenario);
    runner.cancel();
    const env = await job.promise;
    await new Promise((r) => setTimeout(r, 120));
    const s = runner.state();
    check("stuck worker: cancel resolves at once, worker hard-terminated after grace, timers cleared",
      env.status === "cancelled" && fakes[0].terminated && s.stats.hard_terminations === 1 && s.pending_timers === 0 && !s.worker_alive, s);
    // supersede onto a stuck worker: the hard kill must restart the newer job on a fresh worker
    const r2 = R.createPlanRunner({ engine: CORE, mode: "worker", workerFactory: stuckFactory, cancelGraceMs: 50 });
    r2.run(bench.context, bench.scenario);
    const jobB = r2.run(bench.context, Object.assign({}, bench.scenario, { budget: 400000 }));
    await new Promise((r) => setTimeout(r, 120));
    const s2 = r2.state();
    const w2 = fakes[fakes.length - 1];
    check("stuck worker + newer job: newer job re-dispatched to a fresh worker after hard kill",
      s2.stats.redispatched === 1 && s2.active === jobB.request_id && w2.posted.includes("start") && !w2.terminated, s2);
    r2.dispose();
    runner.dispose();
  }

  // 7b. stale messages injected deterministically: result/progress of an older request or with a foreign digest
  {
    let fake = null;
    const factory = () => (fake = { onmessage: null, onerror: null, postMessage() {}, terminate() {} });
    const seen = [];
    const runner = R.createPlanRunner({ engine: CORE, mode: "worker", workerFactory: factory, cancelGraceMs: 10000, onProgress: (e) => seen.push(e) });
    const a = runner.run(bench.context, bench.scenario);
    const b = runner.run(bench.context, Object.assign({}, bench.scenario, { budget: 300000 }));
    const fakeResult = { status: "optimal", fake: true };
    fake.onmessage({ data: { type: "progress", request_id: a.request_id, problem_digest: a.problem_digest, phase: "main", done_masks: 1, all_masks: 2 } });
    fake.onmessage({ data: { type: "result", request_id: a.request_id, problem_digest: a.problem_digest, result: fakeResult } });
    fake.onmessage({ data: { type: "result", request_id: b.request_id, problem_digest: a.problem_digest, result: fakeResult } });
    await new Promise((r) => setTimeout(r, 20));
    const stillActive = runner.state().active === b.request_id;
    const realB = CORE.optimizePlansSync(bench.context, Object.assign({}, bench.scenario, { budget: 300000 }));
    fake.onmessage({ data: { type: "result", request_id: b.request_id, problem_digest: b.problem_digest, result: realB } });
    const eb = await b.promise, ea = await a.promise;
    check("stale messages (old request_id, or right request_id with foreign digest) are ignored; only the matching result settles",
      stillActive && seen.length === 0 && ea.status === "superseded" && eb.status === "optimal" && !eb.result.fake &&
      runner.state().stats.stale_messages_ignored === 3, { stillActive, progress_seen: seen.length, stats: runner.state().stats });
    runner.dispose();
  }

  // 7c. chunks mode stops computing after cancel (no progress for the cancelled request afterwards)
  {
    const after = [];
    let cancelledAt = null, rid = null;
    const runner = R.createPlanRunner({ engine: CORE, mode: "chunks", sliceMs: 2,
      onProgress: (e) => { if (cancelledAt !== null && e.request_id === rid) after.push(e); else if (cancelledAt === null && e.fraction > 0.1) { cancelledAt = Date.now(); runner.cancel(); } } });
    const job = runner.run(bench.context, bench.scenario, { sensitivity: true });
    rid = job.request_id;
    const env = await job.promise;
    await new Promise((r) => setTimeout(r, 300));
    check("chunks cancel: no further slices/progress for the cancelled request", env.status === "cancelled" && after.length === 0, { after: after.length });
    runner.dispose();
  }

  // 8. invalid scenario: typed error, no work started, runner state unchanged
  {
    const runner = R.createPlanRunner({ engine: CORE, mode: "chunks" });
    const ok = await runner.run(bench.context, bench.scenario).promise;
    const bad = await runner.run(bench.context, Object.assign({}, bench.scenario, { budget: 1e999 })).promise;
    const bad2 = await runner.run(bench.context, Object.assign({}, bench.scenario, { source_snapshot: "other" })).promise;
    const bad3 = await runner.run(bench.context, Object.assign({}, bench.scenario, { derived_results: { mean: ["C00"] }, extra: 1 })).promise;
    check("invalid scenario: typed errors (bad_budget, bad_snapshot, unknown_field); previous result object untouched",
      bad.status === "error" && bad.code === "bad_budget" && bad2.code === "bad_snapshot" && bad3.code === "unknown_field" &&
      ok.status === "optimal" && runner.state().active === null, [bad.code, bad2.code, bad3.code]);
    runner.dispose();
  }

  // 9. digests: order-independent; selected_ids only in scenario digest; parameters change problem digest
  {
    const sc = CORE.validatePlanScenario(bench.scenario, bench.context);
    const sh = Object.assign({}, bench.scenario, { control_points: shuffle(bench.scenario.control_points, 7), candidates: shuffle(bench.scenario.candidates, 9) });
    const sc2 = CORE.validatePlanScenario(sh, bench.context);
    const sel = CORE.validatePlanScenario(Object.assign({}, bench.scenario, { selected_ids: ["C03"] }), bench.context);
    const bud = CORE.validatePlanScenario(Object.assign({}, bench.scenario, { budget: 999999 }), bench.context);
    const w = JSON.parse(JSON.stringify(bench.scenario)); w.control_points[0].weight = w.control_points[0].weight === 1 ? 2 : 1;
    const ws = CORE.validatePlanScenario(w, bench.context);
    const rA = CORE.optimizePlansSync(bench.context, bench.scenario), rB = CORE.optimizePlansSync(bench.context, sh);
    check("problem_digest independent of array order; selected_ids only in scenario_digest; budget/weight change digest; shuffled input -> same plan",
      CORE.problemDigest(sc) === CORE.problemDigest(sc2) && CORE.problemDigest(sc) === CORE.problemDigest(sel) &&
      CORE.scenarioDigest(sc) !== CORE.scenarioDigest(sel) && CORE.problemDigest(sc) !== CORE.problemDigest(bud) &&
      CORE.problemDigest(sc) !== CORE.problemDigest(ws) && JSON.stringify(strip(rA)) === JSON.stringify(strip(rB)));
  }

  // 10. auto mode falls back to chunks when the worker cannot be created
  {
    const runner = R.createPlanRunner({ engine: CORE, mode: "auto", workerFactory: () => { throw new Error("SecurityError: Worker from file:// denied (simulated)"); } });
    const env = await runner.run(bench.context, bench.scenario).promise;
    check("auto mode: worker creation failure -> chunks, fallback reason reported, result optimal",
      env.mode === "chunks" && env.status === "optimal" && /simulated/.test(env.fallback || ""), { mode: env.mode, fallback: env.fallback });
    runner.dispose();
  }

  // 11. manual plan evaluation rows (namespace of nearest record, null semantics, feasibility reasons)
  {
    const e1 = load("synthetic", "syn_empty_baseline.json");
    const ev1 = CORE.evaluatePlan(e1.context, e1.scenario, []);
    const fx = load("synthetic", "syn_required_excluded.json");
    const ev2 = CORE.evaluatePlan(fx.context, fx.scenario, ["a", "b"]);
    const ev3 = CORE.evaluatePlan(fx.context, fx.scenario, ["d", "b"]);
    check("evaluatePlan: empty set -> after null (not 0), delta null; infeasible reasons; hypothetical vs source namespace",
      ev1.rows.every((r) => r.before_mm === null && r.after_mm === null && r.delta_mm === null) && ev1.metrics.unknown_count === 5 &&
      ev1.metrics.weighted_mean_mm === null && ev1.metrics.max_mm === null &&
      !ev2.feasible && ev2.reasons.includes("missing_required") && ev2.reasons.includes("contains_excluded") &&
      ev3.feasible && ev3.rows.some((r) => r.nearest_after && r.nearest_after.kind === "source") &&
      ev3.rows.every((r) => r.nearest_after && ["source", "hypothetical"].includes(r.nearest_after.kind)),
      { ev2: ev2.reasons, ev3: ev3.rows.map((r) => r.nearest_after) });
  }

  const summary = { pass: results.filter((r) => r.ok).length, fail: results.filter((r) => !r.ok).length };
  console.log("summary:", JSON.stringify(summary));
  const outIdx = process.argv.indexOf("--out");
  if (outIdx > 0) fs.writeFileSync(process.argv[outIdx + 1], JSON.stringify({ tool: "tests/harness.cjs", node: process.version, summary, results }, null, 1) + "\n");
  process.exitCode = summary.fail ? 1 : 0;  // no process.exit(): the process must end by itself (proves released workers/timers)
})();
