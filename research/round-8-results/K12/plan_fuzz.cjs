// K12 round 8, stage 3: reusable property/fuzz runner for a city-plan-v2 implementation behind an adapter.
// Bounded (seed, case count, wall-clock budget), deterministic, strict PASS/FAIL, greedy shrinking to a minimal repro.
// Differential check against the independent Python oracle (oracle/plan_v2_oracle.py) in one batch.
// All generated scenarios are SYNTHETIC (random points/candidates/costs inside the slice bbox) — not city statistics.
//
//   node plan_fuzz.cjs --app-root <dir> [--adapter adapters/reference_v2_adapter.cjs] [--seed 12] [--cases 200]
//        [--max-ms 120000] [--python python3] [--no-oracle] [--replay <seed>:<index>] [--repro-dir repro] [--out r.json]
//        [--bench]
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), os = require("os");
const { spawnSync } = require("child_process");

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const HERE = __dirname;
const APP = path.resolve(opt("--app-root", ""));
const ADAPTER = path.resolve(opt("--adapter", path.join(HERE, "adapters", "reference_v2_adapter.cjs")));
const SEED = Number(opt("--seed", "12")) >>> 0;
const CASES = Math.max(1, Number(opt("--cases", "200")));
const MAX_MS = Number(opt("--max-ms", "120000"));
const PY = opt("--python", "python3");
const USE_ORACLE = !args.includes("--no-oracle");
const REPLAY = opt("--replay", null);
const REPRO = path.resolve(opt("--repro-dir", path.join(HERE, "repro")));
const OUT = opt("--out");
const BENCH = args.includes("--bench");
if (!fs.existsSync(path.join(APP, "web", "data.js"))) { console.error("usage: node plan_fuzz.cjs --app-root <dir> [...]"); process.exit(2); }

const WEB = path.join(APP, "web");
const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(WEB, f), "utf8"), ctx, { filename: f });
const D = ctx.CITY_EVIDENCE;
const A = require(ADAPTER)({ appRoot: APP, D, EV: ctx.CITY_OBS, ctx, requireWeb: (n) => require(path.join(WEB, n)) });

