// K12 round 7: portable stress test for a city-whatif-v1 scenario IMPORTER (FEATURE_SPEC.txt @ 7927fa8).
// Not a UI. Node >= 18, no dependencies. Fixture files are only read as text: nothing is executed or fetched.
//
//   node whatif_import_stress.cjs --app-root <prototypes/city-evidence copy> [--adapter <adapter.cjs>]
//                                 [--index FIXTURES_INDEX.json] [--out results.json] [--strict-codes]
//
// The adapter (see ADAPTER.md) maps the importer under test to:
//   snapshot(city, category) -> string            initialState(city, category) -> state
//   importScenario(text, state) -> {ok, code, state}   (must not mutate `state`)
//   compute(state) -> rows [{id, before_m, after_m, delta_m, nearest_before_id}]   (optional)
//   currentState() -> state   (optional, for importers that keep the active scenario internally)
//
// For every negative fixture, starting from the accepted P01 scenario:
//   refused (ok === false, no exception); returned state == state before; the passed state object not mutated;
//   currentState()/compute() unchanged; no network attempt; Object.prototype unchanged; no new globals.
// For positive fixtures: accepted; compute() equals this module's own haversine oracle (imported results ignored).
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");

// ---------------------------------------------------------------- arguments
const args = process.argv.slice(2);
const opt = (name, def) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : def; };
const flag = (name) => args.includes(name);
const HERE = __dirname;
const APP = opt("--app-root");
if (!APP) { console.error("usage: node whatif_import_stress.cjs --app-root <dir> [--adapter a.cjs] [--out r.json]"); process.exit(2); }
const ADAPTER = path.resolve(opt("--adapter", path.join(HERE, "adapters", "reference_adapter.cjs")));
const INDEX = path.resolve(opt("--index", path.join(HERE, "FIXTURES_INDEX.json")));
const FIXDIR = path.dirname(INDEX);
const OUT = opt("--out");
const STRICT_CODES = flag("--strict-codes");

// ---------------------------------------------------------------- network guard (installed before any adapter code)
const NET = [];
const trap = (what) => function () { NET.push(what); throw new Error(`K12 network guard: ${what} blocked`); };
for (const [mod, fns] of [["http", ["request", "get"]], ["https", ["request", "get"]], ["net", ["connect", "createConnection"]], ["tls", ["connect"]]]) {
  const m = require(mod);
  for (const f of fns) m[f] = trap(`${mod}.${f}`);
}
globalThis.fetch = trap("fetch");

// ---------------------------------------------------------------- app context (data.js, evidence.js like tests/conformance.cjs)
const WEB = path.join(path.resolve(APP), "web");
const ctx = {};
vm.createContext(ctx);
ctx.window = ctx;
ctx.fetch = trap("window.fetch");
ctx.XMLHttpRequest = function () { NET.push("XMLHttpRequest"); throw new Error("K12 network guard: XMLHttpRequest blocked"); };
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(WEB, f), "utf8"), ctx, { filename: f });
const D = ctx.CITY_EVIDENCE, EV = ctx.CITY_OBS;
const requireWeb = (name) => require(path.join(WEB, name));
const A = require(ADAPTER)({ appRoot: path.resolve(APP), D, EV, ctx, requireWeb });
for (const fn of ["snapshot", "initialState", "importScenario"]) if (typeof A[fn] !== "function") { console.error(`adapter lacks ${fn}()`); process.exit(2); }

// ---------------------------------------------------------------- independent oracle (spec formula)
const R = 6371008.8, RAD = Math.PI / 180;
function hav(lon1, lat1, lon2, lat2) {
  let a = Math.sin((lat2 - lat1) * RAD / 2) ** 2 + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin((lon2 - lon1) * RAD / 2) ** 2;
  a = Math.min(1, Math.max(0, a));
  return 2 * R * Math.asin(Math.sqrt(a));
}
function oracle(s) {
  const recs = D.cities[s.city_id].places.filter((p) => p.group === s.category);
  const pr = s.proposed_object;
  return s.control_points.map((cp) => {
    let best = null;
    for (const r of recs) { const d = hav(cp.lon, cp.lat, r.lon, r.lat); if (!best || d < best.d || (d === best.d && r.id < best.id)) best = { d, id: r.id }; }
    const before = best ? best.d : null, dp = pr ? hav(cp.lon, cp.lat, pr.lon, pr.lat) : null;
    const after = pr ? (before === null ? dp : Math.min(before, dp)) : before;
    return { id: cp.id, before_m: before, after_m: after, delta_m: before === null ? null : before - after, nearest_before_id: best ? best.id : null };
  });
}
const close = (a, b) => (a === null && b === null) || (typeof a === "number" && typeof b === "number" && Math.abs(a - b) <= 1e-6);

