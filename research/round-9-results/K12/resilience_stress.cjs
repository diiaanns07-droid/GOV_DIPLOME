// K12 round 9, stage 2: city-resilience-v1 corpus (FIXTURES_RS_INDEX.json) against an implementation behind an adapter,
// plus checks that run on the ACTUAL build even before it has a resilience module:
//   R  — resilience import via --adapter (BUILD: adapters/build_resilience_import_adapter.cjs; NOT_RUN without web/resilience.js;
//        adapters/oracle_rs_import_adapter.cjs = self-test of this harness against the K12 oracle, NOT a BUILD test);
//   X  — actual BUILD web/plan.js + web/whatif.js: envelopes refused atomically by the v1/v2 importers, the plan part of every
//        accepted envelope is a valid v2 file whose mean optimum equals the oracle "nominal" plan, plan-level negatives,
//        data.js / CITY_EVIDENCE / frozen context unchanged, no network.
//   node resilience_stress.cjs --app-root <copy> [--adapter ...] [--expected expected/rs_oracle_d865dd4.json] [--out r.json]
// All plans/costs/weights are SYNTHETIC; source IDs are real record IDs of the slice. Nothing is fetched.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const HERE = __dirname;
const APP = path.resolve(opt("--app-root", ""));
const ADAPTER = path.resolve(opt("--adapter", path.join(HERE, "adapters", "build_resilience_import_adapter.cjs")));
const EXPECTED = opt("--expected", path.join(HERE, "expected", "rs_oracle_d865dd4.json"));
const OUT = opt("--out");
if (!fs.existsSync(path.join(APP, "web", "data.js"))) { console.error("usage: node resilience_stress.cjs --app-root <dir>"); process.exit(2); }

// ---------------------------------------------------------------- network guard
const NET = [];
const trap = (what) => function () { NET.push(what); throw new Error(`K12 network guard: ${what}`); };
for (const [mod, fns] of [["http", ["request", "get"]], ["https", ["request", "get"]], ["net", ["connect", "createConnection"]], ["tls", ["connect"]]]) {
  const m = require(mod); for (const f of fns) m[f] = trap(`${mod}.${f}`);
}
globalThis.fetch = trap("fetch");

// ---------------------------------------------------------------- app context
const WEB = path.join(APP, "web");
const DATA_FILE = path.join(WEB, "data.js");
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const DATA_SHA_BEFORE = sha(fs.readFileSync(DATA_FILE));
const CTX = {}; vm.createContext(CTX); CTX.window = CTX;
CTX.fetch = trap("window.fetch");
CTX.XMLHttpRequest = function () { NET.push("XMLHttpRequest"); throw new Error("K12 network guard"); };
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(WEB, f), "utf8"), CTX, { filename: f });
const D = CTX.CITY_EVIDENCE;
const D_HASH = () => sha(JSON.stringify(D));
const D_BEFORE = D_HASH();
const requireWeb = (n) => require(path.join(WEB, n));
const A = require(ADAPTER)({ appRoot: APP, D, EV: CTX.CITY_OBS, ctx: CTX, requireWeb });

// ---------------------------------------------------------------- corpus
const IDX = JSON.parse(fs.readFileSync(path.join(HERE, "FIXTURES_RS_INDEX.json"), "utf8"));
const byId = Object.fromEntries(IDX.fixtures.map((f) => [f.id, f]));
const OTHER = { shymkent: "astana", astana: "shymkent" };
const raw = (f) => fs.readFileSync(path.join(HERE, f.file)).toString("utf8");
function recipe(base, r) {
  if (r.op === "pad") return base.slice(0, -2) + " ".repeat(r.total_bytes - Buffer.byteLength(base, "utf8")) + base.slice(-2);
  if (r.op === "deep_field") return base.replace('"cases": [', '"pad": ' + "[".repeat(r.depth) + "]".repeat(r.depth) + ', "cases": [');
  throw new Error("unknown recipe " + r.op);
}
// snapshot substitution: snap(city, current) -> value; recipes are applied after substitution so sizes stay exact
function textOf(f, snap) {
  const sub = (t) => t.split('"__SNAPSHOT__"').join(JSON.stringify(snap(f.city, true))).split('"__SNAPSHOT_OTHER_CITY__"').join(JSON.stringify(snap(OTHER[f.city], false)));
  if (!f.recipe) { const t = raw(f); if (sha(Buffer.from(t, "utf8")) !== f.sha256) throw new Error(`${f.id}: sha256 differs from index`); return sub(t); }
  const base = raw(byId[f.recipe.from]);
  if (sha(Buffer.from(recipe(base, f.recipe), "utf8")) !== f.sha256) throw new Error(`${f.id}: recipe sha256 differs from index`);
  return recipe(sub(base), f.recipe);
}
const EXP = fs.existsSync(EXPECTED) ? JSON.parse(fs.readFileSync(EXPECTED, "utf8")) : null;
const expOf = (id) => EXP && EXP.results.find((r) => r.name === id);
if (EXP && EXP.data_js_sha256 !== DATA_SHA_BEFORE) console.log(`NOTE expected results were computed on data.js ${EXP.data_js_sha256.slice(0, 12)}, this copy is ${DATA_SHA_BEFORE.slice(0, 12)}: oracle comparison skipped`);
const EXP_OK = !!EXP && EXP.data_js_sha256 === DATA_SHA_BEFORE;

