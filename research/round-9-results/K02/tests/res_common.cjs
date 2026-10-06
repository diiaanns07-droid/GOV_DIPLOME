// Сборка фактов устойчивости из envelope-фикстуры: движок сборки (через resilience_ref) → адаптер K02.
const fs = require("fs"), path = require("path");
const C = require("./common.cjs");
const R = require(path.join(C.HERE, "resilience_ref.js")), RF = require(path.join(C.HERE, "resilience_facts.js"));
const resFixture = (n) => JSON.parse(fs.readFileSync(path.join(C.HERE, "fixtures", n + ".json"), "utf8"));
function resSolve(n, mutateEnv) {
  const fx = resFixture(n), ctx = C.ctxFor(C.r8(fx.provenance.from_r8_fixture || ({ res_synthetic_infeasible: "synthetic_infeasible_required", res_synthetic_tie: "synthetic_tie_same_winners" })[n]));
  const env = JSON.parse(JSON.stringify(fx.envelope)); if (mutateEnv) mutateEnv(env, ctx);
  const norm = R.normaliseEnvelope(env, ctx, C.PL), opt = R.optimizeResilience(ctx, norm, C.PL, C.F), man = R.evaluateResilience(ctx, norm, norm.sc.selected_ids, C.PL);
  const names = Object.fromEntries(ctx.places.map((p) => [p.id, p.name]));
  const req = { resilience_problem_digest: opt.resilience_problem_digest };
  const built = RF.buildResilienceCatalog(norm, man, opt, names, { F: C.F }, req);
  return { fx, ctx, env, norm, opt, man, names, req, built, text: (lang) => RF.explain(built, lang || "ru", { F: C.F }, req).text };
}
module.exports = { ...C, R, RF, resFixture, resSolve };
