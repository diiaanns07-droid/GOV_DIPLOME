// K02 r6: независимая сверка JS explain() с Python-эталоном сборки (tests/expected_explanations.json).
// node tests/py_js_parity.cjs --app-root <prototypes/city-evidence>   (эталон перегенерировать: python3 tools/explain_ref.py)
const fs = require("fs"), path = require("path"), vm = require("vm");
const root = process.argv[process.argv.indexOf("--app-root") + 1];
const c = {}; vm.createContext(c); c.window = c;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(root, "web", f), "utf8"), c);
const F = require(path.resolve(root, "web/facts.js"));
const exp = JSON.parse(fs.readFileSync(path.join(root, "tests/expected_explanations.json"), "utf8"));
const rows = exp.cases.map((k) => {
  const r = F.explain(c.CITY_EVIDENCE, c.CITY_OBS, k.city, new Set(k.groups), k.lang);
  return { city: k.city, lang: k.lang, groups: k.groups.length, text_equal: r.text === k.text, digest_equal: r.catalog_digest === k.catalog_digest,
    scenario_equal: r.scenario === k.scenario, // эталон хранит facts_used как список ID; JS — записи {id, value, …}: сравниваем ID и порядок
    facts_used_equal: JSON.stringify(r.facts_used.map((f) => f.id)) === JSON.stringify(k.facts_used) };
});
const ok = rows.every((r) => r.text_equal && r.digest_equal && r.scenario_equal && r.facts_used_equal);
console.log(JSON.stringify({ cases: rows.length, all_equal: ok, rows }));
process.exit(ok ? 0 : 1);
