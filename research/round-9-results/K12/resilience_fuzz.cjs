// K12 round 9, stage 3: bounded property/fuzz runner for city-resilience-v1 on the ACTUAL build (adapter to web/resilience.js),
// with the independent K12 oracle (oracle/resilience_oracle.py) and greedy shrinking to a minimal repro.
//   node resilience_fuzz.cjs --app-root <copy> [--adapter adapters/resilience_api_adapter.cjs] [--seed 21] [--cases 200]
//        [--max-ms 180000] [--no-oracle] [--python python3] [--unicode-rate 0.2] [--replay S:i] [--repro-dir repro_rs] [--out r.json]
// Exit: 0 PASS, 1 FAIL, 3 NOT_RUN (no web/resilience.js). All inputs SYNTHETIC except real source record IDs of the slice.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), os = require("os");
const { spawnSync } = require("child_process");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const HERE = __dirname;
const APP = path.resolve(opt("--app-root", ""));
const ADAPTER = path.resolve(opt("--adapter", path.join(HERE, "adapters", "resilience_api_adapter.cjs")));
const SEED = Number(opt("--seed", "21")) >>> 0, CASES = Number(opt("--cases", "200")), MAX_MS = Number(opt("--max-ms", "180000"));
const USE_ORACLE = !args.includes("--no-oracle"), PY = opt("--python", "python3"), UNI = Number(opt("--unicode-rate", "0.2"));
const REPLAY = opt("--replay", null), REPRO = path.resolve(opt("--repro-dir", path.join(HERE, "repro_rs"))), OUT = opt("--out");
if (!fs.existsSync(path.join(APP, "web", "data.js"))) { console.error("usage: node resilience_fuzz.cjs --app-root <dir>"); process.exit(2); }

const NET = [];
for (const [mod, fns] of [["http", ["request", "get"]], ["https", ["request", "get"]], ["net", ["connect", "createConnection"]]]) {
  const m = require(mod); for (const f of fns) m[f] = () => { NET.push(`${mod}.${f}`); throw new Error("K12 network guard"); };
}
const W = path.join(APP, "web");
const CTXV = {}; vm.createContext(CTXV); CTXV.window = CTXV;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), CTXV, { filename: f });
const A = require(ADAPTER)({ appRoot: APP, D: CTXV.CITY_EVIDENCE, EV: CTXV.CITY_OBS, ctx: CTXV, requireWeb: (n) => require(path.join(W, n)) });
if (!A || A.adapterError) { console.log(JSON.stringify({ verdict: "NOT_RUN", reason: A ? A.adapterError : "web/resilience.js отсутствует" })); process.exit(3); }

