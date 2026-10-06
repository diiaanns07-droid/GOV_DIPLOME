/* Перекрёстная сверка двух независимых реализаций city-resilience-v1: web/resilience.js СБОРКИ и resilience.js K05.
 * Сравнивается математика (статус, feasible_count, nominal/robust ids, W, worst_case_ids, цена), не digest и не имена полей.
 *   node cross_build_vs_k05.cjs --app-root <checkout с web/resilience.js> [--n 48] [--json OUT]
 * Входы: реальные срезы data.js сборки; точки, кандидаты, стоимости и исключения — SYNTHETIC (seed).
 */
"use strict";
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const argv = process.argv.slice(2), arg = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const APP = arg("--app-root"), N = Number(arg("--n", "48"));
const W = path.join(APP, "web");
const sb = {}; vm.createContext(sb); sb.window = sb;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), sb);
const F = require(path.join(W, "facts.js")), X = require(path.join(W, "whatif.js")), PL = require(path.join(W, "plan.js"));
const B = require(path.join(W, "resilience.js"));
const K = require(path.join(__dirname, "..", "resilience.js")).bind(PL, F, X);
const D = sb.CITY_EVIDENCE;
function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let x = a; x = Math.imul(x ^ (x >>> 15), x | 1); x ^= x + Math.imul(x ^ (x >>> 7), x | 61); return ((x ^ (x >>> 14)) >>> 0) / 4294967296; }; }
const view = (r) => r.status !== "optimal" ? { status: r.status } : {
  status: r.status, feasible_count: r.feasible_count, nominal: r.nominal.selected_ids, robust: r.robust.selected_ids,
  W: r.robust.worst_vector, worst: r.robust.worst_case_ids, Wn: r.nominal.worst_vector, worst_n: r.nominal.worst_case_ids,
  price: r.price_of_robustness_m !== undefined ? r.price_of_robustness_m : r.price_of_resilience_m, same: r.same_plan };
const out = []; let fail = 0;
for (let i = 0; i < N; i++) {
  const city = i % 2 ? "astana" : "shymkent", cat = (i >> 1) % 2 ? "outpatient_clinic" : "school";
  const ctx = PL.makeContext(D, city, F), r = rng(5000 + i), b = ctx.bbox, at = () => [b[0] + (b[2] - b[0]) * r(), b[1] + (b[3] - b[1]) * r()];
  const src = ctx.places.filter((p) => p.group === cat).map((p) => p.id);
  const nC = Math.floor(r() * 13), nCases = 1 + Math.floor(r() * 7);
  const cases = Array.from({ length: nCases }, (_, k) => {
    if (k > 0 && r() < 0.2) return { id: `syn_case${k}`, label: `SYNTHETIC дубль ${k}`, disabled_source_ids: [] };  // заполним дублем ниже
    const n = 1 + Math.floor(r() * src.length), s = new Set(); while (s.size < n) s.add(src[Math.floor(r() * src.length)]);
    return { id: `syn_case${k}`, label: `SYNTHETIC ${k}`, disabled_source_ids: [...s] };
  });
  cases.forEach((c, k) => { if (!c.disabled_source_ids.length) c.disabled_source_ids = cases[0].disabled_source_ids.slice().reverse(); });
  const cand = Array.from({ length: nC }, (_, j) => { const [lon, lat] = at(); return { id: `syn_c${String(j).padStart(2, "0")}`, lon, lat, category: cat, kind: "hypothetical", cost: 1 + Math.floor(r() * 300) }; });
  const req = nC && r() < 0.25 ? [cand[0].id] : [], exc = nC > 2 && r() < 0.25 ? [cand[1].id] : [];
  const env = { schema_version: "city-resilience-v1", cases, plan: { schema_version: PL.SCHEMA, city_id: city, source_snapshot: ctx.source_snapshot, category: cat,
    control_points: Array.from({ length: 1 + Math.floor(r() * 25) }, (_, j) => { const [lon, lat] = at(); return { id: `syn_p${j}`, lon, lat, weight: 1 + Math.floor(r() * 100) }; }),
    candidates: cand, budget: Math.floor(r() * 800), max_selected: Math.floor(r() * 6), coverage_radius_m: 100 + Math.floor(r() * 4900),
    required_ids: req, excluded_ids: exc, selected_ids: [] } };
  let vb, vk;
  try { vb = view(B.optimizeResilience(ctx, JSON.parse(JSON.stringify(env)), { F })); } catch (e) { vb = { error: e.code || String(e) }; }
  try { vk = view(K.optimizeResilience(ctx, K.validateResilience(JSON.parse(JSON.stringify(env)), ctx))); } catch (e) { vk = { error: e.code || String(e) }; }
  const same = JSON.stringify(vb) === JSON.stringify(vk);
  if (!same) fail++;
  out.push({ i, city, cat, nC, nCases, same, ...(same ? { status: vb.status, robust_ne_nominal: vb.status === "optimal" && JSON.stringify(vb.robust) !== JSON.stringify(vb.nominal), multi_worst: vb.status === "optimal" && vb.worst.length > 1 } : { build: vb, k05: vk }) });
  if (!same) console.log("DIFF", i, JSON.stringify(vb).slice(0, 300), "|", JSON.stringify(vk).slice(0, 300));
}
const st = {}; for (const o of out) if (o.same) st[o.status] = (st[o.status] || 0) + 1;
const nontriv = { robust_ne_nominal: out.filter((o) => o.robust_ne_nominal).length, multi_worst: out.filter((o) => o.multi_worst).length };
console.log(JSON.stringify({ n: N, same: N - fail, diff: fail, statuses: st, ...nontriv }));
if (arg("--json")) fs.writeFileSync(arg("--json"), JSON.stringify({ app_root: APP, n: N, same: N - fail, diff: fail, statuses: st, ...nontriv, cases: out }, null, 1) + "\n");
process.exit(fail ? 1 : 0);
