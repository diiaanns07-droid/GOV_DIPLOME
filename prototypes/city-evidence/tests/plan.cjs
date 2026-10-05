// web/plan.js (city-plan-v2) vs the independent Python oracle (tests/expected_plans.json) + contract rules. Headless, no DOM.
// Usage: node tests/plan.cjs
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = path.join(__dirname, "..", "web");
const ctx0 = {}; vm.createContext(ctx0); ctx0.window = ctx0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx0, { filename: f });
const F = require(path.join(W, "facts.js"));
const X = require(path.join(W, "whatif.js"));
const PL = require(path.join(W, "plan.js"));
const D = ctx0.CITY_EVIDENCE;
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(detail).slice(0, 400) : "")); };
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || e.message; } };
const J = JSON.stringify;

const exp = JSON.parse(fs.readFileSync(path.join(__dirname, "expected_plans.json"), "utf8"));
// context for a case: synthetic equator "city" for hand fixtures, the real slice otherwise
function caseCtx(c) {
  if (c.kind === "synthetic_hand") {
    const data = { cities: { "synthetic-eq": { bbox: c.bbox, release: "synthetic", files: {}, places: c.places } } };
    return PL.makeContext(data, "synthetic-eq", F);
  }
  return PL.makeContext(D, c.city, F);
}
function caseScenario(c, ctx) {
  return PL.validatePlanScenario({ schema_version: PL.SCHEMA, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot, ...c.scenario }, ctx);
}
const reversed = (sc) => ({ ...sc, control_points: sc.control_points.slice().reverse(), candidates: sc.candidates.slice().reverse(),
  required_ids: sc.required_ids.slice().reverse(), excluded_ids: sc.excluded_ids.slice().reverse(), selected_ids: sc.selected_ids.slice().reverse() });

// 1. manual plan evaluation = oracle (rows in mm, nearest with kind, metrics)
for (const c of exp.cases) {
  const ctx = caseCtx(c), sc = caseScenario(c, ctx), r = PL.evaluatePlan(ctx, sc, sc.selected_ids), e = c.expected.manual;
  const rowsOk = r.rows.every((row) => { const o = e.rows[row.id]; return o && row.before_mm === o.before_mm && row.after_mm === o.after_mm && row.delta_mm === o.delta_mm
    && J(row.nearest_before) === J(o.nearest_before) && J(row.nearest_after) === J(o.nearest_after); });
  const m = r.metrics;
  const mOk = m.unknown_count === e.unknown_count && m.weighted_sum_mm === e.weighted_sum_mm && m.max_mm === e.max_mm && m.covered_weight === e.covered_weight
    && m.total_weight === e.total_weight && m.cost === e.cost && J(r.selected_ids) === J(e.ids);
  check(`evaluatePlan = oracle: ${c.name}`, rowsOk && mOk, J({ m, e: { ...e, rows: undefined } }));
  const r2 = PL.evaluatePlan(ctx, reversed(sc), reversed(sc).selected_ids);
  check(`input order does not change the result: ${c.name}`, J(r2.metrics) === J(r.metrics) && PL.problemDigest(reversed(sc), F) === PL.problemDigest(sc, F));
}

// 2. hand geometry and semantics on the synthetic equator fixture
const hand = exp.cases.find((c) => c.name === "no_baseline"), hctx = caseCtx(hand), hsc = caseScenario(hand, hctx);
const empty = PL.evaluatePlan(hctx, hsc, []);
check("no baseline + empty plan: distance null (not 0), delta null, mean/max null", empty.rows.every((r) => r.before_mm === null && r.after_mm === null && r.delta_mm === null)
  && empty.metrics.unknown_count === 3 && empty.metrics.weighted_mean_mm === null && empty.metrics.max_mm === null && empty.metrics.covered_weight === 0);
const withC = PL.evaluatePlan(hctx, hsc, ["C3"]);
check("no baseline + candidate: after known, delta still null", withC.rows.every((r) => r.after_mm !== null && r.delta_mm === null));
const one = PL.mmOf(X.haversine(0, 0, 1, 0));
check("metric haversine-mm-v1: 1° on the equator = 111195080 mm", one === 111195080, one);
const tie = exp.cases.find((c) => c.name === "source_hyp_tie"), tctx = caseCtx(tie), tsc = caseScenario(tie, tctx);
check("equal mm: source record wins over hypothetical", PL.evaluatePlan(tctx, tsc, ["C1"]).rows[0].nearest_after.kind === "source");
const ex = exp.cases.find((c) => c.name === "excluded_and_required"), ectx = caseCtx(ex), esc = caseScenario(ex, ectx);
const ef = PL.evaluatePlan(ectx, esc, esc.selected_ids).feasibility;
check("manual plan feasibility lists reasons (excluded chosen, required missing)", !ef.feasible && ef.reasons.map((x) => x.code).sort().join() === "has_excluded,missing_required", J(ef));
const rq = exp.cases.find((c) => c.name === "required_cost_over_budget"), rctx = caseCtx(rq), rsc = caseScenario(rq, rctx);
check("manual plan over budget is reported, not silently changed", PL.evaluatePlan(rctx, rsc, rsc.selected_ids).feasibility.reasons[0].code === "over_budget");

