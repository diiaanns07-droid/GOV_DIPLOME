// K02 r9 demo: объяснения обоих городов — v2 (explainPlans СБОРКИ) и устойчивость (адаптер K02). Без API-ключа; шаблон, не AI.
//   node demo.cjs --app-root <prototypes/city-evidence> [--out examples] [--lang ru|kk]
const fs = require("fs"), path = require("path");
const { PL, F, r8, solve, arg, resSolve } = require("./tests/res_common.cjs");
const out = arg("--out"), langs = arg("--lang") ? [arg("--lang")] : ["ru", "kk"];
for (const [city, v2fx, resfx] of [["shymkent", "real_shymkent_school", "res_shymkent_school"], ["astana", "real_astana_clinic", "res_astana_clinic"]]) {
  const v2 = solve(r8(v2fx)).text(), rs = resSolve(resfx), res = Object.fromEntries(langs.map((l) => [l, rs.text(l)]));
  console.log(`===== ${city}: city-plan-v2 (explainPlans сборки) =====\n${v2}\n`);
  for (const l of langs) console.log(`===== ${city}: устойчивость (${l}) =====\n${res[l]}\n`);
  if (out) { fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, `${city}.txt`), `# ${city}: шаблонные объяснения (не LLM/AI). kk — черновик, требует языковой проверки.\n\n## city-plan-v2 (web/plan.js explainPlans сборки)\n${v2}\n\n` +
      langs.map((l) => `## Устойчивость к допущениям (${l}) — resilience_facts.js\n${res[l]}\n`).join("\n")); }
}
