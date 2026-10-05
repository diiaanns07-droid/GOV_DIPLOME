// JS facts.js vs Python K02 reference (tests/expected_explanations.json) + plan-validation edge cases.
// Usage: node tests/conformance.cjs   (no dependencies)
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = path.join(__dirname, "..", "web");
const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx);
const F = require(path.join(W, "facts.js"));
const D = ctx.CITY_EVIDENCE, EV = ctx.CITY_OBS;
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + detail : "")); };

// 1. text equality with the unmodified K02 Python renderer
const exp = JSON.parse(fs.readFileSync(path.join(__dirname, "expected_explanations.json"), "utf8"));
for (const c of exp.cases) {
  const r = F.explain(D, EV, c.city, new Set(c.groups), c.lang);
  check(`K02 parity ${c.city} ${c.lang} [${c.groups.length} groups]`, r.text === c.text && r.scenario === c.scenario, `\n--- js ---\n${r.text}\n--- py ---\n${c.text}`);
}

// 2. plan validation edge cases
const all = new Set(F.GROUP_ORDER);
const sh = F.buildCatalog(D, EV, "shymkent", all), ast = F.buildCatalog(D, EV, "astana", all);
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || e.message; } };
const plan = (type, ids) => ({ sections: [{ type, fact_ids: ids }] });
const sid = (p) => `shymkent/${sh.scenario}/${p}`;
check("unknown fact ID rejected", code(() => F.validatePlan(plan("summary", [sid("places.hospital_beds")]), sh.catalog, "shymkent", sh.scenario)) === "unknown_id");
check("foreign city ID rejected", code(() => F.validatePlan(plan("summary", [`astana/${ast.scenario}/places.school`]), sh.catalog, "shymkent", sh.scenario)) === "foreign_city");
const onlySchool = F.buildCatalog(D, EV, "shymkent", new Set(["school"]));
check("stale scenario (filter changed) rejected", code(() => F.validatePlan(plan("summary", [sid("places.school")]), onlySchool.catalog, "shymkent", onlySchool.scenario)) === "stale_scenario");
check("free text instead of ID rejected", code(() => F.validatePlan(plan("summary", ["В Шымкенте 500 школ"]), sh.catalog, "shymkent", sh.scenario)) === "not_an_id");
check("null value outside data_gaps rejected", code(() => F.validatePlan(plan("summary", [sid("capacity.school_places")]), sh.catalog, "shymkent", sh.scenario)) === "null_as_fact");
check("value inside data_gaps rejected", code(() => F.validatePlan(plan("data_gaps", [sid("places.school")]), sh.catalog, "shymkent", sh.scenario)) === "value_in_gaps");

// 3. null vs 0
const capF = sh.catalog.get(sid("capacity.school_places")), amb = sh.catalog.get(sid("district_status.ambiguous"));
check("capacity is null (unknown), not 0", capF.value === null && capF.kind === "unknown");
check("ambiguous count is a real 0 over the slice", amb.value === 0 && amb.kind === "derived");
const shyPre = EV.cities.shymkent.observations.find((o) => o.indicator_id === "places.preschool");
const noGroup = EV.cities.astana.observations.filter((o) => o.indicator_id.startsWith("places.") && o.value === null);
check("groups with 0 records in a partial slice are missing/zero_in_partial_coverage (never 0)",
  noGroup.every((o) => o.value_status === "missing" && o.missing_reason === "zero_in_partial_coverage") && shyPre.value === 1, JSON.stringify(noGroup.map((o) => o.indicator_id)));
const zeroGroups = Object.values(EV.cities).flatMap((c) => c.observations).filter((o) => o.indicator_id.startsWith("places.") && o.value === 0);
check("no place count is reported as 0", zeroGroups.length === 0);
check("formatValue: 0 → '0', 1.5 → '1,5'", F.formatValue(0) === "0" && F.formatValue(1.5) === "1,5");

// 4. every fact value equals its K05 observation when filter = all
const obsByInd = Object.fromEntries(EV.cities.astana.observations.map((o) => [o.indicator_id, o.value]));
const mism = [...ast.catalog.values()].filter((f) => f.source.startsWith("k05:")).filter((f) => obsByInd[f.id.split("/")[2]] !== f.value);
check("catalog values equal K05 observations (astana, all groups)", mism.length === 0, JSON.stringify(mism));
console.log(fails ? `${fails} FAILED` : "all passed");
process.exit(fails ? 1 : 0);