// 3. contract city-plan-v2: validation and digests
const sh = PL.makeContext(D, "shymkent", F), ast = PL.makeContext(D, "astana", F);
const real = exp.cases.find((c) => c.name === "shymkent_school_16x25");
const base = () => JSON.parse(J({ schema_version: PL.SCHEMA, city_id: "shymkent", source_snapshot: sh.source_snapshot, ...real.scenario }));
check("valid 16×25 scenario accepted", code(() => PL.validatePlanScenario(base(), sh)) === "accepted");
check("context source records frozen (immutable)", Object.isFrozen(sh.places) && Object.isFrozen(sh.places[0]) && code(() => { "use strict"; sh.places[0].lon = 0; }) !== "accepted");
check("v2 snapshot differs from v1 snapshot and between cities", sh.source_snapshot !== X.sourceSnapshot(D, "shymkent", F) && sh.source_snapshot !== ast.source_snapshot);
const rej = (name, mut, want) => { const o = base(); mut(o); check(`rejects ${name} (${want})`, code(() => PL.validatePlanScenario(o, sh)) === want); };
rej("v1 scenario (no silent migration)", (o) => { o.schema_version = X.SCHEMA; }, "wrong_version");
rej("unknown version", (o) => { o.schema_version = "city-plan-v3"; }, "bad_version");
rej("Astana scenario in Shymkent context", (o) => { o.city_id = "astana"; }, "other_city");
rej("unknown city", (o) => { o.city_id = "almaty"; }, "bad_city");
rej("foreign snapshot", (o) => { o.source_snapshot = ast.source_snapshot; }, "foreign_snapshot");
rej("unknown field", (o) => { o.script = "alert(1)"; }, "unknown_field");
rej("missing field", (o) => { delete o.coverage_radius_m; }, "missing_field");
rej("26 control points", (o) => { o.control_points = Array.from({ length: 26 }, (_, k) => ({ ...o.control_points[0], id: "Q" + k })); }, "bad_points");
rej("0 control points", (o) => { o.control_points = []; }, "bad_points");
rej("17 candidates", (o) => { o.candidates.push({ ...o.candidates[0], id: "K17" }); }, "too_many_candidates");
rej("duplicate point id", (o) => { o.control_points[1].id = o.control_points[0].id; }, "duplicate_id");
rej("duplicate candidate id", (o) => { o.candidates[1].id = o.candidates[0].id; }, "duplicate_id");
rej("id longer than 64", (o) => { o.candidates[0].id = "x".repeat(65); }, "bad_id");
rej("id with markup", (o) => { o.control_points[0].id = "<b>x</b>"; }, "bad_id");
check("Kazakh candidate / point IDs accepted", code(() => { const o = base(); o.candidates[0].id = "жаңа-мектеп"; o.control_points[0].id = "нүкте-1"; o.selected_ids = ["жаңа-мектеп"]; return PL.validatePlanScenario(o, sh); }) === "accepted");
rej("NFD id", (o) => { o.control_points[0].id = "дом-й".normalize("NFD"); }, "bad_id");
rej("weight 0", (o) => { o.control_points[0].weight = 0; }, "bad_weight");
rej("weight 1.5", (o) => { o.control_points[0].weight = 1.5; }, "bad_weight");
rej("weight 101", (o) => { o.control_points[0].weight = 101; }, "bad_weight");
rej("cost 0", (o) => { o.candidates[0].cost = 0; }, "bad_cost");
rej("cost 1000001", (o) => { o.candidates[0].cost = 1000001; }, "bad_cost");
rej("budget negative", (o) => { o.budget = -1; }, "bad_budget");
rej("budget not integer", (o) => { o.budget = 10.5; }, "bad_budget");
rej("max_selected 6", (o) => { o.max_selected = 6; }, "bad_max_selected");
rej("radius 99", (o) => { o.coverage_radius_m = 99; }, "bad_radius");
rej("radius 5001", (o) => { o.coverage_radius_m = 5001; }, "bad_radius");
rej("required unknown candidate", (o) => { o.required_ids = ["NOPE"]; }, "unknown_ref");
rej("selected unknown candidate", (o) => { o.selected_ids = ["NOPE"]; }, "unknown_ref");
rej("required ∩ excluded", (o) => { o.required_ids = ["K01"]; o.excluded_ids = ["K01"]; }, "required_excluded_overlap");
rej("duplicate in required", (o) => { o.required_ids = ["K01", "K01"]; }, "duplicate_id");
rej("candidate kind observed", (o) => { o.candidates[0].kind = "observed"; }, "bad_kind");
rej("candidate other category", (o) => { o.candidates[0].category = "outpatient_clinic"; }, "bad_category");
rej("candidate outside bbox", (o) => { o.candidates[0].lon = 70.5; }, "outside_bbox");
rej("point NaN-like string", (o) => { o.control_points[0].lat = "42.3"; }, "bad_coord");
rej("extra field in candidate", (o) => { o.candidates[0].url = "https://example.com"; }, "bad_shape");
check("derived_results field tolerated by validation (ignored)", code(() => PL.validatePlanScenario({ ...base(), derived_results: { forged: true } }, sh)) === "accepted");
const v = PL.validatePlanScenario(base(), sh);
check("problem digest ignores selected_ids; scenario digest includes them",
  PL.problemDigest({ ...v, selected_ids: [] }, F) === PL.problemDigest(v, F) && PL.scenarioDigest({ ...v, selected_ids: [] }, F) !== PL.scenarioDigest(v, F));