// ---------------------------------------------------------------- fixtures
const IDX = JSON.parse(fs.readFileSync(INDEX, "utf8"));
const byId = Object.fromEntries(IDX.fixtures.map((f) => [f.id, f]));
const OTHER_CITY = { shymkent: "astana", astana: "shymkent" };
const OTHER_CAT = { school: "outpatient_clinic", outpatient_clinic: "school" };
const sha = (s) => crypto.createHash("sha256").update(Buffer.from(s, "utf8")).digest("hex");
function snap(city, cat) {
  try { return A.snapshot(city, cat); } catch (e) { return A.snapshot(CITY_FALLBACK(city), cat === "school" || cat === "outpatient_clinic" ? cat : "school"); }
}
const CITY_FALLBACK = (c) => (c === "astana" ? "astana" : "shymkent");
function substitute(text, f) {
  const city = CITY_FALLBACK(f.city), cat = f.category;
  return text.split('"__SNAPSHOT__"').join(JSON.stringify(snap(city, cat)))
    .split('"__SNAPSHOT_OTHER_CITY__"').join(JSON.stringify(snap(OTHER_CITY[city], cat)))
    .split('"__SNAPSHOT_OTHER_CATEGORY__"').join(JSON.stringify(snap(city, OTHER_CAT[cat] || "school")));
}
function applyRecipe(base, r) {
  if (r.op === "pad") {
    const pad = r.total_bytes - Buffer.byteLength(base, "utf8");
    if (pad < 0) throw new Error("recipe pad: base too large");
    return base.slice(0, -1) + " ".repeat(pad) + base.slice(-1);
  }
  if (r.op === "insert_label") {
    const anchor = '"id": "cp1",';
    return base.replace(anchor, anchor + ' "label": "' + r.char.repeat(r.count) + '",');
  }
  throw new Error("unknown recipe " + r.op);
}
const rawText = (f) => fs.readFileSync(path.join(FIXDIR, f.file)).toString("utf8");
function fixtureText(f) {
  if (!f.recipe) {
    const raw = rawText(f);
    if (sha(raw) !== f.sha256) throw new Error(`${f.id}: file sha256 differs from index`);
    return substitute(raw, f);
  }
  const base = rawText(byId[f.recipe.from]);
  const built = applyRecipe(base, f.recipe);
  if (sha(built) !== f.sha256) throw new Error(`${f.id}: recipe output sha256 differs from index (generator/test mismatch)`);
  return applyRecipe(substitute(base, byId[f.recipe.from]), f.recipe); // same size rule after substitution
}

// ---------------------------------------------------------------- run
const protoKeys = () => Object.getOwnPropertyNames(Object.prototype).sort().join(",");
const globalsOf = () => Object.keys(ctx).sort().join(",") + "|" + Object.keys(globalThis).sort().join(",");
const view = (st) => JSON.stringify(st);
const tryCompute = (st) => { if (typeof A.compute !== "function") return null; try { return JSON.stringify(A.compute(st)); } catch (e) { return "compute threw: " + e.message; } };

function callImport(text, state) {
  const passed = JSON.parse(JSON.stringify(state));
  const before = { state: view(state), current: A.currentState ? view(A.currentState()) : null, compute: tryCompute(state),
                   proto: protoKeys(), globals: globalsOf(), net: NET.length };
  let r, threw = null;
  try { r = A.importScenario(text, passed); } catch (e) { threw = `${e && e.name}: ${e && e.message}`; }
  const after = { passed: view(passed), current: A.currentState ? view(A.currentState()) : null,
                  proto: protoKeys(), globals: globalsOf(), net: NET.length };
  return { r, threw, before, after, polluted: ({}).k12_polluted !== undefined || ctx.__K12_PWNED__ !== undefined };
}