// ---------------------------------------------------------------- PRNG + generator of VALID envelopes
function mulberry32(a) { return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const caseSeed = (s, i) => (Math.imul(s ^ 0x9e3779b9, 2654435761) + Math.imul(i + 1, 0x85ebca6b)) >>> 0;
function R(seed) { const r = mulberry32(seed); const int = (lo, hi) => lo + Math.floor(r() * (hi - lo + 1));
  return { r, int, chance: (p) => r() < p, pick: (a) => a[int(0, a.length - 1)],
           shuffle: (a) => { const c = a.slice(); for (let i = c.length - 1; i > 0; i--) { const j = int(0, i); [c[i], c[j]] = [c[j], c[i]]; } return c; } }; }
// IDs valid by BUILD rules (NFC letters/digits/_ . -); astral and high-BMP letters order differently in UTF-16 and code points
const UNI_IDS = ["\u{1D538}", "ﬀ", "\u{1D49C}", "ｶ", "жағдай", "Ә1", "\u{10400}", "ﭐ", "z", "a.b", "a-b", "a_b"];
const round6 = (x) => Math.round(x * 1e6) / 1e6;
function gen(seed) {
  const g = R(seed);
  const city = g.pick(["shymkent", "astana"]), category = g.pick(["school", "outpatient_clinic"]);
  const ctx = A.ctx(city), bb = ctx.bbox, src = A.places(city, category);
  const placesXY = ctx.places.filter((p) => p.group === category);
  const xy = () => [round6(bb[0] + g.r() * (bb[2] - bb[0])), round6(bb[1] + g.r() * (bb[3] - bb[1]))];
  const uniq = (n, mk) => { const out = []; let k = 0; while (out.length < n) { const id = mk(k++); if (!out.includes(id)) out.push(id); } return out; };
  const np = g.chance(0.1) ? 25 : g.int(1, 8), nc = g.chance(0.1) ? 12 : g.chance(0.1) ? 0 : g.int(1, 9);
  const useUni = g.chance(UNI);
  const cid = uniq(nc, (k) => (useUni && k < UNI_IDS.length && g.chance(0.7) ? UNI_IDS[(k + g.int(0, 5)) % UNI_IDS.length] : `c${k}`));
  const pts = Array.from({ length: np }, (_, k) => { const [lon, lat] = xy(); return { id: `p${k}`, lon, lat, weight: g.chance(0.3) ? 1 : g.int(1, 100) }; });
  const cands = cid.map((id) => { let [lon, lat] = xy(); if (placesXY.length && g.chance(0.15)) { const s = g.pick(placesXY); lon = s.lon; lat = s.lat; }
    return { id, lon, lat, category, kind: "hypothetical", cost: g.chance(0.25) ? 100000 : g.int(1, 1000000) }; });
  if (nc > 1 && g.chance(0.35)) { cands[1].lon = cands[0].lon; cands[1].lat = cands[0].lat; cands[1].cost = cands[0].cost; }   // exact tie
  const req = g.chance(0.25) ? g.shuffle(cid).slice(0, g.int(0, Math.min(2, nc))) : [];
  const exc = g.chance(0.25) ? g.shuffle(cid.filter((x) => !req.includes(x))).slice(0, g.int(0, Math.min(2, nc))) : [];
  const nCases = g.int(1, 7);
  const cases = [];
  for (let k = 0; k < nCases; k++) {
    const dis = k > 0 && g.chance(0.15) ? cases[g.int(0, k - 1)].disabled_source_ids.slice()         // duplicate exclusion set
      : g.chance(0.1) ? src.slice() : g.shuffle(src).slice(0, g.int(1, Math.max(1, Math.min(src.length, 4))));
    cases.push({ id: useUni && g.chance(0.4) ? `${UNI_IDS[k % UNI_IDS.length]}${k}` : `k${k}`, label: g.pick(["Случай", "Жағдай", "<b>case</b> & 1", "😀 тест"]) + ` ${k}`, disabled_source_ids: dis });
  }
  const sumSome = g.shuffle(cands).slice(0, g.int(0, Math.min(3, nc))).reduce((s, c) => s + c.cost, 0);
  return { schema_version: "city-resilience-v1",
    plan: { schema_version: "city-plan-v2", city_id: city, source_snapshot: A.snapshot(city), category, control_points: pts, candidates: cands,
      budget: Math.min(1000000, g.pick([0, g.int(0, 1000000), sumSome, 1000000])), max_selected: g.int(0, 5), coverage_radius_m: g.pick([100, 500, 5000, g.int(100, 5000)]),
      required_ids: req, excluded_ids: exc, selected_ids: g.shuffle(cid).slice(0, g.int(0, Math.min(5, nc))) }, cases };
}

// ---------------------------------------------------------------- properties
const J = (x) => JSON.stringify(x);
const clone = (x) => JSON.parse(J(x));
const lex = (a, b) => { const k = (v) => [v.unknown_count, v.weighted_sum_mm, v.max_mm === null ? Infinity : v.max_mm]; const x = k(a), y = k(b);
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1; return 0; };
const opt0 = (e) => A.optimize(A.ctx(e.plan.city_id), e);
const plans = (o) => [o.status, o.nominal && o.nominal.selected_ids, o.robust && o.robust.selected_ids, o.robust && o.robust.worst_vector];
const PROPS = {
  accepted(e) { try { A.validate(e, A.ctx(e.plan.city_id)); return null; } catch (x) { return `валидный конверт отклонён: ${x.code || x.message}`; } },
  input_not_mutated(e) { const before = J(e); opt0(e); A.evaluate(A.ctx(e.plan.city_id), e, e.plan.selected_ids); return J(e) === before ? null : "вызов изменил переданный объект"; },
  permutation_invariant(e, g) { const p = clone(e); p.cases = g.shuffle(p.cases).map((c) => ({ ...c, disabled_source_ids: g.shuffle(c.disabled_source_ids) }));
    p.plan.control_points = g.shuffle(p.plan.control_points); p.plan.candidates = g.shuffle(p.plan.candidates);
    const a = opt0(e), b = opt0(p);
    return J([plans(a), a.robust && a.robust.worst_case_ids]) === J([plans(b), b.robust && b.robust.worst_case_ids]) ? null : "результат зависит от порядка случаев/массивов"; },
  duplicate_case_no_effect(e, g) { if (e.cases.length >= 7) return null; const p = clone(e); const c = g.pick(p.cases); p.cases.push({ ...clone(c), id: `dup_${c.id}`.slice(0, 64) });
    const a = opt0(e), b = opt0(p); return J(plans(a)) === J(plans(b)) ? null : "дубль случая изменил планы"; },
  robust_vs_nominal(e) { const o = opt0(e); if (o.status !== "optimal") return null;
    if (lex(o.robust.worst_vector, o.nominal.worst_vector) > 0) return "W устойчивого хуже W обычного";
    if (lex(o.nominal.per_case[0].loss, o.robust.per_case[0].loss) > 0) return "L_base обычного хуже L_base устойчивого";
    if (o.price_of_robustness_m !== null && o.price_of_robustness_m < -1e-9) return `цена устойчивости ${o.price_of_robustness_m} < 0`;
    if (o.same_plan && o.price_of_robustness_m !== null && Math.abs(o.price_of_robustness_m) > 1e-12) return "совпавшие планы, но цена ≠ 0";
    return null; },
  worst_is_max_over_cases(e) { const o = opt0(e); if (o.status !== "optimal") return null;
    for (const k of ["nominal", "robust"]) { const p = o[k]; let w = null; for (const r of p.per_case) if (!w || lex(r.loss, w) > 0) w = r.loss;
      if (J(w) !== J(p.worst_vector)) return `${k}: worst_vector ≠ max по случаям`;
      const ids = p.per_case.filter((r) => lex(r.loss, w) === 0).map((r) => r.case_id).sort();
      if (J(ids) !== J(p.worst_case_ids.slice().sort())) return `${k}: worst_case_ids неполны`; }
    return null; },
  evaluate_matches_optimize(e) { const o = opt0(e); if (o.status !== "optimal") return null;
    const ev = A.evaluate(A.ctx(e.plan.city_id), e, o.robust.selected_ids);
    return J([ev.worst_vector, ev.worst_case_ids]) === J([o.robust.worst_vector, o.robust.worst_case_ids]) ? null : "evaluateResilience(robust) ≠ optimize.robust"; },
  more_cases_never_better(e, g) { if (e.cases.length >= 7) return null; const p = clone(e);
    const src = A.places(e.plan.city_id, e.plan.category); p.cases.push({ id: "extra", label: "extra", disabled_source_ids: g.shuffle(src).slice(0, 1) });
    if (e.cases.some((c) => c.id === "extra")) return null;
    const a = opt0(e), b = opt0(p); if (a.status !== "optimal") return null;
    return lex(b.robust.worst_vector, a.robust.worst_vector) >= 0 ? null : "новый случай уменьшил W устойчивого оптимума"; },
  counts_and_strict_json(e) { const o = opt0(e); const t = J(o);
    if (/NaN|Infinity/.test(t)) return "NaN/Infinity в выводе";
    if (o.status === "optimal" && !(o.feasible_count <= o.evaluated && o.evaluated === o.total_subsets)) return "feasible/evaluated/total несогласованы";
    return null; },
  cancel_not_optimal(e) { const c = A.ctx(e.plan.city_id), s = A.createSearch(c, e); if (s.total < 4) return null; s.step(1); s.cancel(); s.step(1 << 12);
    const r = s.result(); return r.status === "cancelled" && !r.robust ? null : `после cancel: ${r.status}`; },
};

// ---------------------------------------------------------------- invalid mutations: typed refusal, input untouched
const MUT = [
  ["candidate_as_source", (e) => { if (!e.plan.candidates.length) return false; e.cases[0].disabled_source_ids = [e.plan.candidates[0].id]; }],
  ["fake_source", (e) => { e.cases[0].disabled_source_ids = ["ffffffff-0000-0000-0000-000000000000"]; }],
  ["reserved_base", (e) => { e.cases[0].id = "base"; }],
  ["duplicate_case_id", (e) => { if (e.cases.length < 2) return false; e.cases[1].id = e.cases[0].id; }],
  ["eight_cases", (e) => { while (e.cases.length < 8) e.cases.push({ ...clone(e.cases[0]), id: `x${e.cases.length}` }); }],
  ["thirteen_candidates", (e, g) => { const c = e.plan.candidates; while (c.length < 13) c.push({ ...(c[0] || { lon: e.plan.control_points[0].lon, lat: e.plan.control_points[0].lat, category: e.plan.category, kind: "hypothetical", cost: 1 }), id: `m${c.length}_${g.int(0, 9999)}` }); }],
  ["empty_exclusion", (e) => { e.cases[0].disabled_source_ids = []; }],
  ["dup_source", (e) => { e.cases[0].disabled_source_ids = [e.cases[0].disabled_source_ids[0], e.cases[0].disabled_source_ids[0]]; }],
  ["label_too_long", (e) => { e.cases[0].label = "Ж".repeat(121); }],
  ["label_control", (e) => { e.cases[0].label = "a\u0007b"; }],
  ["case_extra_field", (e) => { e.cases[0].probability = 0.5; }],
  ["envelope_derived", (e) => { e.derived_results = { robust: [] }; }],
  ["plan_derived", (e) => { e.plan.derived_results = { note: "x" }; }],
  ["other_category_source", (e) => { const o = e.plan.category === "school" ? "outpatient_clinic" : "school"; e.cases[0].disabled_source_ids = [A.places(e.plan.city_id, o)[0]]; }],
  ["wrong_schema", (e) => { e.schema_version = "city-plan-v2"; }],
  ["foreign_snapshot", (e) => { e.plan.source_snapshot = A.snapshot(e.plan.city_id === "astana" ? "shymkent" : "astana"); }],
];
function mutationRefused(e, g) {
  const [name, fn] = g.pick(MUT); const m = clone(e); if (fn(m, g) === false) return null;
  const before = J(m); let code = null, ok = false;
  try { A.optimize(A.ctx(m.plan.city_id), m); ok = true; } catch (x) { code = x && x.code; }
  if (ok) return { name, msg: "недопустимый конверт принят" };
  if (typeof code !== "string") return { name, msg: "нетипизированное исключение" };
  if (J(m) !== before) return { name, msg: "отказ изменил переданный объект" };
  return { name, msg: null, code };
}

// ---------------------------------------------------------------- shrink (keeps the envelope valid)
function shrinkCands(e) {
  const out = [], C = (f) => { const x = clone(e); f(x); return x; };
  for (let k = 0; k < e.cases.length && e.cases.length > 1; k++) out.push(C((x) => x.cases.splice(k, 1)));
  for (let k = 0; k < e.plan.control_points.length && e.plan.control_points.length > 1; k++) out.push(C((x) => x.plan.control_points.splice(k, 1)));
  for (let k = 0; k < e.plan.candidates.length; k++) out.push(C((x) => { const id = x.plan.candidates[k].id; x.plan.candidates.splice(k, 1);
    for (const f of ["required_ids", "excluded_ids", "selected_ids"]) x.plan[f] = x.plan[f].filter((y) => y !== id); }));
  for (let k = 0; k < e.cases.length; k++) if (e.cases[k].disabled_source_ids.length > 1) out.push(C((x) => { x.cases[k].disabled_source_ids = x.cases[k].disabled_source_ids.slice(0, 1); }));
  for (const f of ["required_ids", "excluded_ids", "selected_ids"]) if (e.plan[f].length) out.push(C((x) => { x.plan[f] = []; }));
  if (e.plan.control_points.some((p) => p.weight !== 1)) out.push(C((x) => x.plan.control_points.forEach((p) => { p.weight = 1; })));
  return out;
}
function shrink(e, fails, budget = 300) {
  let cur = e, steps = 0;
  for (let improved = true; improved && steps < budget;) { improved = false;
    for (const c of shrinkCands(cur)) { steps++; let valid = true; try { A.validate(c, A.ctx(c.plan.city_id)); } catch (x) { valid = false; }
      if (valid && fails(c)) { cur = c; improved = true; break; } if (steps >= budget) break; } }
  return { env: cur, steps };
}
function saveRepro(kind, name, tag, env, msg) {
  fs.mkdirSync(REPRO, { recursive: true });
  const f = path.join(REPRO, `${kind}_${name}_${tag.replace(":", "_")}.json`);
  fs.writeFileSync(f, JSON.stringify({ kind, property: name, replay: `--seed ${tag.split(":")[0]} --replay ${tag}`, message: msg, note: "SYNTHETIC minimal repro (resilience_fuzz.cjs)", envelope: env }, null, 1) + "\n");
  return path.relative(HERE, f);
}

// ---------------------------------------------------------------- oracle
const forOracle = (e) => { const x = clone(e); x.plan.source_snapshot = "__SNAPSHOT__"; return x; };
function runOracle(list) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "k12rsfz_")), inp = path.join(dir, "p.json"), outp = path.join(dir, "o.json");
  fs.writeFileSync(inp, J({ problems: list.map(([name, e]) => ({ name, envelope: forOracle(e) })) }));
  const r = spawnSync(PY, [path.join(HERE, "oracle", "resilience_oracle.py"), "--app-root", APP, "--problems", inp, "--out", outp], { encoding: "utf8", timeout: 900000 });
  const res = r.status === 0 ? JSON.parse(fs.readFileSync(outp, "utf8")).results : null;
  fs.rmSync(dir, { recursive: true, force: true });
  if (!res) throw new Error("oracle failed: " + String(r.stderr || r.error).slice(0, 300));
  return Object.fromEntries(res.map((x) => [x.name, x]));
}
const vec = (v) => (v ? [v.unknown_count, v.weighted_sum_mm, v.max_mm] : null);
function oracleDiff(o, x) {
  if (o.status !== x.status) return `status ${o.status} ≠ ${x.status}`;
  if (x.status !== "optimal") return null;
  if (o.evaluated !== x.evaluated || o.feasible_count !== x.feasible_count) return `evaluated/feasible ${o.evaluated}/${o.feasible_count} ≠ ${x.evaluated}/${x.feasible_count}`;
  for (const k of ["nominal", "robust"]) {
    if (J(o[k].selected_ids) !== J(x[k].ids)) return `${k} ${J(o[k].selected_ids)} ≠ oracle ${J(x[k].ids)}`;
    if (J(vec(o[k].worst_vector)) !== J(x[k].worst_vector)) return `${k}.W ${J(vec(o[k].worst_vector))} ≠ ${J(x[k].worst_vector)}`;
    if (J(o[k].worst_case_ids) !== J(x[k].worst_case_ids)) return `${k}.worst_case_ids ${J(o[k].worst_case_ids)} ≠ ${J(x[k].worst_case_ids)}`;
  }
  const a = o.price_of_robustness_m, b = x.price_of_robustness_m;
  if ((a === null) !== (b === null) || (a !== null && Math.abs(a - b) > 1e-9)) return `price ${a} ≠ ${b}`;
  return null;
}