// ---------------------------------------------------------------- deterministic PRNG
function mulberry32(a) { return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const caseSeed = (seed, i) => (Math.imul(seed ^ 0x9e3779b9, 2654435761) + Math.imul(i + 1, 0x85ebca6b)) >>> 0;
function R(seed) {
  const r = mulberry32(seed);
  const int = (lo, hi) => lo + Math.floor(r() * (hi - lo + 1));
  return { r, int, chance: (p) => r() < p, pick: (a) => a[int(0, a.length - 1)],
           sample: (a, k) => { const c = a.slice(); for (let i = c.length - 1; i > 0; i--) { const j = int(0, i); [c[i], c[j]] = [c[j], c[i]]; } return c.slice(0, k); },
           shuffle: (a) => { const c = a.slice(); for (let i = c.length - 1; i > 0; i--) { const j = int(0, i); [c[i], c[j]] = [c[j], c[i]]; } return c; } };
}

// ---------------------------------------------------------------- generator of VALID scenarios
const round6 = (x) => Math.round(x * 1e6) / 1e6;
function genScenario(seed) {
  const g = R(seed);
  const city = g.pick(["shymkent", "astana"]), category = g.pick(["school", "outpatient_clinic"]);
  const bb = D.cities[city].bbox;
  const srcs = D.cities[city].places.filter((p) => p.group === category);
  const xy = () => [round6(bb[0] + g.r() * (bb[2] - bb[0])), round6(bb[1] + g.r() * (bb[3] - bb[1]))];
  const np = g.chance(0.15) ? 25 : g.int(1, 8);
  const nc = g.chance(0.08) ? 16 : g.chance(0.1) ? 0 : g.chance(0.12) ? g.int(11, 15) : g.int(1, 10);
  const pts = Array.from({ length: np }, (_, k) => { const [lon, lat] = xy(); return { id: `p${k}`, lon, lat, weight: g.chance(0.3) ? 1 : g.int(1, 100) }; });
  const cands = Array.from({ length: nc }, (_, k) => {
    let [lon, lat] = xy();
    if (srcs.length && g.chance(0.15)) { const s = g.pick(srcs); lon = s.lon; lat = s.lat; }                  // tie with a source record
    return { id: `c${k}`, lon, lat, category, kind: "hypothetical", cost: g.chance(0.2) ? 100000 : g.int(1, 1000000) };
  });
  if (nc > 1 && g.chance(0.15)) { cands[1].lon = cands[0].lon; cands[1].lat = cands[0].lat; }                     // tie between candidates
  if (nc && g.chance(0.1)) { pts[0].lon = cands[0].lon; pts[0].lat = cands[0].lat; }                              // zero distance
  const ids = cands.map((c) => c.id);
  const required = g.sample(ids, g.chance(0.3) ? g.int(0, Math.min(2, nc)) : 0);
  const excluded = g.sample(ids.filter((id) => !required.includes(id)), g.chance(0.3) ? g.int(0, Math.min(2, nc)) : 0);
  const sumSome = g.sample(cands, g.int(0, Math.min(3, nc))).reduce((s, c) => s + c.cost, 0);
  const budget = Math.min(1000000, g.pick([0, g.int(0, 1000000), sumSome, 1000000]));
  return { schema_version: "city-plan-v2", city_id: city, source_snapshot: A.snapshot(city), category, control_points: pts, candidates: cands,
           budget, max_selected: g.int(0, 5), coverage_radius_m: g.pick([100, 500, g.int(100, 5000), 5000]),
           required_ids: required, excluded_ids: excluded, selected_ids: g.sample(ids, g.int(0, Math.min(5, nc))) };
}

// ---------------------------------------------------------------- properties of VALID scenarios
const view = (x) => JSON.stringify(x);
const imp = (sc) => A.importScenario(JSON.stringify(sc), A.initialState());
const lexLE = (a, b) => { for (let k = 0; k < a.length; k++) { if (a[k] < b[k]) return true; if (a[k] > b[k]) return false; } return true; };
const meanKey = (m) => [m.unknown_count, m.weighted_sum_mm];
const PROPS = {
  accepted(sc) { const r = imp(sc); return r.ok ? null : `valid scenario rejected: ${r.code}`; },
  permutation_invariant(sc, g) {
    const p = { ...sc, control_points: g.shuffle(sc.control_points), candidates: g.shuffle(sc.candidates),
                required_ids: g.shuffle(sc.required_ids), excluded_ids: g.shuffle(sc.excluded_ids), selected_ids: g.shuffle(sc.selected_ids) };
    const a = imp(sc), b = imp(p);
    if (!a.ok || !b.ok) return "import failed";
    if (A.problemDigest && A.problemDigest(a.state) !== A.problemDigest(b.state)) return "problem_digest depends on array order";
    const oa = A.optimize(a.state), ob = A.optimize(b.state);
    return view([oa.objectives, oa.pareto]) === view([ob.objectives, ob.pareto]) ? null : "plans depend on array order";
  },
  winners_feasible_and_consistent(sc) {
    const r = imp(sc); const o = A.optimize(r.state);
    if (!["optimal", "infeasible"].includes(o.status)) return `status ${o.status}`;
    for (const [k, w] of Object.entries(o.objectives)) {
      if (!w) { if (o.status === "optimal") return `${k} missing though optimal`; continue; }
      if (w.selected_ids.length > sc.max_selected) return `${k} exceeds max_selected`;
      if (sc.excluded_ids.some((id) => w.selected_ids.includes(id))) return `${k} includes excluded`;
      if (sc.required_ids.some((id) => !w.selected_ids.includes(id))) return `${k} misses required`;
      const cost = sc.candidates.filter((c) => w.selected_ids.includes(c.id)).reduce((s, c) => s + c.cost, 0);
      if (cost > sc.budget || cost !== w.metrics.cost) return `${k} cost ${w.metrics.cost} (recomputed ${cost}, budget ${sc.budget})`;
    }
    return null;
  },
  pareto_valid(sc) {
    const o = A.optimize(imp(sc).state);
    const P = o.pareto;
    for (let i = 0; i < P.length; i++) for (let j = 0; j < P.length; j++) {
      if (i !== j && P[j].cost <= P[i].cost && P[j].weighted_sum_mm <= P[i].weighted_sum_mm) return "pareto member dominated or duplicated";
    }
    for (let i = 1; i < P.length; i++) if (!(P[i].cost > P[i - 1].cost && P[i].weighted_sum_mm < P[i - 1].weighted_sum_mm)) return "pareto not strictly ordered";
    return null;
  },
  budget_monotone(sc) {
    const s = A.optimize(imp(sc).state).sensitivity;
    if (!s) return null;
    for (let i = 1; i < s.length; i++) {
      const a = s[i - 1], b = s[i];
      if (a.mean && !b.mean) return `budget ${b.budget} lost a plan that ${a.budget} had`;
      if (a.mean && b.mean && !lexLE([b.mean.unknown_count, b.mean.weighted_sum_mm], [a.mean.unknown_count, a.mean.weighted_sum_mm]))
        return `larger budget ${b.budget} gave a worse mean objective`;
    }
    return null;
  },
  coverage_objective_maximal(sc) {
    const o = A.optimize(imp(sc).state);
    if (o.status !== "optimal") return null;
    const cov = o.objectives.coverage.metrics.covered_weight;
    return ["mean", "minimax"].every((k) => o.objectives[k].metrics.covered_weight <= cov) ? null : "coverage winner covers less than another winner";
  },
  more_candidates_never_worse(sc) {
    const free = sc.candidates.filter((c) => !sc.required_ids.includes(c.id));
    if (!free.length) return null;
    const drop = free[free.length - 1].id;
    const less = { ...sc, candidates: sc.candidates.filter((c) => c.id !== drop), excluded_ids: sc.excluded_ids.filter((x) => x !== drop),
                   selected_ids: sc.selected_ids.filter((x) => x !== drop) };
    const a = A.optimize(imp(sc).state), b = A.optimize(imp(less).state);
    if (!a.objectives.mean || !b.objectives.mean) return null;
    return lexLE(meanKey(a.objectives.mean.metrics), meanKey(b.objectives.mean.metrics)) ? null : `removing ${drop} improved the optimum`;
  },
  rows_consistent(sc) {
    if (!A.evaluate) return null;
    const ev = A.evaluate(imp(sc).state);
    for (const row of ev.rows) {
      if (row.before_mm !== null && row.after_mm !== null && (row.after_mm > row.before_mm || row.delta_mm !== row.before_mm - row.after_mm)) return `row ${row.id} after/delta`;
      if (row.before_mm === null && row.delta_mm !== null) return `row ${row.id}: delta without baseline`;
    }
    return null;
  },
  strict_json_output(sc) {
    const o = A.optimize(imp(sc).state);
    const t = JSON.stringify(o);
    return /NaN|Infinity/.test(t) || view(JSON.parse(t)) !== t ? "output is not strict JSON" : null;
  },
};

// ---------------------------------------------------------------- mutations: INVALID scenarios must be refused atomically
const MUT = [
  ["weight_out_of_range", (s, g) => { s.control_points[g.int(0, s.control_points.length - 1)].weight = g.pick([0, 101, 1.5, -3, "5", null, true]); }],
  ["cost_out_of_range", (s, g) => { if (!s.candidates.length) return false; s.candidates[g.int(0, s.candidates.length - 1)].cost = g.pick([0, 1000001, 2.5, -1, "10", null]); }],
  ["budget_out_of_range", (s, g) => { s.budget = g.pick([-1, 1000001, 0.5, "1", null]); }],
  ["max_selected_out_of_range", (s, g) => { s.max_selected = g.pick([6, -1, 1.5, "2", true]); }],
  ["radius_out_of_range", (s, g) => { s.coverage_radius_m = g.pick([99, 5001, 100.5, 0]); }],
  ["unknown_id", (s, g) => { s[g.pick(["required_ids", "excluded_ids", "selected_ids"])].push("zz_unknown"); }],
  ["required_excluded_conflict", (s) => { if (!s.candidates.length) return false; const id = s.candidates[0].id; s.required_ids = [id]; s.excluded_ids = [id]; s.selected_ids = s.selected_ids.filter((x) => x !== id); }],
  ["duplicate_point_id", (s) => { s.control_points.push({ ...s.control_points[0] }); if (s.control_points.length > 25) s.control_points.splice(1, 1); }],
  ["duplicate_candidate_id", (s) => { if (!s.candidates.length) return false; s.candidates.push({ ...s.candidates[0], lon: s.candidates[0].lon }); if (s.candidates.length > 16) s.candidates.splice(1, 1); }],
  ["outside_bbox", (s, g) => { const p = g.pick(s.control_points); p.lat = p.lat + 0.5; }],
  ["coord_string", (s) => { s.control_points[0].lon = String(s.control_points[0].lon); }],
  ["extra_field", (s, g) => { if (g.chance(0.5) && s.candidates.length) s.candidates[0].capacity = 900; else s.population = 1000; }],
  ["too_many_points", (s) => { while (s.control_points.length < 26) s.control_points.push({ ...s.control_points[0], id: `x${s.control_points.length}` }); }],
  ["kind_observed", (s) => { if (!s.candidates.length) return false; s.candidates[0].kind = "observed"; }],
  ["foreign_snapshot", (s) => { s.source_snapshot = A.snapshot(s.city_id === "astana" ? "shymkent" : "astana"); }],
];
const TEXT_MUT = [
  ["duplicate_key", (t) => t.replace('{"schema_version"', '{"budget":0,"schema_version"')],
  ["nan_token", (t) => t.replace(/"weight":\d+/, '"weight":NaN')],
  ["overflow_1e999", (t) => t.replace(/"budget":\d+/, '"budget":1e999')],
  ["truncated", (t) => t.slice(0, Math.max(1, t.length - 7))],
  ["deep_derived", (t, g) => { const n = g.int(40, 5000); return t.replace('{"schema_version"', '{"derived_results":' + "[".repeat(n) + "]".repeat(n) + ',"schema_version"'); }],
  ["oversize", (t) => t.slice(0, -1) + " ".repeat(Math.max(0, 262145 - Buffer.byteLength(t, "utf8"))) + "}"],
];
function mutate(sc, g) {
  for (let tries = 0; tries < 10; tries++) {
    if (g.chance(0.35)) {
      const [name, fn] = g.pick(TEXT_MUT);
      const t = fn(JSON.stringify(sc), g);
      if (t !== JSON.stringify(sc)) return { name, text: t };
    } else {
      const [name, fn] = g.pick(MUT);
      const s = JSON.parse(JSON.stringify(sc));
      if (fn(s, g) !== false) return { name, text: JSON.stringify(s) };
    }
  }
  return null;
}
function invalidRefusedAtomically(text) {
  const base = imp(genScenario(1)).state;
  const before = view(base), passed = JSON.parse(before);
  let r, threw = null;
  try { r = A.importScenario(text, passed); } catch (e) { threw = e.message; }
  if (threw) return `exception: ${threw.slice(0, 120)}`;
  if (r.ok) return "invalid scenario accepted";
  if (view(r.state) !== before || view(passed) !== before) return "state changed on refusal";
  return null;
}

// ---------------------------------------------------------------- shrinking (greedy, keeps the scenario valid)
function shrinkCandidates(sc) {
  const out = [];
  const drop = (field, k) => { const s = JSON.parse(JSON.stringify(sc)); s[field].splice(k, 1); return s; };
  for (let k = 0; k < sc.control_points.length && sc.control_points.length > 1; k++) out.push(drop("control_points", k));
  for (let k = 0; k < sc.candidates.length; k++) {
    const s = drop("candidates", k), id = sc.candidates[k].id;
    for (const f of ["required_ids", "excluded_ids", "selected_ids"]) s[f] = s[f].filter((x) => x !== id);
    out.push(s);
  }
  for (const f of ["required_ids", "excluded_ids", "selected_ids"]) if (sc[f].length) out.push({ ...JSON.parse(JSON.stringify(sc)), [f]: [] });
  if (sc.control_points.some((p) => p.weight !== 1)) { const s = JSON.parse(JSON.stringify(sc)); s.control_points.forEach((p) => { p.weight = 1; }); out.push(s); }
  if (sc.max_selected > sc.required_ids.length) out.push({ ...JSON.parse(JSON.stringify(sc)), max_selected: sc.max_selected - 1 });
  return out;
}
function shrink(sc, fails, budgetSteps = 400) {
  let cur = sc, steps = 0;
  for (let improved = true; improved && steps < budgetSteps;) {
    improved = false;
    for (const cand of shrinkCandidates(cur)) {
      steps++;
      if (imp(cand).ok && fails(cand)) { cur = cand; improved = true; break; }
      if (steps >= budgetSteps) break;
    }
  }
  return { scenario: cur, steps };
}
function saveRepro(kind, name, seedIdx, sc, msg) {
  fs.mkdirSync(REPRO, { recursive: true });
  const file = path.join(REPRO, `${kind}_${name}_${seedIdx.replace(":", "_")}.json`);
  fs.writeFileSync(file, JSON.stringify({ kind, property: name, replay: `--seed ${seedIdx.split(":")[0]} --replay ${seedIdx}`, message: msg,
    note: "SYNTHETIC minimal repro produced by plan_fuzz.cjs", scenario: sc }, null, 1) + "\n");
  return path.relative(HERE, file);
}

// ---------------------------------------------------------------- oracle (batch)
function runOracle(problems) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "k12fuzz_"));
  const inp = path.join(dir, "p.json"), outp = path.join(dir, "o.json");
  fs.writeFileSync(inp, JSON.stringify({ problems }));
  const r = spawnSync(PY, [path.join(HERE, "oracle", "plan_v2_oracle.py"), "--app-root", APP, "--problems", inp, "--out", outp], { encoding: "utf8", timeout: 600000 });
  const res = r.status === 0 ? JSON.parse(fs.readFileSync(outp, "utf8")).results : null;
  fs.rmSync(dir, { recursive: true, force: true });
  if (!res) throw new Error("oracle failed: " + (r.stderr || r.error || "").toString().slice(0, 300));
  return Object.fromEntries(res.map((x) => [x.name, x]));
}
const mk = ["unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost"];
function oracleDiff(o, x) {
  if (o.status !== x.status) return `status ${o.status} ≠ ${x.status}`;
  if (o.feasible_count !== x.feasible_count) return `feasible_count ${o.feasible_count} ≠ ${x.feasible_count}`;
  if (o.evaluated !== x.evaluated) return `evaluated ${o.evaluated} ≠ ${x.evaluated}`;
  for (const k of ["mean", "minimax", "coverage"]) {
    const a = o.objectives[k], b = x.objectives[k];
    if ((a === null) !== (b === null)) return `${k} null mismatch`;
    if (a && view(a.selected_ids) !== view(b.selected_ids)) return `${k} plan differs: ${view(a.selected_ids)} vs oracle ${view(b.selected_ids)}`;
    const bad = a && mk.find((m) => a.metrics[m] !== b.metrics[m]);
    if (bad) return `${k} ${view(a.selected_ids)}: ${bad} ${a.metrics[bad]} vs oracle ${b.metrics[bad]}`;
  }
  if (view(o.pareto.map((p) => [p.cost, p.weighted_sum_mm, p.selected_ids])) !== view(x.pareto.map((p) => [p.cost, p.weighted_sum_mm, p.selected_ids]))) return "pareto differs";
  if (o.sensitivity) {
    const a = o.sensitivity.map((s) => [s.budget, s.status, s.feasible_count, s.mean ? s.mean.selected_ids : null]);
    const b = x.sensitivity.map((s) => [s.budget, s.status, s.feasible_count, s.mean_ids === undefined ? null : s.mean_ids]);
    if (view(a) !== view(b)) return `sensitivity differs: ${view(a)} vs ${view(b)}`.slice(0, 300);
  }
  return null;
}
function manualDiff(ev, x) {                                     // manual plan (selected_ids) vs oracle
  if (!ev) return null;
  for (const m of mk) if (ev.metrics[m] !== x.selected_evaluation[m]) return `manual ${m} ${ev.metrics[m]} ≠ ${x.selected_evaluation[m]}`;
  for (const row of ev.rows) if (row.after_mm !== x.selected_after_mm[row.id]) return `manual row ${row.id} after_mm ${row.after_mm} ≠ ${x.selected_after_mm[row.id]}`;
  return null;
}

