// K12 round 9, stage 1: public-API boundary check for city-plan-v2 (and city-resilience-v1 when BUILD publishes it).
// CORE_SPEC r9: "Непроверенные объекты при прямом вызове публичных evaluate/optimize/создания поиска валидировать ...
// изменение переданного объекта не должно обходить ограничения". The normal UI and file import validate first; this
// file calls the PUBLIC functions directly, the way another module or a later API extension would.
// Every probe runs in its own child process with a watchdog, so a heavy enumeration or a freeze is reported, not waited
// for. Sizes start at 17/20 candidates (v2) and 13 (resilience); 2^30 is never attempted.
//   node api_guard.cjs --app-root <copy of prototypes/city-evidence> [--timeout-ms 10000] [--only S17_create,...] [--out r.json]
// Verdicts: PASS (typed refusal before heavy work, or correct control result), FAIL (accepted / untyped crash / timeout /
// wrong control result), NOT_RUN (module or API missing in this build). Inputs are SYNTHETIC.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const { spawnSync } = require("child_process");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const HERE = __dirname;
const APP = path.resolve(opt("--app-root", ""));
const TIMEOUT = Number(opt("--timeout-ms", "10000"));
const FAST_MS = Number(opt("--fast-ms", "200"));        // a refusal "before heavy work" must come this fast
const V2_ADAPTER = path.resolve(opt("--v2-adapter", path.join(HERE, "adapters", "plan_v2_api_adapter.cjs")));
const RS_ADAPTER = path.resolve(opt("--rs-adapter", path.join(HERE, "adapters", "resilience_api_adapter.cjs")));
const OUT = opt("--out");
if (!fs.existsSync(path.join(APP, "web", "data.js"))) { console.error("usage: node api_guard.cjs --app-root <dir>"); process.exit(2); }

function load(adapterPath) {
  const W = path.join(APP, "web");
  const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
  for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx, { filename: f });
  return require(adapterPath)({ appRoot: APP, D: ctx.CITY_EVIDENCE, EV: ctx.CITY_OBS, ctx, requireWeb: (n) => require(path.join(W, n)) });
}
const clone = (x) => JSON.parse(JSON.stringify(x));

// ---------------------------------------------------------------- synthetic inputs inside the slice bbox
function plan(A, nc, { city = "shymkent", category = "school", np = 6 } = {}) {
  const c = A.ctx(city), bb = c.bbox;
  const at = (k, m, row) => [+(bb[0] + 0.001 + (k % 7) * (bb[2] - bb[0] - 0.002) / 6).toFixed(6),
                             +(bb[1] + 0.001 + ((Math.floor(k / 7) + row) % 4) * (bb[3] - bb[1] - 0.002) / 3).toFixed(6)];
  return { schema_version: "city-plan-v2", city_id: city, source_snapshot: A.snapshot(city), category,
    control_points: Array.from({ length: np }, (_, k) => { const [lon, lat] = at(k, np, 0); return { id: `p${k}`, lon, lat, weight: 1 + (k % 5) }; }),
    candidates: Array.from({ length: nc }, (_, k) => { const [lon, lat] = at(k + 3, nc, 1); return { id: `c${k}`, lon, lat, category, kind: "hypothetical", cost: 1000 + 37 * k }; }),
    budget: 1000000, max_selected: 5, coverage_radius_m: 500, required_ids: [], excluded_ids: [], selected_ids: [] };
}
function envelope(A, nc, ncases = 2, opts = {}) {
  const p = plan(A, nc, opts);
  const src = A.places(p.city_id, p.category);
  return { schema_version: "city-resilience-v1", plan: p,
    cases: Array.from({ length: ncases }, (_, k) => ({ id: `case${k + 1}`, label: `Случай ${k + 1}`, disabled_source_ids: [src[k % src.length]] })) };
}

