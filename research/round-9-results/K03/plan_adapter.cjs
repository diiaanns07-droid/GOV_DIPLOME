// K03 r9: небольшой адаптер к НАСТОЯЩЕМУ web/plan.js сборки (Node, без DOM). Сам ничего не вычисляет:
// только вызывает makeContext / validatePlanScenario / precompute / evaluatePlan / facts.qaOf и упаковывает ответ.
//   node plan_adapter.cjs <request.json>
// request = {app_root, cases: [{id, op, city, category?, places?, selected_ids?, allow_empty?, ids?, disabled_source_ids?}]}
// Печатает JSON-массив [{id, ok, result | error:{code, detail}}]. data.js/evidence.js — из app_root/web, как в tests/plan.cjs сборки.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const req = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const W = path.join(req.app_root, "web");
const fileSha = (f) => crypto.createHash("sha256").update(fs.readFileSync(path.join(W, f))).digest("hex");
const shaBefore = { "data.js": fileSha("data.js"), "evidence.js": fileSha("evidence.js") };
const box = {}; vm.createContext(box); box.window = box;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), box, { filename: f });
globalThis.CITY_OBS = box.CITY_OBS;  // facts.qaOf читает root.CITY_OBS (в Node root = globalThis)
const F = require(path.join(W, "facts.js")), X = require(path.join(W, "whatif.js")), PL = require(path.join(W, "plan.js"));
const D = box.CITY_EVIDENCE;
const dataJsonBefore = JSON.stringify(D);

const ctxCache = new Map();
const ctxOf = (city) => { if (!ctxCache.has(city)) ctxCache.set(city, PL.makeContext(D, city, F)); return ctxCache.get(city); };
// NaN/Infinity в JSON запроса закодированы {"$num": "NaN" | "Infinity" | "-Infinity"} (как в fixtures r8)
const revive = (v) => Array.isArray(v) ? v.map(revive) : v && typeof v === "object"
  ? ("$num" in v && Object.keys(v).length === 1 ? Number(v.$num) : Object.fromEntries(Object.entries(v).map(([k, x]) => [k, revive(x)]))) : v;

// Полный сценарий city-plan-v2 из мест fixture: ограничения не мешают (бюджет и max_selected максимальны, без required/excluded).
function scenarioInput(ctx, c) {
  return { schema_version: PL.SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, category: c.category,
    control_points: c.places.control_points, candidates: c.places.candidates, budget: PL.LIMITS.budget[1], max_selected: PL.LIMITS.max_selected,
    coverage_radius_m: 1000, required_ids: [], excluded_ids: [], selected_ids: c.selected_ids || [] };
}
// Вычислительное представление случая: исходные записи без disabled_source_ids; контекст сборки не меняется (он заморожен).
function caseView(ctx, disabled) {
  const off = new Set(disabled || []);
  return Object.freeze({ ...ctx, places: Object.freeze(ctx.places.filter((p) => !off.has(p.id))) });
}
const qaOf = (city, id) => {
  const p = D.cities[city].places.find((x) => x.id === id);
  return p ? F.qaOf(city, p).map((q) => ({ code: q.code, ids: q.ids.slice(), text: q.text })) : null;
};

const out = [];
for (const c of req.cases) {
  try {
    let result;
    if (c.op === "tomm") result = c.values.map((m) => PL.mmOf(m));
    else if (c.op === "dist") result = c.pairs.map(([a, b]) => PL.mmOf(X.haversine(a[0], a[1], b[0], b[1])));
    else if (c.op === "inbbox") result = c.points.map(([lon, lat]) => X.inBbox(ctxOf(c.city).bbox, lon, lat));
    else if (c.op === "validate_raw") { const sc = PL.validatePlanScenario(c.scenario, ctxOf(c.city)); result = { city_id: sc.city_id, source_snapshot: sc.source_snapshot }; }
    else if (c.op === "qa") result = c.ids.map((id) => ({ id, qa: qaOf(c.city, id) }));
    else if (c.op === "context") {
      const ctx = ctxOf(c.city);
      result = { city_id: ctx.city_id, bbox: ctx.bbox, release: ctx.release, source_snapshot: ctx.source_snapshot, versions: ctx.versions,
        frozen: Object.isFrozen(ctx) && Object.isFrozen(ctx.places) && ctx.places.every(Object.isFrozen),
        places: ctx.places.map((p) => [p.id, p.group, p.lon, p.lat]),
        snapshot_recomputed: PL.sourceSnapshot(D, c.city, F) };
    } else {
      const ctx0 = ctxOf(c.city), ctx = c.disabled_source_ids ? caseView(ctx0, c.disabled_source_ids) : ctx0;
      const sc = PL.validatePlanScenario(revive(scenarioInput(ctx0, c)), ctx, { requirePoints: !c.allow_empty });
      if (c.op === "validate") result = { control_points: sc.control_points.map((p) => p.id), candidates: sc.candidates.map((q) => [q.id, q.kind]) };
      else if (c.op === "table") {
        const P = PL.precompute(ctx, sc);
        result = { source_count: P.src.length,
          base: Object.fromEntries(P.pts.map((p, j) => [p.id, P.base[j] ? { id: P.base[j].id, mm: P.base[j].mm } : null])),
          dist: Object.fromEntries(P.cands.map((q, i) => [q.id, Object.fromEntries(P.pts.map((p, j) => [p.id, P.dist[i][j].mm]))])) };
      } else if (c.op === "after") {
        const ev = PL.evaluatePlan(ctx, sc, sc.selected_ids);
        result = { source_candidates: ev.source_candidates, metric_version: ev.metric_version, selected_ids: ev.selected_ids,
          rows: ev.rows.map((r) => ({ id: r.id, before_mm: r.before_mm, nearest_before: r.nearest_before, after_mm: r.after_mm,
            nearest_after: r.nearest_after, delta_mm: r.delta_mm })),
          metrics: { unknown_count: ev.metrics.unknown_count, weighted_sum_mm: ev.metrics.weighted_sum_mm, max_mm: ev.metrics.max_mm },
          baseline: { unknown_count: ev.baseline.unknown_count, weighted_sum_mm: ev.baseline.weighted_sum_mm, max_mm: ev.baseline.max_mm } };
      } else throw new Error("unknown op " + c.op);
    }
    out.push({ id: c.id, ok: true, result });
  } catch (e) {
    if (!(e instanceof PL.PlanError)) { out.push({ id: c.id, ok: false, crash: String(e && e.stack || e).slice(0, 400) }); continue; }
    out.push({ id: c.id, ok: false, error: { code: e.code, detail: String(e.detail).slice(0, 200) } });
  }
}
// Инвариант: ни один вызов не изменил данные сборки (ни файл, ни загруженный объект).
const integrity = { data_js_sha256: fileSha("data.js"), evidence_js_sha256: fileSha("evidence.js"),
  file_unchanged: fileSha("data.js") === shaBefore["data.js"] && fileSha("evidence.js") === shaBefore["evidence.js"],
  loaded_data_unchanged: JSON.stringify(D) === dataJsonBefore,
  snapshots: Object.fromEntries([...ctxCache].map(([city, ctx]) => [city, { ctx: ctx.source_snapshot, recomputed: PL.sourceSnapshot(D, city, F) }])) };
process.stdout.write(JSON.stringify({ results: out, integrity }));
