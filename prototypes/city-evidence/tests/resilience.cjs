// web/resilience.js (city-resilience-v1) vs the independent Python oracle (tests/expected_resilience.json) + contract rules.
// Headless, no DOM.  Usage: node tests/resilience.cjs
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = path.join(__dirname, "..", "web");
const c0 = {}; vm.createContext(c0); c0.window = c0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), c0, { filename: f });
const F = require(path.join(W, "facts.js")), X = require(path.join(W, "whatif.js")), PL = require(path.join(W, "plan.js")), RS = require(path.join(W, "resilience.js"));
const D = c0.CITY_EVIDENCE;
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(detail).slice(0, 400) : "")); };
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || e.message; } };
const J = JSON.stringify;

const exp = JSON.parse(fs.readFileSync(path.join(__dirname, "expected_resilience.json"), "utf8"));
function ctxOf(c) {
  if (c.kind === "synthetic_hand") return PL.makeContext({ cities: { "synthetic-eq": { bbox: c.bbox, release: "synthetic", files: {}, places: c.records } } }, "synthetic-eq", F);
  return PL.makeContext(D, c.city, F);
}
const envOf = (c, ctx) => ({ schema_version: RS.SCHEMA, plan: { ...c.plan, city_id: ctx.city_id, source_snapshot: ctx.source_snapshot }, cases: c.cases });
const M = ["unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "weighted_mean_mm"];
const close = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) < 1e-6);
function samePlan(js, py) {
  if (!js || !py) return js === py;
  if (J(js.selected_ids) !== J(py.ids) || js.cost !== py.cost || J(js.worst_case_ids) !== J(py.worst_case_ids) || J(js.worst_vector) !== J(py.worst)) return false;
  return js.per_case.every((r) => M.every((k) => close(r.metrics[k], py.per_case[r.case_id][k])));
}

// 1. math = oracle (manual, nominal, robust: per-case metrics, worst vector and ids, counts, price)
for (const c of exp.cases) {
  const ctx = ctxOf(c), env = envOf(c, ctx), e = c.expected;
  const man = RS.evaluateResilience(ctx, env, c.plan.selected_ids);
  check(`manual plan per case = oracle: ${c.name}`, samePlan(man, e.manual), J({ js: man.worst_vector, py: e.manual.worst }));
  const r = RS.optimizeResilience(ctx, env, { F }), o = e.optimize;
  let ok = r.status === o.status && r.feasible_count === o.feasible_count;
  if (o.status === "optimal") ok = ok && r.evaluated === o.evaluated && samePlan(r.nominal, o.nominal) && samePlan(r.robust, o.robust) && r.same_plan === o.same_plan && close(r.price_of_robustness_m, o.price_of_robustness_m);
  else ok = ok && J(r.reasons.map((x) => x.code)) === J(o.reasons);
  check(`optimizeResilience = oracle: ${c.name}`, ok, J({ js: [r.status, r.nominal && r.nominal.selected_ids, r.robust && r.robust.selected_ids, r.price_of_robustness_m], py: [o.status, o.nominal && o.nominal.ids, o.robust && o.robust.ids, o.price_of_robustness_m] }));
  // order of cases / ids / points / candidates does not matter
  const rev = { ...env, cases: env.cases.slice().reverse().map((x) => ({ ...x, disabled_source_ids: x.disabled_source_ids.slice().reverse() })),
    plan: { ...env.plan, control_points: env.plan.control_points.slice().reverse(), candidates: env.plan.candidates.slice().reverse() } };
  const rr = RS.optimizeResilience(ctx, rev, { F });
  check(`input order independent: ${c.name}`, J(rr.robust && rr.robust.selected_ids) === J(r.robust && r.robust.selected_ids) && rr.resilience_problem_digest === r.resilience_problem_digest
    && J(rr.robust && rr.robust.worst_vector) === J(r.robust && r.robust.worst_vector));
  // nominal = v2 mean optimum on the base case
  if (r.status === "optimal") check(`nominal = plan.js v2 mean optimum: ${c.name}`, J(r.nominal.selected_ids) === J(PL.optimizePlans(ctx, env.plan, { F }).objectives.mean.ids));
}

// 2. semantics
const rd = exp.cases.find((c) => c.name === "robust_differs_from_nominal"), rctx = ctxOf(rd), renv = envOf(rd, rctx), rres = RS.optimizeResilience(rctx, renv, { F });
check("robust differs from nominal; price of robustness > 0 and equals base mean difference",
  !rres.same_plan && rres.price_of_robustness_m > 0 && Math.abs(rres.price_of_robustness_m - (rres.robust.base_weighted_mean_mm - rres.nominal.base_weighted_mean_mm) / 1000) < 1e-9);