const START = (() => {
  const p01 = byId.P01;
  const r = A.importScenario(fixtureText(p01), A.initialState("shymkent", "school"));
  if (!r || !r.ok) { console.error("P01 (valid baseline) was not accepted — invariants cannot be checked", r); process.exit(1); }
  return r.state;
})();

const results = [];
for (const f of IDX.fixtures) {
  const res = { id: f.id, expect: f.expect, advisory: f.advisory, expected_codes: f.expected_codes, checks: {} };
  let text;
  try { text = fixtureText(f); } catch (e) { res.status = "ERROR"; res.error = e.message; results.push(res); continue; }
  res.bytes = Buffer.byteLength(text, "utf8");
  const startState = f.expect === "accept" ? A.initialState(CITY_FALLBACK(f.city), f.category) : START;
  const c = callImport(text, startState);
  const ok = c.r && c.r.ok === true;
  res.outcome = c.threw ? "exception" : ok ? "accepted" : "rejected";
  res.code = c.r ? c.r.code ?? null : null;
  const C = res.checks;
  C.no_exception = !c.threw;
  C.passed_state_not_mutated = c.after.passed === c.before.state;
  C.no_network = c.after.net === c.before.net;
  C.prototype_unchanged = c.after.proto === c.before.proto && !c.polluted;
  C.no_new_globals = c.after.globals === c.before.globals;
  if (f.expect === "accept") {
    C.accepted = ok;
    if (ok && typeof A.compute === "function") {
      const s = JSON.parse(text.replace(/^﻿/, ""));
      const exp = oracle(s), got = A.compute(c.r.state);
      const gm = Object.fromEntries((got || []).map((row) => [row.id, row]));
      C.recomputed_equals_oracle = exp.length === (got || []).length && exp.every((e) => gm[e.id] && close(gm[e.id].before_m, e.before_m) &&
        close(gm[e.id].after_m, e.after_m) && close(gm[e.id].delta_m, e.delta_m) && gm[e.id].nearest_before_id === e.nearest_before_id);
      res.oracle_rows = exp.map((e) => ({ ...e, before_m: e.before_m && +e.before_m.toFixed(3), after_m: e.after_m && +e.after_m.toFixed(3),
                                          delta_m: e.delta_m && +e.delta_m.toFixed(3) }));
    } else if (ok) C.recomputed_equals_oracle = "skipped (adapter has no compute)";
  } else if (f.expect === "reject") {
    C.rejected = !ok && !c.threw;
    C.returned_state_unchanged = !c.r || view(c.r.state) === c.before.state;
    C.current_state_unchanged = c.after.current === c.before.current;
    C.compute_unchanged = tryCompute(c.r ? c.r.state : startState) === c.before.compute;
    if (f.expected_codes.length) res.code_match = f.expected_codes.includes(res.code);
  } else { // reject_or_accept (advisory)
    C.no_crash = !c.threw;
    if (!ok) C.returned_state_unchanged = !c.r || view(c.r.state) === c.before.state;
  }
  const hard = Object.entries(C).filter(([, v]) => v === false).map(([k]) => k);
  if (STRICT_CODES && res.code_match === false) hard.push("code_match");
  res.failed_checks = hard;
  res.status = hard.length ? (f.advisory ? "ADVISORY_FAIL" : "FAIL") : "PASS";
  results.push(res);
}

const summary = { adapter: path.basename(ADAPTER), app_root: path.basename(path.resolve(APP)), index: IDX.fixture_set,
  total: results.length, pass: results.filter((r) => r.status === "PASS").length,
  fail: results.filter((r) => r.status === "FAIL").map((r) => r.id),
  advisory_fail: results.filter((r) => r.status === "ADVISORY_FAIL").map((r) => r.id),
  error: results.filter((r) => r.status === "ERROR").map((r) => r.id),
  code_mismatch: results.filter((r) => r.code_match === false).map((r) => `${r.id}:${r.code}`),
  network_attempts: NET.length };
for (const r of results) {
  console.log(`${r.status.padEnd(13)} ${r.id} ${String(r.outcome).padEnd(9)} code=${String(r.code).padEnd(18)}` +
              (r.failed_checks && r.failed_checks.length ? ` failed: ${r.failed_checks.join(",")}` : "") + (r.error ? ` ${r.error}` : ""));
}
console.log(JSON.stringify(summary));
if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 1) + "\n");
process.exit(summary.fail.length || summary.error.length ? 1 : 0);