check("problem digest changes with budget / weight / cost / radius / required",
  new Set([PL.problemDigest(v, F), PL.problemDigest({ ...v, budget: v.budget + 1 }, F), PL.problemDigest({ ...v, coverage_radius_m: 401 }, F),
    PL.problemDigest({ ...v, required_ids: ["K01"] }, F),
    PL.problemDigest({ ...v, control_points: v.control_points.map((p, k) => (k ? p : { ...p, weight: p.weight + 1 })) }, F),
    PL.problemDigest({ ...v, candidates: v.candidates.map((c, k) => (k ? c : { ...c, cost: c.cost + 1 })) }, F)]).size === 6);

// 4. exact optimizer = oracle (status, reasons, winners, Pareto, counts) and sensitivity
const pick = (o) => o && { ids: o.ids, cost: o.cost, unknown_count: o.unknown_count, weighted_sum_mm: o.weighted_sum_mm, max_mm: o.max_mm, covered_weight: o.covered_weight };
for (const c of exp.cases) {
  const ctx = caseCtx(c), sc = caseScenario(c, ctx), e = c.expected.optimize;
  const t0 = Date.now(), r = PL.optimizePlans(ctx, sc, { F }), ms = Date.now() - t0;
  const ok = r.status === e.status && J(r.reasons.map((x) => x.code)) === J(e.reasons) && r.feasible_count === e.feasible_count && r.evaluated === e.evaluated
    && J(r.objectives && Object.fromEntries(Object.entries(r.objectives).map(([k, v]) => [k, pick(v)]))) === J(e.objectives)
    && J(r.pareto) === J(e.pareto);
  check(`optimizePlans = oracle: ${c.name} (${r.evaluated} subsets, ${ms} ms)`, ok, J({ js: { s: r.status, o: r.objectives, p: r.pareto.length }, py: { s: e.status, o: e.objectives, p: e.pareto.length } }));
  const rr = PL.optimizePlans(ctx, reversed(sc), { F });
  check(`optimizer independent of input order: ${c.name}`, J(rr.objectives) === J(r.objectives) && J(rr.pareto) === J(r.pareto) && rr.problem_digest === r.problem_digest);
  const sens = PL.sensitivity(ctx, sc, { F });
  check(`sensitivity budgets = oracle: ${c.name}`, J(sens.map((x) => [x.budget, x.status, x.feasible_count, x.objectives && x.objectives.mean.ids])) ===
    J(c.expected.sensitivity.map((x) => [x.budget, x.status, x.feasible_count, x.objectives && x.objectives.mean.ids])));
}
// winners may coincide; the result never claims three different plans
const same = exp.cases.find((c) => c.name === "dominated_plans"), sr = PL.optimizePlans(caseCtx(same), caseScenario(same, caseCtx(same)), { F });
check("identical winners allowed (mean = minimax = coverage)", J(sr.objectives.mean.ids) === J(sr.objectives.coverage.ids));
check("Pareto excludes dominated plans (Dear alone not on the front)", !sr.pareto.some((p) => J(p.ids) === J(["Dear"])));
const cvm = exp.cases.find((c) => c.name === "coverage_vs_mean"), cr = PL.optimizePlans(caseCtx(cvm), caseScenario(cvm, caseCtx(cvm)), { F });
check("different objectives can pick different plans (coverage ≠ mean)", J(cr.objectives.coverage.ids) !== J(cr.objectives.mean.ids));
// chunked run + cancel + progress
const big = exp.cases.find((c) => c.name === "shymkent_school_16x25"), bctx = caseCtx(big), bsc = caseScenario(big, bctx);
const s1 = PL.createSearch(bctx, bsc, { F, request_id: 7 });
let steps = 0; while (!s1.step(4096)) steps++;
check("chunked search (4096 per step) = one-shot result", J(s1.result()) === J(PL.optimizePlans(bctx, bsc, { F, request_id: 7 })) && steps === 15 && s1.examined === 65536);
const s2 = PL.createSearch(bctx, bsc, { F }); s2.step(1000); s2.cancel();
const cr2 = s2.result();
check("cancelled search: status cancelled, no objectives, progress kept", cr2.status === "cancelled" && cr2.objectives === null && cr2.evaluated === 1000 && cr2.total_subsets === 65536);
const s3 = PL.createSearch(bctx, bsc, { F }); s3.step(10);
check("unfinished search is never 'optimal'", s3.result().status === "incomplete" && s3.result().objectives === null);
check("problem_digest in the result binds it to the input", PL.optimizePlans(bctx, bsc, { F }).problem_digest === PL.problemDigest(bsc, F)
  && PL.optimizePlans(bctx, { ...bsc, budget: bsc.budget - 1 }, { F }).problem_digest !== PL.problemDigest(bsc, F));
