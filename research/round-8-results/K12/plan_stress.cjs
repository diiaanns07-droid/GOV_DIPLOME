// K12 round 8, stage 1: portable stress test for a city-plan-v2 IMPORTER + optimizer (CORE_SPEC.txt @ c3f6c00).
// Node >= 18, no dependencies, headless (no DOM). Fixture files are read as text only; nothing is executed or fetched.
//
//   node plan_stress.cjs --app-root <prototypes/city-evidence copy> [--adapter adapters/reference_v2_adapter.cjs]
//        [--index FIXTURES_V2_INDEX.json] [--expected expected/oracle_<sha>.json] [--out results.json] [--strict-codes]
//
// Adapter (see HANDOFF.md):  snapshot(city) · initialState() · importScenario(text, state) -> {ok, code, state}
//   optional: evaluate(state) -> {selected_ids, rows, metrics, feasibility} · optimize(state) -> optimizePlans result
//             problemDigest(state) · currentState()
// Negative fixtures: refused without exception; returned/current state unchanged; passed state not mutated; no network;
// Object.prototype unchanged; no new globals. Positive fixtures: accepted; evaluate/optimize equal the independent
// Python oracle (expected/oracle_*.json, computed on the same data.js — sha256 checked), derived_results ignored.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const HERE = __dirname;
const APP = opt("--app-root");
if (!APP) { console.error("usage: node plan_stress.cjs --app-root <dir> [--adapter a.cjs] [--expected e.json] [--out r.json]"); process.exit(2); }
const ADAPTER = path.resolve(opt("--adapter", path.join(HERE, "adapters", "reference_v2_adapter.cjs")));
const INDEX = path.resolve(opt("--index", path.join(HERE, "FIXTURES_V2_INDEX.json")));
const EXPECTED = opt("--expected", null);
const OUT = opt("--out");
const STRICT_CODES = args.includes("--strict-codes");

// ---------------------------------------------------------------- network guard (before any adapter code)
const NET = [];
const trap = (what) => function () { NET.push(what); throw new Error(`K12 network guard: ${what} blocked`); };
for (const [mod, fns] of [["http", ["request", "get"]], ["https", ["request", "get"]], ["net", ["connect", "createConnection"]], ["tls", ["connect"]]]) {
  const m = require(mod);
  for (const f of fns) m[f] = trap(`${mod}.${f}`);
}
globalThis.fetch = trap("fetch");

// ---------------------------------------------------------------- app context (as tests/conformance.cjs)
const WEB = path.join(path.resolve(APP), "web");
const ctx = {};
vm.createContext(ctx);
ctx.window = ctx;
ctx.fetch = trap("window.fetch");
ctx.XMLHttpRequest = function () { NET.push("XMLHttpRequest"); throw new Error("K12 network guard: XMLHttpRequest blocked"); };
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(WEB, f), "utf8"), ctx, { filename: f });
const DATA_SHA = crypto.createHash("sha256").update(fs.readFileSync(path.join(WEB, "data.js"))).digest("hex");
const A = require(ADAPTER)({ appRoot: path.resolve(APP), D: ctx.CITY_EVIDENCE, EV: ctx.CITY_OBS, ctx, requireWeb: (n) => require(path.join(WEB, n)) });
for (const fn of ["snapshot", "initialState", "importScenario"]) if (typeof A[fn] !== "function") { console.error(`adapter lacks ${fn}()`); process.exit(2); }

// ---------------------------------------------------------------- expected values (independent oracle)
let EXP = null, expNote = "no --expected: oracle comparison skipped";
if (EXPECTED) {
  const e = JSON.parse(fs.readFileSync(EXPECTED, "utf8"));
  if (e.data_js_sha256 !== DATA_SHA) expNote = `oracle computed on data.js ${e.data_js_sha256.slice(0, 12)} ≠ app ${DATA_SHA.slice(0, 12)}: comparison skipped`;
  else { EXP = Object.fromEntries(e.results.map((r) => [r.name, r])); expNote = `oracle ${path.basename(EXPECTED)} (data.js ${DATA_SHA.slice(0, 12)})`; }
}

