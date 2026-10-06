// Deterministic city-resilience-v1 fixtures (both cities) on the REAL BUILD context. Scenario content is SYNTHETIC
// (points, weights, costs, chosen exclusions); source IDs are real Overture record IDs of the BUILD slice.
//   node make_resilience_fixtures.cjs --app-root APP --build-sha SHA
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const { loadBuild } = require("./build_adapter.cjs");
const APP = process.argv[process.argv.indexOf("--app-root") + 1], SHA = process.argv[process.argv.indexOf("--build-sha") + 1];
const B = loadBuild(APP);
const R8 = path.join(__dirname, "..", "..", "round-8-results", "K01", "fixtures", "synthetic");
const OUT = path.join(__dirname, "fixtures", "resilience"); fs.rmSync(OUT, { recursive: true, force: true }); fs.mkdirSync(OUT, { recursive: true });
const FIX = {}, EXP = {};
const add = (name, city, obj, code, note, raw) => {
  FIX[name] = raw !== undefined ? raw : JSON.stringify(obj, null, 1) + "\n";
  EXP[name] = { city, valid: !code, ...(code ? { code } : {}), ...(note ? { note } : {}) };
};
const clone = (o) => JSON.parse(JSON.stringify(o));
for (const [city, pre] of [["shymkent", "shy"], ["astana", "ast"]]) {
  const plan = JSON.parse(fs.readFileSync(path.join(R8, `${pre}_valid_clinic_constraints.json`), "utf8"));   // outpatient_clinic, 4 candidates
  const ctx = B.ctxFor(city), other = B.ctxFor(city === "shymkent" ? "astana" : "shymkent");
  const own = ctx.places.filter((p) => p.group === plan.category).map((p) => p.id).sort();
  const school = ctx.places.filter((p) => p.group === "school").map((p) => p.id).sort();
  const foreign = other.places.filter((p) => p.group === plan.category).map((p) => p.id).sort();
  const env = (cases, p) => ({ schema_version: "city-resilience-v1", plan: p || plan, cases });
  const c1 = { id: "без-ближайших", label: "Условно без двух записей (не подтверждение закрытия)", disabled_source_ids: [own[0], own[1]] };
  const c2 = { id: "qa_doubt", label: "Сомнение QA: одна запись", disabled_source_ids: [own[2]] };
  add(`${pre}_valid_two_cases.json`, city, env([c1, c2]));
  const seven = Array.from({ length: 7 }, (_, k) => ({ id: `c${k + 1}`, label: `Случай ${k + 1} 😀 әңғ`, disabled_source_ids: [own[k % own.length]] }));
  seven[6].disabled_source_ids = seven[0].disabled_source_ids.slice();
  add(`${pre}_valid_seven_cases_dup_sets.json`, city, env(seven), null, "7 user cases (+base = 8); c1 and c7 share the same exclusion set: allowed");
  add(`${pre}_valid_exclude_all_sources.json`, city, env([{ id: "all", label: "Все записи категории условно исключены", disabled_source_ids: own.slice() }]),
    null, "exclusions == number of category records: allowed; baseline becomes empty in that case");
  add(`${pre}_valid_12_candidates.json`, city, env([c1], Object.assign(clone(plan), { candidates: Array.from({ length: 12 }, (_, k) => ({ id: `k${k}`,
    lon: plan.candidates[0].lon, lat: plan.candidates[0].lat, category: plan.category, kind: "hypothetical", cost: 100 + k })), required_ids: [], excluded_ids: [], selected_ids: [] })));
  add(`${pre}_invalid_13_candidates.json`, city, env([c1], Object.assign(clone(plan), { candidates: Array.from({ length: 13 }, (_, k) => ({ id: `k${k}`,
    lon: plan.candidates[0].lon, lat: plan.candidates[0].lat, category: plan.category, kind: "hypothetical", cost: 100 + k })), required_ids: [], excluded_ids: [], selected_ids: [] })), "too_many_candidates");
  add(`${pre}_invalid_unknown_source.json`, city, env([{ id: "x", label: "x", disabled_source_ids: ["00000000-0000-4000-8000-000000000000"] }]), "unknown_source");
  add(`${pre}_invalid_other_city_source.json`, city, env([{ id: "x", label: "x", disabled_source_ids: [foreign[0]] }]), "unknown_source", "source ID of the other city");
  add(`${pre}_invalid_other_category_source.json`, city, env([{ id: "x", label: "x", disabled_source_ids: [school[0]] }]), "wrong_category_source");
  add(`${pre}_invalid_candidate_as_source.json`, city, env([{ id: "x", label: "x", disabled_source_ids: [plan.candidates[0].id] }]), "candidate_id_as_source");
  add(`${pre}_invalid_base_reserved.json`, city, env([{ id: "base", label: "base", disabled_source_ids: [own[0]] }]), "reserved_case_id");
  add(`${pre}_invalid_duplicate_case_id.json`, city, env([c1, Object.assign({}, c2, { id: c1.id })]), "duplicate_case_id");
  add(`${pre}_invalid_eight_user_cases.json`, city, env([...seven, { id: "c8", label: "восьмой", disabled_source_ids: [own[0]] }]), "bad_cases");
  add(`${pre}_invalid_no_cases.json`, city, env([]), "bad_cases");
}
// one-city negatives (Shymkent context)
const plan = JSON.parse(fs.readFileSync(path.join(R8, "shy_valid_clinic_constraints.json"), "utf8"));
const own = B.ctxFor("shymkent").places.filter((p) => p.group === plan.category).map((p) => p.id).sort();
const env = (cases, p) => ({ schema_version: "city-resilience-v1", plan: p || plan, cases });
const cs = (o) => [Object.assign({ id: "c1", label: "метка", disabled_source_ids: [own[0]] }, o)];
add("shy_invalid_label_empty.json", "shymkent", env(cs({ label: "" })), "bad_label");
add("shy_invalid_label_spaces.json", "shymkent", env(cs({ label: "   " })), "bad_label");
add("shy_valid_label_120_codepoints.json", "shymkent", env(cs({ label: "😀".repeat(120) })), null, "120 astral code points = 240 UTF-16 units: allowed");
add("shy_invalid_label_121.json", "shymkent", env(cs({ label: "ж".repeat(121) })), "bad_label");
add("shy_invalid_label_control.json", "shymkent", env(cs({ label: "строка\u0007звонок" })), "bad_label");
add("shy_invalid_label_newline.json", "shymkent", env(cs({ label: "две\nстроки" })), "bad_label");
add("shy_invalid_label_lone_surrogate.json", "shymkent", null, "bad_label", "escaped \\ud800 in label", JSON.stringify(env(cs({ label: "XSURR" })), null, 1).replace("XSURR", "a\\ud800b") + "\n");
add("shy_valid_label_html_text.json", "shymkent", env(cs({ label: "<img src=x onerror=alert(1)> & «кавычки»" })), null, "markup is just text; UI must render via textContent");
add("shy_invalid_exclusions_empty.json", "shymkent", env(cs({ disabled_source_ids: [] })), "bad_exclusions");
add("shy_invalid_exclusions_too_many.json", "shymkent", env(cs({ disabled_source_ids: [...own, "extra-1"] })), "bad_exclusions");
add("shy_invalid_duplicate_source_id.json", "shymkent", env(cs({ disabled_source_ids: [own[0], own[0]] })), "duplicate_source_id");
add("shy_invalid_case_id_nfd.json", "shymkent", env(cs({ id: "и\u0306" })), "bad_case_id");
add("shy_invalid_case_unknown_field.json", "shymkent", env(cs({ weight: 1 })), "unknown_field");
add("shy_invalid_envelope_derived.json", "shymkent", Object.assign(env(cs({})), { derived_results: { worst: 0 } }), "unknown_field");
add("shy_invalid_plan_derived.json", "shymkent", env(cs({}), Object.assign(clone(plan), { derived_results: {} })), "derived_not_allowed");
add("shy_invalid_version.json", "shymkent", Object.assign(env(cs({})), { schema_version: "city-resilience-v2" }), "bad_version");
add("shy_invalid_plan_as_envelope.json", "shymkent", plan, "wrong_version", "a bare city-plan-v2 file opened as resilience");
add("shy_invalid_foreign_snapshot.json", "shymkent", env(cs({}), Object.assign(clone(plan), { source_snapshot: B.ctxFor("astana").source_snapshot })), "foreign_snapshot");
add("shy_invalid_plan_bad_weight.json", "shymkent", env(cs({}), (() => { const p = clone(plan); p.control_points[0].weight = 0; return p; })()), "bad_weight", "plan errors are BUILD PlanError codes");
const big = JSON.stringify(env(cs({})), null, 1);
add("shy_invalid_too_large.json", "shymkent", null, "too_large", "262145 bytes", big.slice(0, -1) + " ".repeat(256 * 1024 - Buffer.byteLength(big) + 1) + "}");
add("shy_valid_exactly_256k.json", "shymkent", null, null, "262144 bytes", big.slice(0, -1) + " ".repeat(256 * 1024 - Buffer.byteLength(big)) + "}");
add("shy_invalid_nan.json", "shymkent", null, "bad_json", "NaN in plan", big.replace(/"budget": \d+/, '"budget": NaN'));
add("shy_invalid_dup_key.json", "shymkent", null, "bad_json", "cases twice via escape", big.replace('"cases":', '"cases": [], "c\\u0061ses":'));

for (const [n, txt] of Object.entries(FIX)) fs.writeFileSync(path.join(OUT, n), txt);
fs.writeFileSync(path.join(OUT, "..", "RESILIENCE_EXPECTED.json"), JSON.stringify({ note: "SYNTHETIC envelopes; source IDs are real record IDs of the BUILD slice " + SHA.slice(0, 7), build_sha: SHA, fixtures: EXP }, null, 1) + "\n");
const man = Object.keys(FIX).sort().map((n) => { const b = fs.readFileSync(path.join(OUT, n)); return { path: "resilience/" + n, bytes: b.length, sha256: crypto.createHash("sha256").update(b).digest("hex") }; });
fs.writeFileSync(path.join(OUT, "..", "RESILIENCE_MANIFEST.json"), JSON.stringify({ build_sha: SHA, files: man }, null, 1) + "\n");
console.log(`${Object.keys(FIX).length} resilience fixtures (${Object.values(EXP).filter((e) => e.valid).length} valid)`);