// ---------------------------------------------------------------- main
const t0 = Date.now();
const failures = [];
const seenFail = new Set();                                    // only the first failure of each property is shrunk / gets a repro
const firstOf = (key) => !seenFail.has(key) && !!seenFail.add(key);
let ran = 0, invalidRan = 0, propChecks = 0;
const replayIdx = REPLAY ? Number(REPLAY.split(":")[1]) : null;
const indices = REPLAY ? [replayIdx] : Array.from({ length: CASES }, (_, i) => i);
const validForOracle = [];
const gen = {}, mutSeen = {};
for (const i of indices) {
  if (Date.now() - t0 > MAX_MS) break;
  const cs = caseSeed(SEED, i), tag = `${SEED}:${i}`;
  const sc = genScenario(cs), g = R(cs ^ 0x5bd1e995);
  ran++;
  for (const [name, prop] of Object.entries(PROPS)) {
    propChecks++;
    let msg;
    try { msg = prop(sc, R(cs ^ 0x1234)); } catch (e) { msg = `exception: ${e.message}`; }
    if (msg) {
      if (firstOf(`property/${name}`)) {
        const fails = (s) => { try { return !!prop(s, R(cs ^ 0x1234)); } catch (e) { return true; } };
        const sh = shrink(sc, fails);
        failures.push({ kind: "property", property: name, case: tag, message: msg, shrink_steps: sh.steps,
          minimal: { points: sh.scenario.control_points.length, candidates: sh.scenario.candidates.length },
          repro: saveRepro("property", name, tag, sh.scenario, msg) });
      } else failures.push({ kind: "property", property: name, case: tag, message: msg });
    }
  }
  validForOracle.push({ name: tag, scenario: sc });
  try {                                                         // generator coverage (what the random cases actually exercised)
    const o = A.optimize(imp(sc).state), nc = sc.candidates.length;
    const inc = (k) => { gen[k] = (gen[k] || 0) + 1; };
    inc(`status:${o.status}`); inc(`candidates:${nc === 0 ? "0" : nc <= 5 ? "1-5" : nc <= 10 ? "6-10" : nc < 16 ? "11-15" : "16"}`);
    inc(`city:${sc.city_id}/${sc.category}`);
    if (sc.required_ids.length) inc("has_required"); if (sc.excluded_ids.length) inc("has_excluded");
    if (o.objectives && o.objectives.mean && o.objectives.mean.metrics.unknown_count) inc("winner_with_unknown");
    if (o.pareto && o.pareto.length > 1) inc("pareto_len>1");
  } catch (e) { gen.coverage_error = (gen.coverage_error || 0) + 1; }
  const m = mutate(sc, g);
  if (m) {
    invalidRan++; mutSeen[m.name] = (mutSeen[m.name] || 0) + 1;
    const msg = invalidRefusedAtomically(m.text);
    if (msg && !firstOf(`mutation/${m.name}`)) failures.push({ kind: "mutation", property: m.name, case: tag, message: msg });
    else if (msg) failures.push({ kind: "mutation", property: m.name, case: tag, message: msg,
      repro: (() => {
        fs.mkdirSync(REPRO, { recursive: true });
        const big = m.text.length > 20000, f = path.join(REPRO, `mutation_${m.name}_${tag.replace(":", "_")}.${big ? "recipe.json" : "txt"}`);
        fs.writeFileSync(f, big ? JSON.stringify({ mutation: m.name, bytes: Buffer.byteLength(m.text, "utf8"), replay: `--seed ${SEED} --replay ${tag}`, head: m.text.slice(0, 200) }, null, 1) + "\n" : m.text);
        return path.relative(HERE, f);
      })() });
  }
}