check("robust worst vector ≤ nominal worst vector (lexicographic)", (() => { const a = rres.robust.worst_vector, b = rres.nominal.worst_vector;
  const k = (v) => [v.unknown_count, v.weighted_sum_mm, v.max_mm === null ? Infinity : v.max_mm]; const x = k(a), y = k(b); for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] < y[i]; return true; })());
const idc = exp.cases.find((c) => c.name === "identical_plans"), ires = RS.optimizeResilience(ctxOf(idc), envOf(idc, ctxOf(idc)), { F });
check("identical plans: same_plan, price exactly 0 (no invented advantage)", ires.same_plan && ires.price_of_robustness_m === 0);
const unk = exp.cases.find((c) => c.name === "all_sources_off_unknown"), uctx = ctxOf(unk), uev = RS.evaluateResilience(uctx, envOf(unk, uctx), []);
const none = uev.per_case.find((x) => x.case_id === "none");
check("all sources off, no candidate: distances null (not 0), worst case named", none.metrics.unknown_count === 2 && none.metrics.max_mm === null && none.metrics.weighted_mean_mm === null
  && none.rows.every((r) => r.before_mm === null && r.after_mm === null && r.delta_mm === null) && J(uev.worst_case_ids) === J(["none"]));
const ures = RS.optimizeResilience(uctx, envOf(unk, uctx), { F });
check("price null with reason when a base mean is unknown OR equal plans → 0", ures.status === "optimal" && (ures.price_of_robustness_m === 0 || ures.price_reason));
const dup = exp.cases.find((c) => c.name === "duplicate_cases"), dctx = ctxOf(dup), denv = envOf(dup, dctx), dres = RS.optimizeResilience(dctx, denv, { F });
const single = RS.optimizeResilience(dctx, { ...denv, cases: [denv.cases[0]] }, { F });
check("duplicate cases: shown as a group, result equals the single-case result", J(dres.duplicate_case_groups) === J([["x1", "x2"]]) && J(dres.robust.selected_ids) === J(single.robust.selected_ids)
  && J(dres.robust.worst_vector) === J(single.robust.worst_vector) && dres.robust.worst_case_ids.includes("x1") && dres.robust.worst_case_ids.includes("x2"));
const req = exp.cases.find((c) => c.name === "required_over_budget"), qres = RS.optimizeResilience(ctxOf(req), envOf(req, ctxOf(req)), { F });
check("infeasible required: status infeasible, reason, price null, constraints not dropped", qres.status === "infeasible" && qres.price_of_robustness_m === null && qres.evaluated === 0);
const man2 = RS.evaluateResilience(ctxOf(req), envOf(req, ctxOf(req)), ["C2"]);
check("manual plan violating required is flagged infeasible", !man2.feasibility.feasible && man2.feasibility.reasons.some((x) => x.code === "missing_required"));

// 3. source data immutable; per-case filtering on copies
const sh = PL.makeContext(D, "shymkent", F), nBefore = sh.places.length, snap = sh.source_snapshot;
const real = exp.cases.find((c) => c.name === "shymkent_school_8x12x5"), senv = envOf(real, sh);
RS.optimizeResilience(sh, senv, { F });
check("context not mutated by cases (records, snapshot, frozen)", sh.places.length === nBefore && sh.source_snapshot === snap && Object.isFrozen(sh.places));
const cc = RS.caseContext(sh, senv.cases[0].disabled_source_ids);
check("case context is a filtered copy", cc !== sh && cc.places.length === nBefore - senv.cases[0].disabled_source_ids.length && sh.places.length === nBefore);
check("source_snapshot of the result is the plan's own (exclusions have a separate digest)", (() => { const r = RS.optimizeResilience(sh, senv, { F }); return r.source_snapshot === snap && /^sha256:/.test(r.exclusions_digest); })());

// 4. validation (before any precomputation)
const base = () => JSON.parse(J(senv));
const rej = (name, mut, want) => { const o = base(); mut(o); check(`rejects ${name} (${want})`, code(() => RS.validateResilience(o, sh)) === want); };
rej("13 candidates (limit 12 for resilience)", (o) => { o.plan.candidates = Array.from({ length: 13 }, (_, k) => ({ ...o.plan.candidates[k % 8], id: "Q" + k })); o.plan.selected_ids = []; }, "too_many_candidates");
check("13 candidates refused fast, before precomputation", (() => { const o = base(); o.plan.candidates = Array.from({ length: 13 }, (_, k) => ({ ...o.plan.candidates[k % 8], id: "Q" + k })); o.plan.selected_ids = [];
  const t = Date.now(); const c = code(() => RS.optimizeResilience(sh, o, { F })); return c === "too_many_candidates" && Date.now() - t < 50; })());