// ---------------------------------------------------------------- probes
// expect "refuse": the call must throw an error that carries a string code, within FAST_MS.
// expect "check": custom function returns {ok, detail}.
const summarize = (r) => {
  if (r === undefined || r === null) return r;
  if (typeof r.step === "function") return { search_object: true, total: r.total, examined: r.examined };
  if (r.status !== undefined) return { status: r.status, evaluated: r.evaluated, mean: r.objectives && r.objectives.mean ? (r.objectives.mean.ids || r.objectives.mean.selected_ids) : null };
  if (Array.isArray(r)) return r.slice(0, 3).map((x) => ({ budget: x.budget, status: x.status }));
  if (r.metrics) return { metrics: r.metrics };
  return JSON.parse(JSON.stringify(r, (k, v) => (typeof v === "number" && !Number.isFinite(v) ? String(v) : v)));
};
const V2 = {
  S17_create:    { what: "createSearch, 17 кандидатов", refuse: (A) => { const p = plan(A, 17); return A.createSearch(A.ctx("shymkent"), p); } },
  S20_create:    { what: "createSearch, 20 кандидатов", refuse: (A) => A.createSearch(A.ctx("shymkent"), plan(A, 20)) },
  S17_optimize:  { what: "optimizePlans, 17 кандидатов", refuse: (A) => A.optimize(A.ctx("shymkent"), plan(A, 17)) },
  S20_optimize:  { what: "optimizePlans, 20 кандидатов", refuse: (A) => A.optimize(A.ctx("shymkent"), plan(A, 20)) },
  S17_sensitivity: { what: "sensitivity, 17 кандидатов", refuse: (A) => A.sensitivity(A.ctx("shymkent"), plan(A, 17)) },
  S17_evaluate:  { what: "evaluatePlan, 17 кандидатов", refuse: (A) => A.evaluate(A.ctx("shymkent"), plan(A, 17), ["c0"]) },
  M_after_validation: { what: "объект прошёл validate, затем дополнен до 17 кандидатов → optimizePlans",
    refuse: (A) => { const c = A.ctx("shymkent"); const v = A.validate(plan(A, 3), c); v.candidates.push(...plan(A, 17).candidates.slice(3)); return A.optimize(c, v); } },
  M_after_validation_eval: { what: "объект прошёл validate, затем вес стал строкой \"5\" → evaluatePlan",
    refuse: (A) => { const c = A.ctx("shymkent"); const v = A.validate(plan(A, 3), c); v.control_points[0].weight = "5"; return A.evaluate(c, v, ["c0"]); } },
  T_weight_string: { what: "вес \"5\" (строка) → evaluatePlan",
    refuse: (A) => { const p = plan(A, 3); p.control_points[0].weight = "5"; return A.evaluate(A.ctx("shymkent"), p, ["c1"]); } },
  T_cost_string: { what: "стоимость \"100\" (строка) → optimizePlans",
    refuse: (A) => { const p = plan(A, 3); p.candidates[0].cost = "100"; return A.optimize(A.ctx("shymkent"), p); } },
  T_nan_coord:   { what: "lon = NaN → evaluatePlan", refuse: (A) => { const p = plan(A, 3); p.control_points[0].lon = NaN; return A.evaluate(A.ctx("shymkent"), p, ["c1"]); } },
  T_negative_weight: { what: "вес −50 → optimizePlans", refuse: (A) => { const p = plan(A, 3); p.control_points[0].weight = -50; return A.optimize(A.ctx("shymkent"), p); } },
  T_dup_candidate: { what: "повтор ID кандидата → optimizePlans", refuse: (A) => { const p = plan(A, 3); p.candidates.push({ ...p.candidates[0] }); return A.optimize(A.ctx("shymkent"), p); } },
  T_max_selected_99: { what: "max_selected 99 → optimizePlans", refuse: (A) => { const p = plan(A, 3); p.max_selected = 99; return A.optimize(A.ctx("shymkent"), p); } },
  T_city_mismatch: { what: "city_id astana при контексте Шымкента → evaluatePlan", refuse: (A) => { const p = plan(A, 3); p.city_id = "astana"; return A.evaluate(A.ctx("shymkent"), p, ["c1"]); } },
  T_foreign_snapshot: { what: "чужой source_snapshot → optimizePlans", refuse: (A) => { const p = plan(A, 3); p.source_snapshot = "sha256:" + "0".repeat(64); return A.optimize(A.ctx("shymkent"), p); } },
  T_category_unknown: { what: "категория hospital → evaluatePlan", refuse: (A) => { const p = plan(A, 3); p.category = "hospital"; p.candidates.forEach((x) => { x.category = "hospital"; }); return A.evaluate(A.ctx("shymkent"), p, ["c1"]); } },
  T_outside_bbox: { what: "кандидат вне bbox среза → optimizePlans", refuse: (A) => { const p = plan(A, 3); p.candidates[0].lat += 1; return A.optimize(A.ctx("shymkent"), p); } },
  T_unknown_required: { what: "required_ids с неизвестным ID → optimizePlans (ожидается типизированный отказ, не TypeError)",
    refuse: (A) => { const p = plan(A, 3); p.required_ids = ["nope"]; return A.optimize(A.ctx("shymkent"), p); } },
  C_valid16: { what: "контроль: валидные 16 кандидатов через прямой API = optimal, 65 536 наборов, как после validate",
    check: (A) => { const c = A.ctx("shymkent"), p = plan(A, 16); const a = A.optimize(c, p), b = A.optimize(c, A.validate(clone(p), c));
      const ok = a.status === "optimal" && a.evaluated === 65536 && JSON.stringify(a.objectives) === JSON.stringify(b.objectives);
      return { ok, detail: { status: a.status, evaluated: a.evaluated } }; } },
  C_clean_copy: { what: "контроль: validate возвращает независимую копию (изменение входа после validate её не меняет)",
    check: (A) => { const c = A.ctx("shymkent"), inp = plan(A, 3); const v = A.validate(inp, c), before = JSON.stringify(v);
      inp.candidates.push({ ...inp.candidates[0], id: "zz" }); inp.budget = -1; inp.control_points[0].weight = "5";
      return { ok: JSON.stringify(v) === before, detail: { candidates: v.candidates.length, budget: v.budget } }; } },
  C_mid_search_mutation: { what: "изменение переданного объекта посреди пошагового поиска не меняет ответ (бюджет 0, max_selected 0)",
    check: (A) => { const c = A.ctx("shymkent"), p = plan(A, 10); p.budget = 5000;
      const ref = A.optimize(c, clone(p));
      const s = A.createSearch(c, p); s.step(64); p.budget = 0; p.max_selected = 0; p.control_points[0].weight = 100;
      while (!s.step(4096)); const r = s.result();
      const same = JSON.stringify([r.status, r.objectives, r.feasible_count]) === JSON.stringify([ref.status, ref.objectives, ref.feasible_count]);
      return { ok: same, detail: { ref: [ref.status, ref.feasible_count, ref.objectives && ref.objectives.mean.ids], got: [r.status, r.feasible_count, r.objectives && r.objectives.mean && r.objectives.mean.ids] } }; } },
};
const RS = {
  R13_create:   { what: "createResilienceSearch, 13 кандидатов", refuse: (A) => A.createSearch(A.ctx("shymkent"), envelope(A, 13)) },
  R13_optimize: { what: "optimizeResilience, 13 кандидатов", refuse: (A) => A.optimize(A.ctx("shymkent"), envelope(A, 13)) },
  R13_evaluate: { what: "evaluateResilience, 13 кандидатов", refuse: (A) => A.evaluate(A.ctx("shymkent"), envelope(A, 13), ["c0"]) },
  R16_optimize: { what: "optimizeResilience, 16 кандидатов (предел v2, не устойчивости)", refuse: (A) => A.optimize(A.ctx("shymkent"), envelope(A, 16)) },
  R_cases_8user: { what: "8 пользовательских случаев (+base = 9) → optimizeResilience", refuse: (A) => A.optimize(A.ctx("shymkent"), envelope(A, 4, 8)) },
  R_after_validation: { what: "envelope прошёл validate, затем 13-й кандидат → optimizeResilience",
    refuse: (A) => { const c = A.ctx("shymkent"); const v = A.validate(envelope(A, 12), c); const p = v.plan || v;
      p.candidates.push({ ...p.candidates[0], id: "c_extra", lon: p.candidates[0].lon }); return A.optimize(c, v); } },
  R_candidate_as_source: { what: "ID кандидата в disabled_source_ids → optimizeResilience",
    refuse: (A) => { const e = envelope(A, 3); e.cases[0].disabled_source_ids = ["c0"]; return A.optimize(A.ctx("shymkent"), e); } },
  R_reserved_base: { what: "case id \"base\" → evaluateResilience", refuse: (A) => { const e = envelope(A, 3); e.cases[0].id = "base"; return A.evaluate(A.ctx("shymkent"), e, ["c0"]); } },
  RC_valid12: { what: "контроль: 12 кандидатов × 7 случаев → optimal, 4096 наборов",
    check: (A) => { const r = A.optimize(A.ctx("shymkent"), envelope(A, 12, 7)); return { ok: r.status === "optimal" && r.evaluated === 4096, detail: { status: r.status, evaluated: r.evaluated } }; } },
};