// ---------------------------------------------------------------- fixtures
const IDX = JSON.parse(fs.readFileSync(INDEX, "utf8"));
const FIXDIR = path.dirname(INDEX);
const byId = Object.fromEntries(IDX.fixtures.map((f) => [f.id, f]));
const OTHER = { shymkent: "astana", astana: "shymkent" };
const sha = (s) => crypto.createHash("sha256").update(Buffer.from(s, "utf8")).digest("hex");
const sub = (text, f) => text.split('"__SNAPSHOT__"').join(JSON.stringify(A.snapshot(f.city)))
  .split('"__SNAPSHOT_OTHER_CITY__"').join(JSON.stringify(A.snapshot(OTHER[f.city])));
function recipe(base, r) {
  if (r.op === "pad") return base.slice(0, -1) + " ".repeat(r.total_bytes - Buffer.byteLength(base, "utf8")) + base.slice(-1);
  const anchor = '"selected_ids": [';
  if (r.op === "insert_derived") return base.replace(anchor, '"derived_results": {"note": "' + r.char.repeat(r.count) + '"},\n ' + anchor);
  if (r.op === "deep_derived") return base.replace(anchor, '"derived_results": ' + "[".repeat(r.depth) + "]".repeat(r.depth) + ",\n " + anchor);
  throw new Error("unknown recipe " + r.op);
}
const raw = (f) => fs.readFileSync(path.join(FIXDIR, f.file)).toString("utf8");
function textOf(f) {
  if (!f.recipe) { const t = raw(f); if (sha(t) !== f.sha256) throw new Error(`${f.id}: sha256 differs from index`); return sub(t, f); }
  const base = raw(byId[f.recipe.from]);
  if (sha(recipe(base, f.recipe)) !== f.sha256) throw new Error(`${f.id}: recipe output sha256 differs from index`);
  return recipe(sub(base, byId[f.recipe.from]), f.recipe);
}

// ---------------------------------------------------------------- invariant probes
const protoKeys = () => Object.getOwnPropertyNames(Object.prototype).sort().join(",") + "|" + Object.getOwnPropertyNames(Array.prototype).length;
const globalsOf = () => Object.keys(ctx).sort().join(",") + "|" + Object.keys(globalThis).sort().join(",");
const view = (s) => JSON.stringify(s);
function callImport(text, state) {
  const passed = JSON.parse(JSON.stringify(state));
  const before = { state: view(state), current: A.currentState ? view(A.currentState()) : null, proto: protoKeys(), globals: globalsOf(), net: NET.length };
  let r, threw = null;
  const t0 = process.hrtime.bigint();
  try { r = A.importScenario(text, passed); } catch (e) { threw = `${e && e.name}: ${e && e.message}`.slice(0, 200); }
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  return { r, threw, ms, before, after: { passed: view(passed), current: A.currentState ? view(A.currentState()) : null,
           proto: protoKeys(), globals: globalsOf(), net: NET.length },
           polluted: ({}).k12_polluted !== undefined || ctx.__K12_PWNED__ !== undefined || globalThis.__K12_PWNED__ !== undefined };
}

