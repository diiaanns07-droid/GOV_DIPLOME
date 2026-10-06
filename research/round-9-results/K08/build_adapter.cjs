// K08 R9: адаптер к НАСТОЯЩЕМУ BUILD (web/plan.js, headless Node). Только вызывает API сборки, движок не копирует.
// Usage: node build_adapter.cjs --app-root <prototypes/city-evidence> --jobs jobs.json --out out.json
// jobs: [{name, scenario, drop_category_sources?: bool, names?: {id: name}, city_label?, attribution?, release?, demo?}]
//   scenario.source_snapshot == "@build" -> подставляется ctx.source_snapshot сборки.
// Для каждого job вызывается то же, что plan-ui.js: validate -> export -> import -> evaluate -> optimize -> sensitivity -> reportHtml.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const arg = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };
const APP = path.resolve(arg("--app-root")), W = path.join(APP, "web");
const ctx0 = {}; vm.createContext(ctx0); ctx0.window = ctx0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx0, { filename: f });
globalThis.CITY_OBS = ctx0.CITY_OBS;  // facts.qaOf читает root.CITY_OBS (как в браузере)
const F = require(path.join(W, "facts.js"));
const PL = require(path.join(W, "plan.js"));
const D = JSON.parse(JSON.stringify(ctx0.CITY_EVIDENCE));
const jobs = JSON.parse(fs.readFileSync(arg("--jobs"), "utf8"));
const errOf = (e) => ({ code: e.code || "exception", detail: String(e.detail || e.message).slice(0, 300) });
const out = { app_root: APP, plan_schema: PL.SCHEMA, metric: PL.METRIC, jobs: [] };
for (const j of jobs) {
  const r = { name: j.name };
  try {
    const data = JSON.parse(JSON.stringify(D));
    if (j.drop_category_sources) data.cities[j.scenario.city_id].places = data.cities[j.scenario.city_id].places.filter((p) => p.group !== j.scenario.category);
    const c = data.cities[j.scenario.city_id];
    const ctx = PL.makeContext(data, j.scenario.city_id, F);
    const raw = JSON.parse(JSON.stringify(j.scenario));
    if (raw.source_snapshot === "@build") raw.source_snapshot = ctx.source_snapshot;
    r.snapshot = ctx.source_snapshot;
    const sc = PL.validatePlanScenario(raw, ctx);
    const exportText = PL.exportPlanScenario(ctx, sc, F);
    r.export_text = exportText; r.export_bytes = Buffer.byteLength(exportText, "utf8");
    try { const imp = PL.importPlanScenario(exportText, () => ctx, F); r.import = { ok: true, same: JSON.stringify(imp.scenario) === JSON.stringify(sc) }; }
    catch (e) { r.import = { ok: false, ...errOf(e) }; }
    if (j.forge) {  // подделка производных значений в экспортированном файле
      const o = JSON.parse(exportText);
      o.derived_results.manual.metrics.weighted_sum_mm += 1;
      try { PL.importPlanScenario(JSON.stringify(o), () => ctx, F); r.forge = { accepted: true }; } catch (e) { r.forge = { accepted: false, ...errOf(e) }; }
      const o2 = JSON.parse(exportText); o2.source_snapshot = "sha256:" + "0".repeat(64);
      try { PL.importPlanScenario(JSON.stringify(o2), () => ctx, F); r.foreign = { accepted: true }; } catch (e) { r.foreign = { accepted: false, ...errOf(e) }; }
    }
    const man = PL.evaluatePlan(ctx, sc, sc.selected_ids);
    const res = PL.optimizePlans(ctx, sc, { F });
    const sens = res.status === "optimal" ? PL.sensitivity(ctx, sc, { F }) : null;
    r.manual = man; r.result = res; r.sens = sens;
    r.problem_digest = PL.problemDigest(sc, F); r.scenario_digest = PL.scenarioDigest(sc, F);
    const names = j.names || Object.fromEntries(c.places.map((p) => [p.id, p.name || "Без названия"]));
    const att = [...new Set((c.attribution || []).map((a) => a.dataset))].join("; ");
    // provenance — как в proposal/report_provenance.patch (plan-ui reportProvenance); исходный BUILD это поле игнорирует
    const pids = new Set();
    for (const row of man.rows) for (const n of [row.nearest_before, row.nearest_after]) if (n && n.kind === "source") pids.add(n.id);
    const byId = Object.fromEntries(c.places.map((p) => [p.id, p]));
    const provenance = { bbox: c.bbox, places_file: c.files && c.files.places_social, records: [...pids].sort().map((id) => {
      const p = byId[id] || { id }; return { id, name: p.name || null, category: p.category || null, sources: p.sources || [],
        qa: p.lon !== undefined ? F.qaOf(j.scenario.city_id, p).map((q) => q.text) : [] }; }) };
    r.report_html = PL.reportHtml({ provenance, scenario: sc, city_label: j.city_label || c.label, release: j.release || `Overture ${c.release}`,
      problem_digest: r.problem_digest, scenario_digest: r.scenario_digest, generated: "2026-10-06 00:00:00 UTC", manual: man, result: res, sens,
      explanation: j.explanation || null, names,
      attribution: j.attribution || `Источники записей: ${att || "не указаны"} (через Overture Maps ${c.release}); лицензии ODbL-1.0 / CDLA-Permissive-2.0 / Apache-2.0 — см. web/attribution/ATTRIBUTION.md.`,
      demo: !!j.demo });
  } catch (e) { r.error = errOf(e); }
  out.jobs.push(r);
}
fs.writeFileSync(arg("--out"), JSON.stringify(out, null, 1));
console.log(out.jobs.map((x) => `${x.name}: ${x.error ? "ERROR " + x.error.code : (x.result && x.result.status) + " export " + x.export_bytes + "B import " + (x.import.ok ? "ok" : x.import.code)}`).join("\n"));