// ---------------------------------------------------------------- main
const t0 = Date.now(), failures = [], seen = new Set(), gen0 = {}, mutSeen = {};
const first = (k) => !seen.has(k) && !!seen.add(k);
const idx = REPLAY ? [Number(REPLAY.split(":")[1])] : Array.from({ length: CASES }, (_, i) => i);
const forOr = [];
let ran = 0, checks = 0;
for (const i of idx) {
  if (Date.now() - t0 > MAX_MS) break;
  const cs = caseSeed(SEED, i), tag = `${SEED}:${i}`, e = gen(cs);
  ran++;
  const inc = (k) => { gen0[k] = (gen0[k] || 0) + 1; };
  inc(`city:${e.plan.city_id}/${e.plan.category}`); inc(`candidates:${e.plan.candidates.length >= 10 ? "10-12" : e.plan.candidates.length >= 4 ? "4-9" : "0-3"}`); inc(`cases:${e.cases.length}`);
  if (e.plan.candidates.some((c) => /[^\x00-\x7f]/.test(c.id))) inc("unicode_candidate_ids");
  for (const [name, P] of Object.entries(PROPS)) {
    checks++;
    let msg; try { msg = P(e, R(cs ^ 0x77)); } catch (x) { msg = `exception: ${x.code || ""} ${x.message}`; }
    if (!msg) continue;
    if (first(`property/${name}`)) {
      const fails = (s) => { try { return !!P(s, R(cs ^ 0x77)); } catch (x) { return true; } };
      const sh = shrink(e, fails);
      failures.push({ kind: "property", property: name, case: tag, message: msg, shrink_steps: sh.steps,
        minimal: { points: sh.env.plan.control_points.length, candidates: sh.env.plan.candidates.length, cases: sh.env.cases.length }, repro: saveRepro("property", name, tag, sh.env, msg) });
    } else failures.push({ kind: "property", property: name, case: tag, message: msg });
  }
  try { const o = opt0(e); inc(`status:${o.status}`); if (o.status === "optimal" && !o.same_plan) inc("robust_differs"); } catch (x) { inc("optimize_error"); }
  forOr.push([tag, e]);
  const m = mutationRefused(e, R(cs ^ 0x99));
  if (m) { mutSeen[m.name] = (mutSeen[m.name] || 0) + 1;
    if (m.msg) failures.push({ kind: "mutation", property: m.name, case: tag, message: m.msg, ...(first(`mutation/${m.name}`) ? { repro: saveRepro("mutation", m.name, tag, e, m.msg) } : {}) }); }
}
let oracleNote = "skipped (--no-oracle)", compared = 0;
if (USE_ORACLE && forOr.length) {
  const ex = runOracle(forOr);
  for (const [tag, e] of forOr) {
    compared++;
    const d = oracleDiff(opt0(e), ex[tag]);
    if (!d) continue;
    if (first("oracle")) {
      const fails = (s) => { try { return !!oracleDiff(opt0(s), runOracle([["x", s]]).x); } catch (x) { return false; } };
      const sh = shrink(e, fails, 60);
      failures.push({ kind: "oracle", property: "equals_k12_oracle", case: tag, message: d, shrink_steps: sh.steps,
        minimal: { points: sh.env.plan.control_points.length, candidates: sh.env.plan.candidates.length, cases: sh.env.cases.length }, repro: saveRepro("oracle", "equals_k12_oracle", tag, sh.env, d) });
    } else failures.push({ kind: "oracle", property: "equals_k12_oracle", case: tag, message: d });
  }
  oracleNote = `compared ${compared} envelopes with oracle/resilience_oracle.py`;
}
const byProp = {}; for (const f of failures) byProp[`${f.kind}/${f.property}`] = (byProp[`${f.kind}/${f.property}`] || 0) + 1;
const summary = { adapter: A.name, app_root: path.basename(APP), seed: SEED, cases_requested: REPLAY ? 1 : CASES, cases_run: ran,
  truncated_by_time_budget: !REPLAY && ran < CASES, property_checks: checks, oracle: oracleNote, generator_coverage: Object.fromEntries(Object.entries(gen0).sort()),
  mutation_kinds: mutSeen, failures: failures.length, failures_by_property: byProp, network_attempts: NET.length, elapsed_ms: Date.now() - t0 };
summary.verdict = failures.length || NET.length ? "FAIL" : "PASS";
for (const f of failures.filter((x) => x.repro)) console.log(`FAIL ${f.kind}/${f.property} case ${f.case}: ${f.message} → ${f.repro}${f.minimal ? ` (minimal: ${J(f.minimal)}, ${f.shrink_steps} steps)` : ""}`);
console.log(J(summary));
if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, failures: failures.filter((x) => x.repro).concat(failures.filter((x) => !x.repro).slice(0, 30)) }, null, 1) + "\n");
process.exit(summary.verdict === "PASS" ? 0 : 1);