const t0 = Date.now(); PL.optimizePlans(bctx, bsc, { F }); const tBig = Date.now() - t0;
check(`16×25 full search under 2 s in Node (${tBig} ms)`, tBig < 2000);

// 5. files: export / import city-plan-v2 (strict, atomic, derived_results verified)
const ctxFor = (city) => PL.makeContext(D, city, F);
const txt = PL.exportPlanScenario(bctx, bsc, F), ej = JSON.parse(txt);
const imp = PL.importPlanScenario(txt, ctxFor, F);
check("export -> import round trip (scenario and evaluation equal)", J(imp.scenario) === J(bsc) && J(imp.evaluation.metrics) === J(PL.evaluatePlan(bctx, bsc, bsc.selected_ids).metrics));
check("export contains labelled derived block, digests, no local paths", ej.derived_results.note.includes("пересчитываются") && ej.derived_results.problem_digest === PL.problemDigest(bsc, F) && !/\/home\/|\/tmp\/|[A-Z]:\\/.test(txt));
const irej = (name, t, want) => check(`import rejects ${name} (${want})`, code(() => PL.importPlanScenario(t, ctxFor, F)) === want);
const forged = JSON.parse(txt); forged.derived_results.manual.metrics.weighted_sum_mm = 1;
irej("forged derived_results (metric changed)", J(forged), "forged_derived");
const forged2 = JSON.parse(txt); forged2.derived_results.manual.rows[0].after_mm = 0;
irej("forged derived_results (row changed)", J(forged2), "forged_derived");
const forged3 = JSON.parse(txt); forged3.derived_results.extra = 1;
irej("derived_results with an extra field", J(forged3), "forged_derived");
const noDerived = JSON.parse(txt); delete noDerived.derived_results;
check("import without derived_results accepted (recomputed)", code(() => PL.importPlanScenario(J(noDerived), ctxFor, F)) === "accepted");
irej("v1 scenario (separate mode, no silent migration)", X.exportScenario({ schema_version: X.SCHEMA, city_id: "shymkent", source_snapshot: X.sourceSnapshot(D, "shymkent", F), category: "school",
  control_points: [{ id: "P1", lon: bsc.control_points[0].lon, lat: bsc.control_points[0].lat }], proposed_object: null }, D, F), "wrong_version");
