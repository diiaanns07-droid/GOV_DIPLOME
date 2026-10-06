// K09 r9 — адаптер к НАСТОЯЩЕМУ web/plan.js сборки (city-plan-v2), без DOM. Движок не копируется и не меняется:
// модули загружаются из байтовой копии закреплённого SHA (scripts/pin_build.py).
//
//   node adapter/build_plan_adapter.cjs --web <copy>/prototypes/city-evidence/web --in tasks.jsonl --out build.jsonl [--repeats 3]
//
// Вход (JSONL, по задаче): {task_id, city, category, baseline: "real_slice_records"|"empty_synthetic_condition",
//   scenario: {control_points, candidates, budget, max_selected, coverage_radius_m, required_ids, excluded_ids, selected_ids},
//   selections: [[candidate ids], ...]}
// Контекст: PL.makeContext(data.js, city) — реальный срез. Условие без записей (empty_synthetic_condition) строится адаптером:
// копия data.cities[city] без записей этой категории → другой source_snapshot (это тестовый контекст, не данные продукта).
// source_snapshot сценария берётся из контекста BUILD (r8-snapshot K09 другой и в BUILD не используется).
// Выход (JSONL): статус, коды причин, objectives, Парето, чувствительность, evaluatePlan для selections, время (мс).
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const { performance } = require("perf_hooks");

function arg(name, def) { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : def; }
const W = arg("--web"), IN = arg("--in"), OUT = arg("--out"), REPEATS = Number(arg("--repeats", "1"));
if (!W || !IN || !OUT) { console.error("usage: --web <dir> --in <jsonl> --out <jsonl> [--repeats N]"); process.exit(2); }

const c0 = {}; vm.createContext(c0); c0.window = c0;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), c0, { filename: "data.js" });
const F = require(path.resolve(W, "facts.js"));
const PL = require(path.resolve(W, "plan.js"));
const D = c0.CITY_EVIDENCE;

const ctxCache = new Map();
function contextFor(city, category, baseline) {
  const key = `${city}|${category}|${baseline}`;
  if (ctxCache.has(key)) return ctxCache.get(key);
  let ctx;
  if (baseline === "real_slice_records") ctx = PL.makeContext(D, city, F);
  else if (baseline === "empty_synthetic_condition") {
    const c = D.cities[city];
    const data = { cities: { [city]: { ...c, places: c.places.filter((p) => p.group !== category) } } };
    ctx = PL.makeContext(data, city, F);
  } else throw new Error("unknown baseline " + baseline);
  ctxCache.set(key, ctx);
  return ctx;
}

const pickObj = (o) => (o ? { ids: o.ids, cost: o.cost, unknown_count: o.unknown_count, weighted_sum_mm: o.weighted_sum_mm, max_mm: o.max_mm, covered_weight: o.covered_weight } : null);

function runTask(t) {
  const ctx = contextFor(t.city, t.category, t.baseline);
  const out = { task_id: t.task_id, n_sources: ctx.places.filter((p) => p.group === t.category).length, source_snapshot: ctx.source_snapshot };
  let sc;
  try {
    sc = PL.validatePlanScenario({ schema_version: PL.SCHEMA, city_id: t.city, source_snapshot: ctx.source_snapshot, category: t.category, ...t.scenario }, ctx);
  } catch (e) { out.validation_error = e.code || String(e.message); return out; }
  let r = null, best = Infinity;
  for (let k = 0; k < Math.max(1, REPEATS); k++) {
    const t0 = performance.now();
    r = PL.optimizePlans(ctx, sc, { F });
    const dt = performance.now() - t0;
    if (dt < best) best = dt;
  }
  out.t_optimize_ms = best;
  out.status = r.status;
  out.reason_codes = (r.reasons || []).map((x) => x.code);
  out.feasible_count = r.feasible_count;
  out.evaluated = r.evaluated;
  out.total_subsets = r.total_subsets;
  out.problem_digest = r.problem_digest;
  out.objectives = r.objectives ? Object.fromEntries(Object.entries(r.objectives).map(([k, v]) => [k, pickObj(v)])) : null;
  out.pareto = r.pareto.map((p) => ({ ids: p.ids, cost: p.cost, weighted_sum_mm: p.weighted_sum_mm }));
  out.pareto_excluded_unknown = r.pareto_excluded_unknown === undefined ? null : r.pareto_excluded_unknown;
  out.sensitivity = PL.sensitivity(ctx, sc, { F }).map((x) => ({ budget: x.budget, status: x.status, reason_codes: (x.reasons || []).map((y) => y.code),
    ids: x.objectives ? { mean: x.objectives.mean.ids, minimax: x.objectives.minimax.ids, coverage: x.objectives.coverage.ids } : null }));
  out.evals = (t.selections || []).map((ids) => {
    const ev = PL.evaluatePlan(ctx, sc, ids);
    const m = ev.metrics;
    return { ids: ev.selected_ids, feasible: ev.feasibility.feasible, reason_codes: ev.feasibility.reasons.map((x) => x.code),
      metrics: { unknown_count: m.unknown_count, weighted_sum_mm: m.weighted_sum_mm, weighted_mean_mm: m.weighted_mean_mm, max_mm: m.max_mm,
        covered_weight: m.covered_weight, total_weight: m.total_weight, cost: m.cost },
      rows: ev.rows.map((x) => [x.id, x.before_mm, x.after_mm, x.delta_mm, x.nearest_after ? x.nearest_after.kind + ":" + x.nearest_after.id : null]) };
  });
  return out;
}

const lines = fs.readFileSync(IN, "utf8").split("\n").filter(Boolean);
const outLines = [];
const t0 = performance.now();
for (const line of lines) outLines.push(JSON.stringify(runTask(JSON.parse(line))));
fs.writeFileSync(OUT, outLines.join("\n") + "\n");
console.log(JSON.stringify({ tasks: lines.length, wall_ms: Math.round(performance.now() - t0), node: process.version, platform: process.platform, arch: process.arch }));