// differential vs the Python oracle (one batch; failures shrunk with per-step oracle calls)
let oracleCompared = 0, oracleNote = "skipped (--no-oracle)";
if (USE_ORACLE && validForOracle.length) {
  const ex = runOracle(validForOracle.map((v) => ({ name: v.name, scenario: { ...v.scenario } })));
  for (const v of validForOracle) {
    const r = imp(v.scenario);
    if (!r.ok) continue;
    oracleCompared++;
    const both = (st, x) => oracleDiff(A.optimize(st), x) || manualDiff(A.evaluate ? A.evaluate(st) : null, x);
    const d = both(r.state, ex[v.name]);
    if (d && firstOf("oracle/equals_python_oracle")) {
      const fails = (s) => { const rr = imp(s); if (!rr.ok) return false; const e2 = runOracle([{ name: "x", scenario: s }]).x; return !!both(rr.state, e2); };
      const sh = shrink(v.scenario, fails, 60);
      failures.push({ kind: "oracle", property: "equals_python_oracle", case: v.name, message: d, shrink_steps: sh.steps,
        minimal: { points: sh.scenario.control_points.length, candidates: sh.scenario.candidates.length },
        repro: saveRepro("oracle", "equals_python_oracle", v.name, sh.scenario, d) });
    } else if (d) failures.push({ kind: "oracle", property: "equals_python_oracle", case: v.name, message: d });
  }
  oracleNote = `compared ${oracleCompared} scenarios with oracle/plan_v2_oracle.py`;
}