// ---------------------------------------------------------------- oracle comparison
const metricKeys = ["unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost"];
function compareOptimize(got, exp) {
  const diffs = [];
  if (got.status !== exp.status) diffs.push(`status ${got.status} ≠ ${exp.status}`);
  if (got.feasible_count !== exp.feasible_count) diffs.push(`feasible_count ${got.feasible_count} ≠ ${exp.feasible_count}`);
  // for an infeasible problem CORE_SPEC does not define "evaluated" (0 = not enumerated, or 2^|free| = enumerated, none fit)
  if (got.evaluated !== exp.evaluated && !(got.status === "infeasible" && exp.status === "infeasible")) diffs.push(`evaluated ${got.evaluated} ≠ ${exp.evaluated}`);
  for (const k of ["mean", "minimax", "coverage"]) {
    const g = got.objectives[k], x = exp.objectives[k];
    if ((g === null) !== (x === null)) { diffs.push(`${k}: null mismatch`); continue; }
    if (!g) continue;
    if (JSON.stringify(g.selected_ids) !== JSON.stringify(x.selected_ids)) diffs.push(`${k} ids ${g.selected_ids} ≠ ${x.selected_ids}`);
    for (const m of metricKeys) if (g.metrics[m] !== x.metrics[m]) diffs.push(`${k}.${m} ${g.metrics[m]} ≠ ${x.metrics[m]}`);
  }
  const gp = JSON.stringify(got.pareto.map((p) => [p.cost, p.weighted_sum_mm, p.selected_ids]));
  const xp = JSON.stringify(exp.pareto.map((p) => [p.cost, p.weighted_sum_mm, p.selected_ids]));
  if (gp !== xp) diffs.push("pareto differs");
  if (got.sensitivity && exp.sensitivity) {
    const gs = JSON.stringify(got.sensitivity.map((s) => [s.budget, s.status, s.feasible_count, s.mean ? s.mean.selected_ids : null]));
    const xs = JSON.stringify(exp.sensitivity.map((s) => [s.budget, s.status, s.feasible_count, s.mean_ids || null]));
    if (gs !== xs) diffs.push("sensitivity differs");
  }
  return diffs;
}
function compareEvaluate(got, exp) {
  const diffs = [];
  for (const m of metricKeys) if (got.metrics[m] !== exp.selected_evaluation[m]) diffs.push(`manual.${m} ${got.metrics[m]} ≠ ${exp.selected_evaluation[m]}`);
  for (const row of got.rows) if (row.after_mm !== exp.selected_after_mm[row.id]) diffs.push(`row ${row.id} after_mm ${row.after_mm} ≠ ${exp.selected_after_mm[row.id]}`);
  return diffs;
}