// ---------------------------------------------------------------- reporting
const results = [];
const view = (x) => JSON.stringify(x);
function rec(group, id, title, status, detail) {
  results.push({ group, id, title, status, detail: detail === undefined ? null : detail });
  if (status !== "PASS") console.log(`${status.padEnd(8)} ${group}/${id} ${title}${detail !== undefined ? " — " + view(detail).slice(0, 220) : ""}`);
}
const protoSig = () => Object.getOwnPropertyNames(Object.prototype).sort().join(",") + "|" + Object.getOwnPropertyNames(Array.prototype).length;

// ================================================================ R: resilience import via adapter
if (A === null) {
  for (const f of IDX.fixtures) rec("R", f.id, `${f.expect} ${f.name}`, "NOT_RUN", "web/resilience.js отсутствует в этой сборке");
} else {
  const snapR = (city, current) => A.snapshot(city, current);
  const accepted = {};
  for (const f of IDX.fixtures) {
    const text = textOf(f, snapR);
    const st = A.initialState(), stView = view(st), passed = JSON.parse(stView);
    const before = { net: NET.length, proto: protoSig() };
    let r, threw = null;
    try { r = A.importEnvelope(text, passed); } catch (e) { threw = String(e && e.message).slice(0, 160); }
    const invariants = { no_exception: !threw, passed_unchanged: view(passed) === stView, no_network: NET.length === before.net,
      prototype_unchanged: protoSig() === before.proto && ({}).polluted === undefined, data_unchanged: D_HASH() === D_BEFORE };
    const bad = Object.entries(invariants).filter(([, v]) => !v).map(([k]) => k);
    const ok = !!(r && r.ok);
    if (f.expect === "reject") {
      if (!ok && !threw) {
        if (view(r.state) !== stView) bad.push("returned_state_changed");
        rec("R", f.id, `reject ${f.name}`, bad.length ? "FAIL" : "PASS", bad.length ? bad : { code: r.code, rule: f.rule });
      } else if (ok && f.policy) rec("R", f.id, `reject ${f.name}`, "ADVISORY", `принят; ${f.policy}`);
      else rec("R", f.id, `reject ${f.name}`, "FAIL", threw ? `exception ${threw}` : `принят (ожидался отказ: ${f.rule})`);
      continue;
    }
    if (!ok) { rec("R", f.id, `accept ${f.name}`, "FAIL", threw ? `exception ${threw}` : `отклонён: ${r.code}`); continue; }
    accepted[f.id] = r.state;
    if (typeof A.optimize !== "function") { rec("R", f.id, `accept ${f.name}`, bad.length ? "FAIL" : "PASS", bad.length ? bad : "optimize() не задан"); continue; }
    const o = A.optimize(r.state);
    const t = JSON.stringify(o);
    if (/NaN|Infinity/.test(t)) bad.push("non_strict_json_output");
    const x = EXP_OK && expOf(f.id), diffs = [];
    if (x) {
      if (o.status !== x.status) diffs.push(`status ${o.status} ≠ ${x.status}`);
      if (x.status === "optimal") {
        for (const k of ["nominal", "robust"]) {
          if (view(o[k] && o[k].ids) !== view(x[k].ids)) diffs.push(`${k}.ids ${view(o[k] && o[k].ids)} ≠ ${view(x[k].ids)}`);
          if (o[k] && o[k].worst_vector && view(o[k].worst_vector) !== view(x[k].worst_vector)) diffs.push(`${k}.W ${view(o[k].worst_vector)} ≠ ${view(x[k].worst_vector)}`);
          if (o[k] && o[k].worst_case_ids && view(o[k].worst_case_ids) !== view(x[k].worst_case_ids)) diffs.push(`${k}.worst_case_ids differ`);
        }
        if (o.evaluated !== x.evaluated) diffs.push(`evaluated ${o.evaluated} ≠ ${x.evaluated}`);
        if (o.feasible_count !== x.feasible_count) diffs.push(`feasible_count ${o.feasible_count} ≠ ${x.feasible_count}`);
        const pa = o.price_of_robustness_m, pb = x.price_of_robustness_m;
        if ((pa === null) !== (pb === null) || (pa !== null && Math.abs(pa - pb) > 1e-9)) diffs.push(`price ${pa} ≠ ${pb}`);
      }
    }
    if (f.check && f.check.status && o.status !== f.check.status) diffs.push(`status ${o.status}, ожидался ${f.check.status}`);
    if (f.check && f.check.same_plans_as && accepted[f.check.same_plans_as]) {
      const b = A.optimize(accepted[f.check.same_plans_as]);
      if (view([o.nominal && o.nominal.ids, o.robust && o.robust.ids]) !== view([b.nominal && b.nominal.ids, b.robust && b.robust.ids])) diffs.push(`планы отличаются от ${f.check.same_plans_as}`);
    }
    if (f.check && f.check.label_is_text) {
      const lbl = JSON.parse(textOf(f, snapR)).cases[0].label;
      if (!view(r.state).includes(JSON.stringify(lbl).slice(1, -1))) diffs.push("label изменён при импорте (ожидался текст как есть)");
    }
    const st2 = bad.concat(diffs);
    rec("R", f.id, `accept ${f.name}`, st2.length ? "FAIL" : "PASS", st2.length ? st2.slice(0, 6) : { status: o.status, robust: o.robust && o.robust.ids });
  }
}