// limits in a child process with a watchdog (a freeze is a FAIL, not a hang of this runner)
const lim = spawnSync(process.execPath, [path.join(HERE, "limits_child.cjs"), APP, ADAPTER], { encoding: "utf8", timeout: 20000 });
let limits;
if (lim.error || lim.status !== 0) {
  limits = { ok: false, detail: lim.error ? `timeout/kill: ${lim.error.code}` : lim.stderr.slice(0, 300) };
  failures.push({ kind: "limits", property: "refuse_before_enumeration", case: "-", message: limits.detail });
} else {
  const L = JSON.parse(lim.stdout.trim().split("\n").pop());
  const importOk = L.import[16].ok && [17, 24, 40].every((n) => !L.import[n].ok && L.import[n].ms < 200);
  const uncheckedOk = L.unchecked === null ? null : [20, 30].every((n) => L.unchecked[n].status === "too_large" && L.unchecked[n].evaluated === 0 && L.unchecked[n].ms < 200);
  limits = { ok: importOk && uncheckedOk !== false, import: L.import, unchecked: L.unchecked === null ? "SKIP (no optimizeUnchecked)" : L.unchecked };
  if (!limits.ok) failures.push({ kind: "limits", property: "refuse_before_enumeration", case: "-", message: JSON.stringify(L).slice(0, 300) });
}