irej("unknown version", txt.replace('"city-plan-v2"', '"city-plan-v9"'), "bad_version");
irej("unknown source snapshot", txt.replace(bsc.source_snapshot, "sha256:" + "a".repeat(64)), "foreign_snapshot");
irej("Shymkent file claiming Astana", txt.replace('"city_id": "shymkent"', '"city_id": "astana"'), "foreign_snapshot");
irej("unknown city", txt.replace('"city_id": "shymkent"', '"city_id": "almaty"'), "bad_city");
irej("NaN", txt.replace(/"budget": \d+/, '"budget": NaN'), "bad_json");
irej("Infinity", txt.replace(/"budget": \d+/, '"budget": Infinity'), "bad_json");
irej("1e999", txt.replace(/"budget": \d+/, '"budget": 1e999'), "bad_json");
irej("duplicate key", txt.replace('"max_selected"', '"budget": 1, "max_selected"'), "bad_json");
irej("oversize > 256 KiB", " ".repeat(262145) + txt, "too_large");
irej("unknown top-level field", txt.replace('"budget"', '"href": "https://x", "budget"'), "unknown_field");
check("Astana file imported with the Astana context", (() => { const at = PL.exportPlanScenario(ast, caseScenario(exp.cases.find((c) => c.name === "astana_school_16x25"), ast), F);
  return PL.importPlanScenario(at, ctxFor, F).ctx.city_id === "astana"; })());

// 6. explanation (template, digest, stale) and report
const bres = PL.optimizePlans(bctx, bsc, { F }), bsens = PL.sensitivity(bctx, bsc, { F }), bman = PL.evaluatePlan(bctx, bsc, bsc.selected_ids);
const dg = PL.explanationDigest(bsc, bman, bres, bsens, F);
const exT = PL.explainPlans(bsc, bman, bres, bsens, dg, F).text;
check("explanation: template, units, trade-off, capacity disclaimer, conditional units", exT.startsWith("Шаблонное объяснение") && exT.includes("усл. ед.") && exT.includes("жертвует") && exT.includes("Нельзя сделать вывод о вместимости") && !/мин\b|минут/.test(exT), exT.slice(0, 300));
check("explanation digest changes with budget / selection / result", new Set([dg, PL.explanationDigest({ ...bsc, budget: 1 }, bman, bres, bsens, F), PL.explanationDigest({ ...bsc, selected_ids: [] }, bman, bres, bsens, F),
  PL.explanationDigest(bsc, bman, null, bsens, F)]).size === 4);
check("stale explanation rejected", code(() => PL.explainPlans({ ...bsc, budget: bsc.budget - 1 }, bman, bres, bsens, dg, F)) === "stale_explanation");
const sres = PL.optimizePlans(caseCtx(same), caseScenario(same, caseCtx(same)), { F }), ssc = caseScenario(same, caseCtx(same)), sman = PL.evaluatePlan(caseCtx(same), ssc, ssc.selected_ids);
const sT = PL.explainPlans(ssc, sman, sres, null, PL.explanationDigest(ssc, sman, sres, null, F), F).text;
check("identical winners explained as one plan, not three decisions", sT.includes("нет трёх разных решений"));
const ires = PL.optimizePlans(rctx, rsc, { F }), iT = PL.explainPlans(rsc, null, ires, null, PL.explanationDigest(rsc, null, ires, null, F), F).text;
check("infeasible explained with reason; constraints not dropped", iT.includes("Допустимых планов нет") && iT.includes("не снимались"));
const nb = exp.cases.find((c) => c.name === "no_baseline"), nbsc = caseScenario(nb, caseCtx(nb)), nbm = PL.evaluatePlan(caseCtx(nb), nbsc, []);
check("unknown distance explained as unknown, not zero", PL.explainPlans(nbsc, nbm, null, null, PL.explanationDigest(nbsc, nbm, null, null, F), F).text.includes("неизвестно, а не равно нулю"));
const evil = "<script>alert(1)</script>\"'&";
const html = PL.reportHtml({ scenario: bsc, city_label: evil, release: "2026-09-23.1", problem_digest: "p", scenario_digest: "s", generated: "t", manual: bman, result: bres, sens: bsens,
  explanation: exT + evil, names: Object.fromEntries(sh.places.map((p) => [p.id, evil])), attribution: evil, demo: true });
check("HTML report: no script tag, strings escaped, CSP default-src none, no external URL",
  !/<script/i.test(html) && html.includes("&lt;script&gt;") && html.includes("default-src 'none'") && !/https?:\/\//.test(html) && html.includes("синтетический"));
check("HTML report contains plan tables and limitations", html.includes("Точный перебор") && html.includes("Парето") && html.includes("Изменение бюджета") && html.includes("не тенге"));

console.log(fails ? `${fails} FAILED` : "all plan checks passed");
process.exit(fails ? 1 : 0);
