// K03 r9: адаптер к web/resilience.js сборки (Node, без DOM). Только вызывает публичные функции сборки и упаковывает ответ.
//   node resilience_adapter.cjs <request.json>
// request = {app_root, cases: [{id, op: validate|evaluate|optimize|export|import|probe_ctx, city, env?, text?, selected?}]}
// Если web/resilience.js в сборке нет — {available: false} (тесты устойчивости = NOT_RUN, не PASS).
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const req = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const W = path.join(req.app_root, "web");
if (!fs.existsSync(path.join(W, "resilience.js"))) { process.stdout.write(JSON.stringify({ available: false })); process.exit(0); }
const fileSha = (f) => crypto.createHash("sha256").update(fs.readFileSync(path.join(W, f))).digest("hex");
const before = { data: fileSha("data.js"), evidence: fileSha("evidence.js") };
const box = {}; vm.createContext(box); box.window = box;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), box, { filename: f });
globalThis.CITY_OBS = box.CITY_OBS;
const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js")), RS = require(path.join(W, "resilience.js"));
const D = box.CITY_EVIDENCE;
const dataJson = JSON.stringify(D), evJson = JSON.stringify(box.CITY_OBS);
const ctxs = new Map();
const ctxOf = (city) => { if (!ctxs.has(city)) ctxs.set(city, PL.makeContext(D, city, F)); return ctxs.get(city); };
const ctxJson = new Map();
const plain = (v) => JSON.parse(JSON.stringify(v, (k, x) => (x === Infinity ? "Infinity" : x)));
const slimPlan = (p) => p && { selected_ids: p.selected_ids, cost: p.cost, feasible: p.feasibility.feasible, worst_vector: p.worst_vector, worst_case_ids: p.worst_case_ids,
  base_weighted_mean_mm: p.base_weighted_mean_mm,
  per_case: p.per_case.map((c) => ({ case_id: c.case_id, disabled_count: c.disabled_count, source_records: c.source_records, loss: c.loss,
    metrics: { unknown_count: c.metrics.unknown_count, weighted_sum_mm: c.metrics.weighted_sum_mm, max_mm: c.metrics.max_mm, weighted_mean_mm: c.metrics.weighted_mean_mm },
    rows: c.rows.map((r) => ({ id: r.id, before_mm: r.before_mm, nearest_before: r.nearest_before, after_mm: r.after_mm, nearest_after: r.nearest_after, delta_mm: r.delta_mm })) })) };

const out = [];
for (const c of req.cases) {
  try {
    const ctx = c.city ? ctxOf(c.city) : null;
    if (ctx && !ctxJson.has(c.city)) ctxJson.set(c.city, JSON.stringify(ctx));
    let result;
    if (c.op === "validate") result = RS.validateResilience(c.env, ctx);
    else if (c.op === "evaluate") result = slimPlan(RS.evaluateResilience(ctx, c.env, c.selected || []));
    else if (c.op === "optimize") {
      const r = RS.optimizeResilience(ctx, c.env, { F });
      result = { status: r.status, reasons: r.reasons, nominal: slimPlan(r.nominal), robust: slimPlan(r.robust), same_plan: r.same_plan, evaluated: r.evaluated,
        total_subsets: r.total_subsets, feasible_count: r.feasible_count, duplicate_case_groups: r.duplicate_case_groups, price_of_robustness_m: r.price_of_robustness_m,
        price_reason: r.price_reason, source_snapshot: r.source_snapshot, metric_version: r.metric_version, objective_version: r.objective_version, cases: r.cases,
        exclusions_digest: r.exclusions_digest, resilience_problem_digest: r.resilience_problem_digest };
    } else if (c.op === "export") result = RS.exportResilience(ctx, c.env);
    else if (c.op === "import") { const r = RS.importResilience(c.text, ctxOf); result = { envelope: r.envelope, city: r.ctx.city_id }; }
    else throw new Error("unknown op " + c.op);
    out.push({ id: c.id, ok: true, result: plain(result) });
  } catch (e) {
    if (!(e instanceof PL.PlanError)) { out.push({ id: c.id, ok: false, crash: String(e && e.stack || e).slice(0, 400) }); continue; }
    out.push({ id: c.id, ok: false, error: { code: e.code, detail: String(e.detail).slice(0, 200) } });
  }
}
const integrity = { file_unchanged: fileSha("data.js") === before.data && fileSha("evidence.js") === before.evidence,
  loaded_unchanged: JSON.stringify(D) === dataJson && JSON.stringify(box.CITY_OBS) === evJson,
  ctx_unchanged: [...ctxs].every(([city, ctx]) => JSON.stringify(ctx) === ctxJson.get(city)),
  snapshots: Object.fromEntries([...ctxs].map(([city, ctx]) => [city, { ctx: ctx.source_snapshot, recomputed: PL.sourceSnapshot(D, city, F) }])),
  limits: RS.LIMITS, schema: RS.SCHEMA, objective: RS.OBJECTIVE };
process.stdout.write(JSON.stringify({ available: true, results: out, integrity }));
