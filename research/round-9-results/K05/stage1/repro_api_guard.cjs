/* Минимальное воспроизведение: публичный createSearch/optimizePlans сборки не проверяет размер задачи.
 *   node repro_api_guard.cjs --app-root <checkout>/prototypes/city-evidence            (родитель: запускает дочерние процессы с таймаутом)
 *   node repro_api_guard.cjs --app-root … --child --n 20 --mode raw|mutated|validated  (дочерний: один прогон)
 * raw       — объект без validatePlanScenario (прямой вызов API);
 * mutated   — validatePlanScenario на 2 кандидатах, затем в возвращённый объект дописаны кандидаты и max_selected;
 * validated — честный путь: validatePlanScenario на N кандидатах (ожидается too_many_candidates при N>16).
 * Синтетические кандидаты на реальном срезе Шымкента. Это не атака на сервер: проверяется локальный расчёт в браузере/Node.
 */
"use strict";
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm"), cp = require("node:child_process");
const argv = process.argv.slice(2), arg = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const APP = arg("--app-root");
if (!APP) { console.error("нужен --app-root"); process.exit(2); }

if (argv.includes("--child")) {
  const W = path.join(APP, "web");
  const sb = {}; vm.createContext(sb); sb.window = sb;
  vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), sb);
  const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js"));
  const ctx = PL.makeContext(sb.CITY_EVIDENCE, "shymkent", F);
  const n = Number(arg("--n")), mode = arg("--mode");
  const b = ctx.bbox;
  const cand = (i) => ({ id: `syn_c${String(i).padStart(2, "0")}`, lon: b[0] + (b[2] - b[0]) * ((i * 37) % 97) / 97, lat: b[1] + (b[3] - b[1]) * ((i * 53) % 89) / 89,
    category: "school", kind: "hypothetical", cost: 1 });
  const raw = { schema_version: PL.SCHEMA, city_id: "shymkent", source_snapshot: ctx.source_snapshot, category: "school",
    control_points: [{ id: "p1", lon: (b[0] + b[2]) / 2, lat: (b[1] + b[3]) / 2, weight: 1 }],
    candidates: Array.from({ length: n }, (_, i) => cand(i)), budget: 1000000, max_selected: 5, coverage_radius_m: 500,
    required_ids: [], excluded_ids: [], selected_ids: [] };
  let sc;
  try {
    if (mode === "raw") sc = raw;
    else if (mode === "validated") sc = PL.validatePlanScenario(raw, ctx);
    else { sc = PL.validatePlanScenario({ ...raw, candidates: raw.candidates.slice(0, 2) }, ctx); sc.candidates.push(...raw.candidates.slice(2)); sc.max_selected = n; }
  } catch (e) { console.log(JSON.stringify({ n, mode, rejected: e.code || String(e) })); process.exit(0); }
  const t0 = Date.now();
  let s;
  try { s = PL.createSearch(ctx, sc, { F }); } catch (e) { console.log(JSON.stringify({ n, mode, rejected_at_createSearch: e.code || String(e) })); process.exit(0); }
  const total = s.total;
  console.log(JSON.stringify({ n, mode, started: true, total_subsets: total }));
  while (!s.step(1 << 16));
  const r = s.result();
  console.log(JSON.stringify({ n, mode, done: true, status: r.status, evaluated: r.evaluated, ms: Date.now() - t0 }));
  process.exit(0);
}

const TIMEOUT_MS = Number(arg("--timeout", "8000"));
const out = [];
for (const [mode, n] of [["validated", 16], ["validated", 20], ["raw", 16], ["raw", 20], ["raw", 22], ["raw", 30], ["mutated", 22], ["mutated", 30]]) {
  const t0 = Date.now();
  const r = cp.spawnSync(process.execPath, [__filename, "--app-root", APP, "--child", "--n", String(n), "--mode", mode], { timeout: TIMEOUT_MS, encoding: "utf8" });
  const lines = (r.stdout || "").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));
  const row = { mode, n, wall_ms: Date.now() - t0, timed_out: r.error ? r.error.code === "ETIMEDOUT" : false, signal: r.signal, child: lines };
  out.push(row);
  console.log(JSON.stringify(row));
}
const rejected = (x) => x.child[0] && (x.child[0].rejected || x.child[0].rejected_at_createSearch);
const verdict = {
  validated_path_guarded: out.find((x) => x.mode === "validated" && x.n === 20).child[0].rejected === "too_many_candidates",
  raw_path_unguarded: out.filter((x) => x.mode === "raw" && x.n > 16).every((x) => x.child[0] && x.child[0].started && x.child[0].total_subsets === 2 ** x.n),
  mutated_path_unguarded: out.filter((x) => x.mode === "mutated").every((x) => x.child[0] && x.child[0].started && x.child[0].total_subsets === 2 ** x.n),
  hang_reproduced: out.some((x) => x.timed_out),
  all_oversize_rejected: out.filter((x) => x.n > 16).every(rejected),
};
console.log(JSON.stringify({ verdict, timeout_ms: TIMEOUT_MS }));
const j = arg("--json");
if (j) fs.writeFileSync(j, JSON.stringify({ app_root: APP, timeout_ms: TIMEOUT_MS, runs: out, verdict }, null, 1) + "\n");