// ================================================================ X: actual BUILD v1/v2 (always, when present)
let PL = null, X = null, F = null;
try { F = requireWeb("facts.js"); X = requireWeb("whatif.js"); PL = requireWeb("plan.js"); } catch (e) { PL = null; }
if (!PL) rec("X", "X0", "BUILD web/plan.js", "NOT_RUN", "plan.js отсутствует");
else {
  const ctxCache = {}, ctxFor = (c) => ctxCache[c] || (ctxCache[c] = PL.makeContext(D, c, F));
  const snapB = (city) => PL.sourceSnapshot(D, city, F);
  const typed = (fn) => { try { fn(); return { accepted: true }; } catch (e) { return { accepted: false, code: e && e.code, typed: !!(e && typeof e.code === "string") }; } };
  // X1/X2: every envelope text is refused by the v2 and v1 importers, with a typed code, nothing applied
  const x1 = [], x2 = [];
  for (const f of IDX.fixtures) {
    const text = textOf(f, (city) => snapB(city));
    const a = typed(() => PL.importPlanScenario(text, ctxFor, F)), b = typed(() => X.importScenario(text, D, F));
    if (a.accepted || !a.typed) x1.push(`${f.id}:${a.accepted ? "accepted" : "untyped"}`);
    if (b.accepted || !b.typed) x2.push(`${f.id}:${b.accepted ? "accepted" : "untyped"}`);
  }
  rec("X", "X1", "v2-импорт BUILD отклоняет все 59 текстов city-resilience-v1 типизированным кодом", x1.length ? "FAIL" : "PASS", x1.length ? x1 : undefined);
  rec("X", "X2", "v1-импорт BUILD отклоняет все 59 текстов city-resilience-v1 типизированным кодом", x2.length ? "FAIL" : "PASS", x2.length ? x2 : undefined);
  // X3: plan part of accepted envelopes = valid v2; v2 mean optimum on base = oracle "nominal"
  const x3 = [];
  let x3n = 0;
  for (const f of IDX.fixtures.filter((y) => y.expect === "accept" && !y.recipe)) {
    const env = JSON.parse(textOf(f, (city) => snapB(city)));
    let imp;
    try { imp = PL.importPlanScenario(JSON.stringify(env.plan), ctxFor, F); } catch (e) { x3.push(`${f.id}: plan отклонён v2 (${e.code})`); continue; }
    const r = PL.optimizePlans(ctxFor(env.plan.city_id), imp.scenario, { F });
    const x = EXP_OK && expOf(f.id);
    x3n++;
    if (!x) continue;
    if (r.status !== x.status) { x3.push(`${f.id}: status ${r.status} ≠ ${x.status}`); continue; }
    if (x.status !== "optimal") continue;
    const m = r.objectives.mean, nb = x.nominal.per_case[0];
    if (view(m.ids) !== view(x.nominal.ids)) x3.push(`${f.id}: v2 mean ${view(m.ids)} ≠ nominal ${view(x.nominal.ids)}`);
    else if (m.weighted_sum_mm !== nb.weighted_sum_mm || m.unknown_count !== nb.unknown_count || m.max_mm !== nb.max_mm || m.cost !== x.nominal.cost) x3.push(`${f.id}: base metrics differ`);
  }
  rec("X", "X3", `plan каждого допустимого конверта — валидный v2; mean-оптимум BUILD на base = nominal оракула (${x3n} задач)`,
    x3.length ? "FAIL" : EXP_OK ? "PASS" : "SKIP", x3.length ? x3 : EXP_OK ? undefined : "нет ожиданий оракула для этого data.js");
  // X4: plan-level negatives through the v2 importer (13 candidates is valid v2: resilience must refuse it itself)
  const planOnly = { N09: "accepted", N10: "too_many_candidates", N21: "forged_derived", N23: "wrong_version", N24: "foreign_snapshot", N25: "bad_weight", N26: "bad_cost" };
  const x4 = {};
  for (const [id, want] of Object.entries(planOnly)) {
    const env = JSON.parse(textOf(byId[id], (city) => snapB(city)));
    const a = typed(() => PL.importPlanScenario(JSON.stringify(env.plan), ctxFor, F));
    x4[id] = { want, got: a.accepted ? "accepted" : a.code };
  }
  const x4bad = Object.entries(x4).filter(([, v]) => v.want !== v.got);
  rec("X", "X4", "plan-уровень негативов в v2: 13 кандидатов v2 принимает (отказ — задача устойчивости), 17/подделка/v1/snapshot/вес/стоимость — отказ",
    x4bad.length ? "FAIL" : "PASS", x4bad.length ? Object.fromEntries(x4bad) : x4);
  // X5: sources immutable
  const c = ctxFor("shymkent");
  const frozen = Object.isFrozen(c) && Object.isFrozen(c.places) && c.places.every((p) => Object.isFrozen(p));
  let mutationBlocked = false;
  try { c.places[0].lon = 0; } catch (e) { mutationBlocked = true; }   // this file is strict mode: a frozen object throws
  rec("X", "X5", "исходные записи неизменны: CITY_EVIDENCE и data.js те же, контекст plan.js заморожен, запись в него отклоняется",
    D_HASH() === D_BEFORE && sha(fs.readFileSync(DATA_FILE)) === DATA_SHA_BEFORE && frozen && mutationBlocked ? "PASS" : "FAIL",
    { d_same: D_HASH() === D_BEFORE, file_same: sha(fs.readFileSync(DATA_FILE)) === DATA_SHA_BEFORE, frozen, mutationBlocked });
}
rec("X", "X6", "нет сетевых попыток", NET.length === 0 ? "PASS" : "FAIL", NET.length ? NET.slice(0, 5) : undefined);

const count = (s) => results.filter((r) => r.status === s).length;
const summary = { adapter: A === null ? `${path.basename(ADAPTER)} (модуль отсутствует)` : (A.name || path.basename(ADAPTER)), self_test: !!(A && A.selfTest),
  app_root: path.basename(APP), data_js_sha256: DATA_SHA_BEFORE, oracle: EXP_OK ? path.basename(EXPECTED) : "нет", total: results.length,
  pass: count("PASS"), fail: results.filter((r) => r.status === "FAIL").map((r) => `${r.group}/${r.id}`), advisory: results.filter((r) => r.status === "ADVISORY").map((r) => r.id),
  not_run: count("NOT_RUN"), skip: count("SKIP"), network_attempts: NET.length };
summary.verdict = summary.fail.length ? "FAIL" : "PASS";
console.log(JSON.stringify(summary));
if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 1) + "\n");
process.exit(summary.fail.length ? 1 : 0);