// worst-case benchmark (16 candidates, 25 points, max_selected 5, generous budget)
let bench = null;
if (BENCH) {
  const bb = D.cities.shymkent.bbox;
  const g = R(42);
  const xy = () => [round6(bb[0] + g.r() * (bb[2] - bb[0])), round6(bb[1] + g.r() * (bb[3] - bb[1]))];
  const sc = { schema_version: "city-plan-v2", city_id: "shymkent", source_snapshot: A.snapshot("shymkent"), category: "school",
    control_points: Array.from({ length: 25 }, (_, k) => { const [lon, lat] = xy(); return { id: `p${k}`, lon, lat, weight: g.int(1, 100) }; }),
    candidates: Array.from({ length: 16 }, (_, k) => { const [lon, lat] = xy(); return { id: `c${k}`, lon, lat, category: "school", kind: "hypothetical", cost: g.int(1, 200000) }; }),
    budget: 1000000, max_selected: 5, coverage_radius_m: 500, required_ids: [], excluded_ids: [], selected_ids: [] };
  const st = imp(sc).state;
  const times = [];
  let res;
  for (let k = 0; k < 5; k++) { const s = process.hrtime.bigint(); res = A.optimize(st); times.push(Number(process.hrtime.bigint() - s) / 1e6); }
  times.sort((a, b) => a - b);
  bench = { scenario: "25 points × 16 candidates × max_selected 5, budget 1000000 (synthetic)", evaluated: res.evaluated, feasible: res.feasible_count,
            sync_ms_median_incl_sensitivity: +times[2].toFixed(1), sync_ms_max: +times[4].toFixed(1) };
  if (USE_ORACLE) {
    const s = Date.now(); runOracle([{ name: "bench", scenario: sc }]); bench.python_oracle_ms_incl_startup = Date.now() - s;
  }
  if (A.optimizeAsync) {                                       // started after the (blocking) oracle call, so the timing is its own
    const s = process.hrtime.bigint();
    let last = s, maxSlice = 0, slices = 0;
    const yieldFn = () => { const now = process.hrtime.bigint(); maxSlice = Math.max(maxSlice, Number(now - last) / 1e6); slices++;
                            return new Promise((r) => setImmediate(r)).then(() => { last = process.hrtime.bigint(); }); };
    bench.async_promise = A.optimizeAsync(st, { requestId: "bench", chunk: 4096, yieldFn }).then((r) => {
      const now = process.hrtime.bigint(); maxSlice = Math.max(maxSlice, Number(now - last) / 1e6);
      Object.assign(bench, { async_ms_total_no_sensitivity: +(Number(now - s) / 1e6).toFixed(1), async_slices: slices + 1,
                             async_max_slice_ms: +maxSlice.toFixed(1), async_status: r.status, async_equals_sync: view(r.objectives) === view(res.objectives) });
    });
  }
}