// ---------------------------------------------------------------- run
const START = (() => {
  const r = A.importScenario(textOf(byId.V01), A.initialState());
  if (!r || !r.ok) { console.error("V01 (valid baseline) not accepted — invariants cannot be checked", r && r.code); process.exit(1); }
  return r.state;
})();
const accepted = {};
const results = [];
for (const f of IDX.fixtures) {
  const res = { id: f.id, expect: f.expect, expected_codes: f.expected_codes, checks: {} };
  let text;
  try { text = textOf(f); } catch (e) { res.status = "ERROR"; res.error = e.message; results.push(res); continue; }
  res.bytes = Buffer.byteLength(text, "utf8");
  const start = f.expect === "accept" ? A.initialState() : START;
  const c = callImport(text, start);
  const ok = !!(c.r && c.r.ok);
  res.outcome = c.threw ? "exception" : ok ? "accepted" : "rejected";
  res.code = c.r ? c.r.code ?? null : null;
  res.import_ms = +c.ms.toFixed(2);
  const C = res.checks;
  C.no_exception = !c.threw;
  C.passed_state_not_mutated = c.after.passed === c.before.state;
  C.no_network = c.after.net === c.before.net;
  C.prototype_unchanged = c.after.proto === c.before.proto && !c.polluted;
  C.no_new_globals = c.after.globals === c.before.globals;
  if (f.expect === "accept" && !ok && !c.threw && f.check.reject_allowed) {
    res.advisory = `refused (${res.code}); ${f.check.reject_allowed}`;
    C.returned_state_unchanged = !c.r || view(c.r.state) === c.before.state;
  } else if (f.expect === "accept") {
    C.accepted = ok;
    if (ok) {
      accepted[f.id] = c.r.state;
      const exp = EXP && EXP[f.id];
      if (typeof A.optimize === "function" && f.check.optimize) {
        const o = A.optimize(c.r.state);
        C.optimize_status = o.status === f.check.optimize;
        if (f.check.reason) {                     // reason names are not fixed by CORE_SPEC: meaning is hard, exact name is advisory
          const rs = o.reasons || [];
          C.infeasible_reason = rs.includes(f.check.reason) || (!!f.check.reason_pattern && rs.some((x) => String(x).includes(f.check.reason_pattern)));
          if (C.infeasible_reason && !rs.includes(f.check.reason)) res.advisory = `reason name ${rs.join(",")} (K12 name ${f.check.reason})`;
        }
        C.strict_json_output = (() => { try { return JSON.stringify(JSON.parse(JSON.stringify(o))) === JSON.stringify(o) && !/Infinity|NaN/.test(JSON.stringify(o)); } catch (e) { return false; } })();
        if (exp) { const d = compareOptimize(o, exp); C.optimize_equals_oracle = d.length === 0; if (d.length) res.oracle_diff = d.slice(0, 8); }
        if (f.check.must_not_contain) C.poison_not_used = f.check.must_not_contain.every((v) => !JSON.stringify(o).includes(String(v)));
        if (f.check.same_as && accepted[f.check.same_as] && A.problemDigest) {
          C.same_problem_digest = A.problemDigest(c.r.state) === A.problemDigest(accepted[f.check.same_as]);
          C.same_plans = JSON.stringify(o.objectives) === JSON.stringify(A.optimize(accepted[f.check.same_as]).objectives);
        }
        res.summary = { status: o.status, feasible: o.feasible_count, mean: o.objectives.mean && o.objectives.mean.selected_ids };
      }
      if (typeof A.evaluate === "function") {
        const ev = A.evaluate(c.r.state);
        if (exp) { const d = compareEvaluate(ev, exp); C.evaluate_equals_oracle = d.length === 0; if (d.length) res.oracle_diff = (res.oracle_diff || []).concat(d.slice(0, 6)); }
        if (f.check.must_not_contain) C.poison_not_used_eval = f.check.must_not_contain.every((v) => !JSON.stringify(ev).includes(String(v)));
        if ("manual_feasible" in f.check) C.manual_feasibility = ev.feasibility.feasible === f.check.manual_feasible;
      }
    }
  } else {
    C.rejected = !ok && !c.threw;
    C.returned_state_unchanged = !c.r || view(c.r.state) === c.before.state;
    C.current_state_unchanged = c.after.current === c.before.current;
    if (f.expected_codes.length) res.code_match = f.expected_codes.includes(res.code);
  }
  const hard = Object.entries(C).filter(([, v]) => v === false).map(([k]) => k);
  if (STRICT_CODES && res.code_match === false) hard.push("code_match");
  res.failed_checks = hard;
  res.status = hard.length ? "FAIL" : res.advisory ? "ADVISORY" : "PASS";
  results.push(res);
}
const summary = { adapter: path.basename(ADAPTER), app_root: path.basename(path.resolve(APP)), data_js_sha256: DATA_SHA, oracle: expNote,
  fixtures: IDX.fixture_set, total: results.length, pass: results.filter((r) => r.status === "PASS").length,
  advisory: results.filter((r) => r.status === "ADVISORY").map((r) => `${r.id}: ${r.advisory}`),
  fail: results.filter((r) => r.status === "FAIL").map((r) => r.id), error: results.filter((r) => r.status === "ERROR").map((r) => r.id),
  code_mismatch: results.filter((r) => r.code_match === false).map((r) => `${r.id}:${r.code}`), network_attempts: NET.length,
  max_import_ms: Math.max(...results.map((r) => r.import_ms || 0)) };
for (const r of results) console.log(`${r.status.padEnd(8)} ${r.id} ${String(r.outcome).padEnd(9)} code=${String(r.code).padEnd(24)}` +
  (r.failed_checks && r.failed_checks.length ? ` failed: ${r.failed_checks.join(",")}` : "") + (r.oracle_diff ? ` ${r.oracle_diff.join("; ")}` : "") + (r.error ? ` ${r.error}` : ""));
console.log(JSON.stringify(summary));
if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 1) + "\n");
process.exit(summary.fail.length || summary.error.length ? 1 : 0);
