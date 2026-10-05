// Этап 3: факты JS-каталога против независимого Python-оракула (expected/*.json), включая смену radius/weights/required/excluded/budget.
//   python3 oracle/plan_oracle.py && node tests/stage3_oracle.cjs --app-root <app>
const fs = require("fs"), path = require("path");
const { fixture, solve, P, deps, test, finish, HERE } = require("./common.cjs");
const variants = JSON.parse(fs.readFileSync(path.join(HERE, "variants.json"), "utf8")).variants;
for (const v of variants) {
  test(`O_${v.fixture}__${v.name}`, `факты = оракул (${v.fixture}, ${v.name})`, () => {
    const exp = JSON.parse(fs.readFileSync(path.join(HERE, "expected", `${v.fixture}__${v.name}.json`), "utf8"));
    const s = solve(fixture(v.fixture), v.patch), b = s.built, mism = [];
    const val = (p) => { const f = b.catalog.get(`${b.city}/${b.scenario}/${p}`); return f === undefined ? "<absent>" : f.value; };
    for (const [p, e] of Object.entries(exp.facts)) if (val(p) !== e) mism.push({ path: p, js: val(p), oracle: e });
    // лишних ролей/строк Парето в JS быть не должно
    for (const f of b.catalog.values()) if (/^(plan|pareto|sensitivity)\./.test(f.path) && !(f.path in exp.facts) && !/\.(feasible|status|selection|budget)$/.test(f.path) && !/^plan\.\w+\.(selection)$/.test(f.path))
      if (/^pareto\./.test(f.path) || /^plan\.(mean|minimax|coverage)\./.test(f.path)) mism.push({ path: f.path, js: f.value, oracle: "<absent>" });
    const ok = mism.length === 0 && b.meta.status === exp.status;
    // объяснение рендерится на обоих языках и называет наборы победителей из оракула
    const ru = P.explain(b, "ru", deps, { problem_digest: s.opt.problem_digest }).text, kk = P.explain(b, "kk", deps, { problem_digest: s.opt.problem_digest }).text;
    const named = ["mean", "minimax", "coverage"].every((r) => !exp.facts[`plan.${r}.selection`] || (ru.includes(exp.facts[`plan.${r}.selection`]) && kk.includes(exp.facts[`plan.${r}.selection`])));
    return { pass: ok && named, observed: { status: [b.meta.status, exp.status], mism: mism.slice(0, 6), named } };
  });
}
test("O_variants_change_facts", "смена radius/weights/required действительно меняет ожидаемые факты (тест не вырожден)", () => {
  const e = (n) => JSON.parse(fs.readFileSync(path.join(HERE, "expected", `real_shymkent_school__${n}.json`), "utf8")).facts;
  const base = e("base");
  const changed = (n, keys) => keys.some((k) => JSON.stringify(e(n)[k]) !== JSON.stringify(base[k]));
  const r = { radius_600: changed("radius_600", ["plan.baseline.covered_weight", "plan.mean.covered_weight"]),
    radius_100: changed("radius_100", ["plan.mean.covered_weight", "plan.coverage.covered_weight"]),
    weight: changed("weight_center_10", ["plan.mean.selection"]), required: changed("required_park", ["plan.mean.selection", "plan.minimax.selection"]),
    excluded: changed("excluded_sev", ["plan.mean.selection"]) };
  return { pass: Object.values(r).every(Boolean), observed: r };
});
finish("stage3_oracle");