check("v2 still accepts 16 candidates (unchanged)", code(() => PL.validatePlanScenario({ ...senv.plan, candidates: Array.from({ length: 16 }, (_, k) => ({ ...senv.plan.candidates[k % 8], id: "Q" + k })), selected_ids: [] }, sh)) === "accepted");
rej("0 cases", (o) => { o.cases = []; }, "bad_cases");
rej("8 user cases", (o) => { o.cases = Array.from({ length: 8 }, (_, k) => ({ ...o.cases[0], id: "c" + k })); }, "bad_cases");
check("7 user cases accepted (+ base = 8)", code(() => { const o = base(); o.cases = Array.from({ length: 7 }, (_, k) => ({ ...o.cases[0], id: "c" + k })); RS.validateResilience(o, sh); }) === "accepted");
rej("id base (reserved)", (o) => { o.cases[0].id = "base"; }, "reserved_id");
rej("duplicate case id", (o) => { o.cases[1].id = o.cases[0].id; }, "duplicate_id");
rej("case id with markup", (o) => { o.cases[0].id = "<b>x"; }, "bad_id");
rej("empty label", (o) => { o.cases[0].label = "  "; }, "bad_label");
rej("label 121 code points", (o) => { o.cases[0].label = "ә".repeat(121); }, "bad_label");
rej("label with control char", (o) => { o.cases[0].label = "a\u0007b"; }, "bad_label");
check("Kazakh label of 120 code points accepted", code(() => { const o = base(); o.cases[0].label = "ә".repeat(120); RS.validateResilience(o, sh); }) === "accepted");
rej("no exclusions", (o) => { o.cases[0].disabled_source_ids = []; }, "bad_exclusions");
rej("candidate ID instead of source ID", (o) => { o.cases[0].disabled_source_ids = [o.plan.candidates[0].id]; }, "candidate_not_source");
rej("unknown source ID", (o) => { o.cases[0].disabled_source_ids = ["nope"]; }, "unknown_source");
rej("source of another category", (o) => { o.cases[0].disabled_source_ids = [sh.places.find((p) => p.group === "outpatient_clinic").id]; }, "unknown_source");
rej("duplicate exclusion", (o) => { o.cases[0].disabled_source_ids = [o.cases[0].disabled_source_ids[0], o.cases[0].disabled_source_ids[0]]; }, "duplicate_id");
rej("more exclusions than records", (o) => { o.cases[0].disabled_source_ids = [...o.cases[2].disabled_source_ids, "x"]; }, "bad_exclusions");
rej("extra field in case", (o) => { o.cases[0].risk = 0.5; }, "bad_shape");
rej("derived results in envelope", (o) => { o.results = {}; }, "unknown_field");
rej("derived_results inside plan", (o) => { o.plan.derived_results = {}; }, "derived_not_allowed");
rej("missing cases", (o) => { delete o.cases; }, "missing_field");
rej("v2 file", (o) => { o.schema_version = PL.SCHEMA; }, "wrong_version");
rej("unknown version", (o) => { o.schema_version = "city-resilience-v2"; }, "bad_version");
rej("foreign snapshot in plan", (o) => { o.plan.source_snapshot = "sha256:" + "0".repeat(64); }, "foreign_snapshot");
rej("plan with weight 0", (o) => { o.plan.control_points[0].weight = 0; }, "bad_weight");
check("public evaluate / search validate unchecked input", code(() => RS.evaluateResilience(sh, { ...base(), cases: [] }, [])) === "bad_cases" && code(() => RS.createResilienceSearch(sh, { ...base(), cases: [] }, { F })) === "bad_cases");
const mutEnv = base(), ms = RS.createResilienceSearch(sh, mutEnv, { F });
mutEnv.cases.push(...Array.from({ length: 10 }, (_, k) => ({ ...mutEnv.cases[0], id: "m" + k }))); mutEnv.plan.budget = -1;
while (!ms.step(1 << 20));
check("mutating the passed envelope after createResilienceSearch changes nothing", ms.result().cases.length === 5 && ms.result().status === "optimal");

// 5. digests
const v = RS.validateResilience(base(), sh);
check("problem digest independent of case order / exclusion order", RS.resilienceProblemDigest(v, F) === RS.resilienceProblemDigest({ ...v, cases: v.cases.slice().reverse().map((c) => ({ ...c, disabled_source_ids: c.disabled_source_ids.slice().reverse() })) }, F));
check("problem digest changes with label / exclusion / plan budget; selection only in scenario digest", new Set([RS.resilienceProblemDigest(v, F),
  RS.resilienceProblemDigest({ ...v, cases: v.cases.map((c, k) => (k ? c : { ...c, label: c.label + "!" })) }, F),
  RS.resilienceProblemDigest({ ...v, cases: v.cases.map((c, k) => (k ? c : { ...c, disabled_source_ids: c.disabled_source_ids.slice(1) })) }, F),
  RS.resilienceProblemDigest({ ...v, plan: { ...v.plan, budget: v.plan.budget + 1 } }, F)]).size === 4
  && RS.resilienceProblemDigest({ ...v, plan: { ...v.plan, selected_ids: [] } }, F) === RS.resilienceProblemDigest(v, F)
  && RS.resilienceScenarioDigest({ ...v, plan: { ...v.plan, selected_ids: [] } }, F) !== RS.resilienceScenarioDigest(v, F));
