// K02 r8 demo: сравнение планов по фикстурам, ru/kk. Без API-ключа и сети; селектор — заглушка, не LLM.
//   node demo.cjs --app-root <prototypes/city-evidence> [--fixture real_shymkent_school] [--lang ru|kk] [--out examples]
const fs = require("fs"), path = require("path");
const { fixture, solve, P, deps } = require("./tests/common.cjs");
const arg = (n) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : null; };
const names = arg("--fixture") ? [arg("--fixture")] : fs.readdirSync(path.join(__dirname, "fixtures")).map((f) => f.replace(/\.json$/, "")).sort();
const langs = arg("--lang") ? [arg("--lang")] : ["ru", "kk"], out = arg("--out");
for (const n of names) {
  const fx = fixture(n), s = solve(fx), res = {};
  for (const lang of langs) {
    const r = P.explain(s.built, lang, deps, { problem_digest: s.opt.problem_digest });
    res[lang] = r.text; console.log(`=== ${n} [${fx.provenance.kind}] ${lang} ===\n${r.text}\n`);
  }
  if (out) { fs.mkdirSync(out, { recursive: true }); fs.writeFileSync(path.join(out, n + ".json"), JSON.stringify({ fixture: n, provenance: fx.provenance,
    problem_digest: s.opt.problem_digest, catalog_digest: s.built.digest, status: s.opt.status, explanation: res,
    facts: Object.fromEntries([...s.built.catalog.values()].map((f) => [f.path, { value: f.value, unit: f.unit, kind: f.kind, scope: f.scope, hypothetical: f.hypothetical }])) }, null, 1) + "\n"); }
}
