// K12 round 8, stage 3: TEST-ONLY adapter that injects one realistic bug into a copy of the K12 reference module.
// Used to show that plan_fuzz.cjs actually detects defects (mutation score) and shrinks them to a minimal repro.
//   K12_MUTANT=<name> node plan_fuzz.cjs --app-root <dir> --adapter adapters/mutant_adapter.cjs ...
// The mutated copy is written to a fresh temp directory and required from there; reference/plan_v2_ref.cjs is never changed.
// Every patch must match the source exactly once, otherwise the adapter refuses to load (a stale mutant is not a "survivor").
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");

const MUTANTS = {
  round_floor: { bug: "мм округляются вниз (floor) вместо Math.round",
    from: "Math.round(haversine(lon1, lat1, lon2, lat2) * 1000)", to: "Math.floor(haversine(lon1, lat1, lon2, lat2) * 1000)" },
  ignore_excluded: { bug: "перебор не исключает excluded_ids",
    from: "if (mask & st.exc || (mask & st.req) !== st.req) continue;", to: "if ((mask & st.req) !== st.req) continue;" },
  budget_strict: { bug: "план стоимостью ровно budget считается неподходящим (>= вместо >)",
    from: "if (cnt > sc.max_selected || cost > st.budget) continue;", to: "if (cnt > sc.max_selected || cost >= st.budget) continue;" },
  pareto_nonstrict: { bug: "Парето сохраняет точки с равной суммой и большей стоимостью",
    from: "if (p.weighted_sum_mm < best) {", to: "if (p.weighted_sum_mm <= best) {" },
  minimax_key: { bug: "в цели minimax перепутан порядок max и weighted_sum",
    from: "minimax: (m, ids) => [m.unknown_count, m.max_mm === null ? INF : m.max_mm, m.weighted_sum_mm, m.cost, ids]",
    to: "minimax: (m, ids) => [m.unknown_count, m.weighted_sum_mm, m.max_mm === null ? INF : m.max_mm, m.cost, ids]" },
  sensitivity_ceil: { bug: "средний бюджет чувствительности ceil(B/2) вместо floor(B/2)",
    from: "Math.floor(sc.budget / 2)", to: "Math.ceil(sc.budget / 2)" },
  digest_order: { bug: "problem_digest зависит от порядка control_points",
    from: "control_points: sc.control_points.slice().sort(byId)", to: "control_points: sc.control_points.slice()" },
  state_reset_on_refusal: { bug: "при отказе импорта состояние сбрасывается",
    from: "message: String(e && e.message), state };", to: "message: String(e && e.message), state: { scenario: null, evaluation: null } };" },
  extra_fields_ignored: { bug: "лишние поля точек и кандидатов молча игнорируются",
    from: "if (!keys.includes(k)) fail(\"unknown_field\"", to: "if (!keys.includes(k)) void (\"unknown_field\"" },
  weight_loose: { bug: "вес проверяется сравнением без проверки целого (1.5, \"5\", true проходят)",
    from: "intIn(p.weight, LIMITS.weight, \"bad_weight\", `${what}.weight`);",
    to: "if (!(p.weight >= 1 && p.weight <= 100)) fail(\"bad_weight\", `${what}.weight`);" },
  import_limit_off: { bug: "импорт пропускает больше 16 кандидатов",
    from: "if (nc > LIMITS.candidates[1]) fail(", to: "if (nc > 40) fail(" },
  no_size_guard: { bug: "нет отказа до перебора: 2^n подмножеств перебираются при любом n (зависание)",
    from: "  if (sc.candidates.length > LIMITS.exactMaxCandidates) return tooLarge(reg, sc, sc.candidates.length);   // refuse before enumeration\n",
    to: "" },
};

function loadMutant(name) {
  const m = MUTANTS[name];
  if (!m) throw new Error(`K12_MUTANT: unknown mutant ${JSON.stringify(name)}; known: ${Object.keys(MUTANTS).join(", ")}`);
  const src = fs.readFileSync(path.join(__dirname, "..", "reference", "plan_v2_ref.cjs"), "utf8");
  const hits = src.split(m.from).length - 1;
  if (hits !== 1) throw new Error(`mutant ${name}: patch matched ${hits} times (expected 1) — reference changed, update the mutant`);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `k12mut_${name}_`));
  const file = path.join(dir, "plan_v2_ref.cjs");
  fs.writeFileSync(file, src.replace(m.from, m.to));
  return require(file);
}

module.exports = function ({ D, requireWeb }) {
  const name = process.env.K12_MUTANT || "";
  const F = requireWeb("facts.js");
  const P = loadMutant(name);
  const reg = P.makeRegistry(D, { sha256hex: F.sha256hex, placesDigest: F.placesDigest });
  return {
    name: `k12-mutant-${name}`,
    snapshot: (city) => reg.cities[city].snapshot,
    initialState: () => ({ scenario: null, evaluation: null }),
    importScenario: (text, state) => P.importPlanScenario(text, reg, state),
    evaluate: (state) => state.evaluation,
    optimize: (state) => P.optimizePlans(reg, state.scenario),
    problemDigest: (state) => P.problemDigest(reg, state.scenario),
    optimizeUnchecked: (obj) => P.optimizePlans(reg, obj),
  };
};
module.exports.MUTANTS = MUTANTS;