(async () => {
  if (bench && bench.async_promise) { await bench.async_promise; delete bench.async_promise; }
  const summary = { adapter: path.basename(ADAPTER), app_root: path.basename(APP), seed: SEED, cases_requested: REPLAY ? 1 : CASES, cases_run: ran,
    truncated_by_time_budget: !REPLAY && ran < CASES, property_checks: propChecks, invalid_mutations: invalidRan, mutation_kinds: Object.fromEntries(Object.entries(mutSeen).sort()), oracle: oracleNote,
    limits: limits.ok ? "PASS" : "FAIL", generator_coverage: Object.fromEntries(Object.entries(gen).sort()), failures: failures.length, elapsed_ms: Date.now() - t0, verdict: failures.length ? "FAIL" : "PASS" };
  const byProp = {};
  for (const f of failures) byProp[`${f.kind}/${f.property}`] = (byProp[`${f.kind}/${f.property}`] || 0) + 1;
  summary.failures_by_property = byProp;
  for (const f of failures.filter((x) => x.repro || x.kind === "limits")) console.log(`FAIL ${f.kind}/${f.property} case ${f.case}: ${f.message}${f.repro ? ` → ${f.repro}` : ""}${f.minimal ? ` (minimal: ${f.minimal.points} pts, ${f.minimal.candidates} cand, ${f.shrink_steps} steps)` : ""}`);
  if (bench) console.log("bench " + JSON.stringify(bench));
  console.log(JSON.stringify(summary));
  const shown = failures.filter((x) => x.repro || x.kind === "limits").concat(failures.filter((x) => !(x.repro || x.kind === "limits")).slice(0, 30));
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, limits, bench, failures: shown, failures_omitted: failures.length - shown.length }, null, 1) + "\n");
  process.exit(failures.length ? 1 : 0);
})();