// ---------------------------------------------------------------- child: run one probe, print one JSON line
if (args.includes("--child")) {
  const [group, id] = opt("--child").split(":");
  const A = load(group === "v2" ? V2_ADAPTER : RS_ADAPTER);
  const P = (group === "v2" ? V2 : RS)[id];
  const t0 = process.hrtime.bigint();
  let out;
  try {
    if (P.check) { const r = P.check(A); out = { kind: "check", ok: !!r.ok, detail: r.detail }; }
    else { const r = P.refuse(A); out = { kind: "accepted", detail: summarize(r) }; }
  } catch (e) {
    out = { kind: e && typeof e.code === "string" && e.code ? "refused" : "crash", code: e && e.code, name: e && e.name, message: String(e && e.message).slice(0, 160) };
  }
  out.ms = +(Number(process.hrtime.bigint() - t0) / 1e6).toFixed(2);
  fs.writeSync(1, JSON.stringify(out) + "\n");
  process.exit(0);
}

// ---------------------------------------------------------------- parent
function availability() {
  const v2 = (() => { try { return load(V2_ADAPTER); } catch (e) { return { adapterError: String(e.message).slice(0, 200) }; } })();
  const rs = (() => { try { return load(RS_ADAPTER); } catch (e) { return { adapterError: String(e.message).slice(0, 200) }; } })();
  return { v2, rs };
}
const av = availability();
const only = opt("--only", null), onlySet = only ? new Set(only.split(",")) : null;
const results = [];
for (const [group, table, A] of [["v2", V2, av.v2], ["rs", RS, av.rs]]) {
  for (const [id, P] of Object.entries(table)) {
    if (onlySet && !onlySet.has(id)) continue;
    const row = { group, id, what: P.what, expect: P.check ? "check" : "typed refusal before heavy work" };
    if (!A) { row.status = "NOT_RUN"; row.detail = "web/resilience.js отсутствует в этой сборке"; results.push(row); continue; }
    if (A.adapterError) { row.status = "NOT_RUN"; row.detail = `adapter: ${A.adapterError}`; results.push(row); continue; }
    const r = spawnSync(process.execPath, [__filename, "--child", `${group}:${id}`, "--app-root", APP, "--v2-adapter", V2_ADAPTER, "--rs-adapter", RS_ADAPTER],
      { encoding: "utf8", timeout: TIMEOUT });
    const line = String(r.stdout || "").trim().split("\n").filter(Boolean).pop();
    let o = null; try { o = JSON.parse(line); } catch (e) { o = null; }
    if (!o) { row.status = "FAIL"; row.outcome = r.error ? "timeout" : "no_answer"; row.detail = r.error ? `снят сторожем через ${TIMEOUT} мс` : String(r.stderr || "").slice(0, 200); }
    else if (P.check) { row.status = o.kind === "check" && o.ok ? "PASS" : "FAIL"; row.outcome = o.kind; row.ms = o.ms; row.detail = o.detail || o.message; }
    else {
      row.outcome = o.kind; row.ms = o.ms; row.code = o.code || null;
      row.status = o.kind === "refused" && o.ms < FAST_MS ? "PASS" : "FAIL";
      row.detail = o.kind === "accepted" ? o.detail : o.kind === "crash" ? `${o.name}: ${o.message}` : o.ms >= FAST_MS ? `отказ после ${o.ms} мс` : o.message;
    }
    results.push(row);
    console.log(`${row.status.padEnd(7)} ${group}/${id.padEnd(24)} ${String(row.outcome || "").padEnd(9)} ${row.code ? `code=${row.code} ` : ""}${row.ms !== undefined ? `${row.ms} ms ` : ""}${row.status === "PASS" ? "" : JSON.stringify(row.detail).slice(0, 180)}`);
  }
}
for (const r of results.filter((x) => x.status === "NOT_RUN")) console.log(`NOT_RUN ${r.group}/${r.id} ${r.detail}`);
const summary = { app_root: path.basename(APP), timeout_ms: TIMEOUT, fast_ms: FAST_MS, total: results.length,
  pass: results.filter((r) => r.status === "PASS").length, fail: results.filter((r) => r.status === "FAIL").map((r) => `${r.group}/${r.id}`),
  not_run: results.filter((r) => r.status === "NOT_RUN").length,
  verdict: results.some((r) => r.status === "FAIL") ? "FAIL" : "PASS" };
console.log(JSON.stringify(summary));
if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 1) + "\n");
process.exit(summary.verdict === "PASS" ? 0 : 1);
