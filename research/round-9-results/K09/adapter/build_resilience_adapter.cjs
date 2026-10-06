// K09 r9 — адаптер к НАСТОЯЩЕМУ web/resilience.js сборки (city-resilience-v1), без DOM; модули из байтовой копии
// закреплённого SHA (scripts/pin_build.py). Движок не копируется и не меняется.
//
//   node adapter/build_resilience_adapter.cjs --web <copy>/prototypes/city-evidence/web --in envelopes.jsonl --out build.jsonl [--repeats 3]
//   node adapter/build_resilience_adapter.cjs --web ... --validate invalid.jsonl --out codes.jsonl
//
// Вход: строки {task_key, city, category, envelope} (scripts/run_t3.py --emit-envelopes).
// source_snapshot плана заменяется на snapshot контекста BUILD (snapshot K09 другой и в BUILD не используется) — единственная правка входа.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const { performance } = require("perf_hooks");

function arg(name, def) { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : def; }
const W = arg("--web"), IN = arg("--in"), VAL = arg("--validate"), OUT = arg("--out"), REPEATS = Number(arg("--repeats", "1"));
if (!W || (!IN && !VAL) || !OUT) { console.error("usage: --web <dir> (--in <jsonl> | --validate <jsonl>) --out <jsonl> [--repeats N]"); process.exit(2); }

const c0 = {}; vm.createContext(c0); c0.window = c0;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), c0, { filename: "data.js" });
const F = require(path.resolve(W, "facts.js"));
const PL = require(path.resolve(W, "plan.js"));
const RS = require(path.resolve(W, "resilience.js"));
const D = c0.CITY_EVIDENCE;
const ctxs = {};
const ctxFor = (city) => ctxs[city] || (ctxs[city] = PL.makeContext(D, city, F));

const vec = (v) => (v ? { unknown_count: v.unknown_count, weighted_sum_mm: v.weighted_sum_mm, max_mm: v.max_mm } : null);
const view = (p) => p && {
  ids: p.selected_ids, cost: p.cost, feasible: p.feasibility.feasible, W: vec(p.worst_vector), worst_case_ids: p.worst_case_ids,
  base_weighted_mean_mm: p.base_weighted_mean_mm,
  per_case: p.per_case.map((c) => ({ case_id: c.case_id, loss: vec(c.loss), covered_weight: c.metrics.covered_weight, weighted_mean_mm: c.metrics.weighted_mean_mm, source_records: c.source_records,
    rows: c.rows.map((r) => [r.id, r.before_mm, r.nearest_before ? r.nearest_before.kind + ":" + r.nearest_before.id : null, r.after_mm,
      r.nearest_after ? r.nearest_after.kind + ":" + r.nearest_after.id : null, r.delta_mm]) })),
};

function runTask(t) {
  const ctx = ctxFor(t.city);
  const env = JSON.parse(JSON.stringify(t.envelope));
  env.plan.source_snapshot = ctx.source_snapshot;
  const out = { task_key: t.task_key };
  let r = null, best = Infinity;
  try {
    for (let k = 0; k < Math.max(1, REPEATS); k++) {
      const t0 = performance.now();
      r = RS.optimizeResilience(ctx, env, { F });
      const dt = performance.now() - t0;
      if (dt < best) best = dt;
    }
  } catch (e) { out.error = e.code || String(e.message); return out; }
  Object.assign(out, { t_ms: best, status: r.status, reason_codes: (r.reasons || []).map((x) => x.code), cases: r.cases,
    nominal: view(r.nominal), robust: view(r.robust), same_plan: r.same_plan === undefined ? null : r.same_plan,
    price_of_robustness_m: r.price_of_robustness_m, price_reason: r.price_reason, evaluated: r.evaluated, total_subsets: r.total_subsets,
    feasible_count: r.feasible_count, duplicate_case_groups: r.duplicate_case_groups || [] });
  return out;
}

function validateTask(t) {
  const ctx = ctxFor(t.city);
  const env = t.envelope;
  if (env && env.plan && typeof env.plan === "object" && t.keep_snapshot !== true) env.plan.source_snapshot = ctx.source_snapshot;
  try { RS.validateResilience(env, ctx); return { task_key: t.task_key, result: "accepted" }; }
  catch (e) { return { task_key: t.task_key, result: e.code || String(e.message) }; }
}

const src = fs.readFileSync(IN || VAL, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const t0 = performance.now();
const rows = src.map(IN ? runTask : validateTask);
fs.writeFileSync(OUT, rows.map((r) => JSON.stringify(r)).join("\n") + "\n");
console.log(JSON.stringify({ tasks: rows.length, wall_ms: Math.round(performance.now() - t0), node: process.version, platform: process.platform, arch: process.arch }));