check("resilience digest differs from the v2 problem digest", RS.resilienceProblemDigest(v, F) !== PL.problemDigest(v.plan, F));

// 6. chunks, cancel, incomplete
const s1 = RS.createResilienceSearch(sh, senv, { F, request_id: 3 }); let st = 0; while (!s1.step(64)) st++;
check("chunked (64 per step) = one-shot; request_id kept", J(s1.result()) === J(RS.optimizeResilience(sh, senv, { F, request_id: 3 })) && st > 1);
const s2 = RS.createResilienceSearch(sh, senv, { F }); s2.step(10); s2.cancel();
check("cancelled: status cancelled, no plans, price null", s2.result().status === "cancelled" && s2.result().robust === null && s2.result().price_of_robustness_m === null);
const s3 = RS.createResilienceSearch(sh, senv, { F }); s3.step(5);
check("unfinished search never 'optimal'", s3.result().status === "incomplete" && s3.result().nominal === null);

// 7. files: input-only envelope, strict import
const ctxFor = (city) => PL.makeContext(D, city, F);
const txt = RS.exportResilience(sh, senv), ej = JSON.parse(txt);
check("export = input only (no derived fields), schema city-resilience-v1", J(Object.keys(ej)) === J(["schema_version", "plan", "cases"]) && !("derived_results" in ej.plan) && !/"(results|metrics|per_case)"/.test(txt));
const imp = RS.importResilience(txt, ctxFor);
check("export → import round trip (same envelope, recomputed result identical)", J(imp.envelope) === J(RS.validateResilience(senv, sh)) && J(RS.optimizeResilience(imp.ctx, imp.envelope, { F })) === J(RS.optimizeResilience(sh, senv, { F })));
const irej = (name, t, want) => check(`import rejects ${name} (${want})`, code(() => RS.importResilience(t, ctxFor)) === want);
irej("NaN", txt.replace(/"budget": \d+/, '"budget": NaN'), "bad_json");
irej("1e999", txt.replace(/"budget": \d+/, '"budget": 1e999'), "bad_json");
irej("duplicate key", txt.replace('"cases"', '"cases": [], "cases"'), "bad_json");
irej("oversize", " ".repeat(262145) + txt, "too_large");
irej("v2 plan file", PL.exportPlanScenario(sh, senv.plan.selected_ids ? PL.validatePlanScenario(senv.plan, sh) : null, F), "wrong_version");
irej("v1 file", X.exportScenario({ schema_version: X.SCHEMA, city_id: "shymkent", source_snapshot: X.sourceSnapshot(D, "shymkent", F), category: "school",
  control_points: [{ id: "P1", lon: senv.plan.control_points[0].lon, lat: senv.plan.control_points[0].lat }], proposed_object: null }, D, F), "wrong_version");
irej("unknown city", txt.replace('"city_id": "shymkent"', '"city_id": "almaty"'), "bad_city");
irej("Shymkent plan claiming Astana", txt.replace('"city_id": "shymkent"', '"city_id": "astana"'), "foreign_snapshot");
irej("forged result field", txt.replace('"cases"', '"robust": {"selected_ids": []}, "cases"'), "unknown_field");
check("Astana envelope imported in the Astana context", (() => { const ac = PL.makeContext(D, "astana", F), ar = exp.cases.find((c) => c.name === "astana_school_8x12x5");
  return RS.importResilience(RS.exportResilience(ac, envOf(ar, ac)), ctxFor).ctx.city_id === "astana"; })());

// 8. explanation (template)
const ex = RS.explainResilience(v, RS.evaluateResilience(sh, senv, senv.plan.selected_ids), RS.optimizeResilience(sh, senv, { F }));
check("explanation: template, 'не подтверждение закрытия', no probability/risk claims", ex.startsWith("Шаблонное объяснение") && ex.includes("не подтверждение закрытия") && !/вероятност[ьи] \d|риск \d|%/.test(ex));
check("explanation names duplicate cases", ex.includes("first3 = first3dup") || ex.includes("first3dup = first3"));

console.log(fails ? `${fails} FAILED` : "all resilience checks passed");
process.exit(fails ? 1 : 0);
