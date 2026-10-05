// facts.js vs Python K02 reference (tests/expected_explanations.json) + plan / digest / null-vs-0 cases.
// Usage: node tests/conformance.cjs   (no dependencies)
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const W = path.join(__dirname, "..", "web");
const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx, { filename: f });
const F = require(path.join(W, "facts.js"));
const D = ctx.CITY_EVIDENCE, EV = ctx.CITY_OBS;
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + detail : "")); };
const clone = (x) => JSON.parse(JSON.stringify(x));
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || e.message; } };

// 1. byte-equal text and equal digest with the Python K02 renderer
const exp = JSON.parse(fs.readFileSync(path.join(__dirname, "expected_explanations.json"), "utf8"));
for (const c of exp.cases) {
  const r = F.explain(D, EV, c.city, new Set(c.groups), c.lang);
  check(`K02 parity ${c.city} ${c.lang} [${c.groups.length}]`, r.text === c.text && r.scenario === c.scenario && r.catalog_digest === c.catalog_digest,
    `\n--- js ${r.catalog_digest} ---\n${r.text}\n--- py ${c.catalog_digest} ---\n${c.text}`);
}
for (const s of ["", "abc", "Шымкент · Әл-Фараби", "x".repeat(200)])
  check(`sha256 = node:crypto (${s.length} chars)`, F.sha256hex(s) === crypto.createHash("sha256").update(s, "utf8").digest("hex"));

// 2. plan validation
const all = new Set(F.GROUP_ORDER);
const sh = F.buildCatalog(D, EV, "shymkent", all), ast = F.buildCatalog(D, EV, "astana", all);
const plan = (sections, digest) => ({ sections, catalog_digest: digest });
const sid = (p) => `kz.shymkent/${sh.scenario}/${p}`;
check("unknown fact ID rejected", code(() => F.validatePlan(plan([{ type: "summary", fact_ids: [sid("places.hospital_beds")] }], sh.digest), sh)) === "unknown_id");
check("foreign city ID rejected", code(() => F.validatePlan(plan([{ type: "summary", fact_ids: [`kz.astana/${ast.scenario}/places.school`] }], sh.digest), sh)) === "foreign_city");
const onlySchool = F.buildCatalog(D, EV, "shymkent", new Set(["school"]));
check("old plan after filter change rejected (stale_catalog)", code(() => F.validatePlan(F.StubSelector.select(F.catalogView(sh.catalog), sh.digest), onlySchool)) === "stale_catalog");
check("old scenario ID with current digest rejected (stale_scenario)", code(() => F.validatePlan(plan([{ type: "summary", fact_ids: [sid("places.school")] }], onlySchool.digest), onlySchool)) === "stale_scenario");
check("free text instead of ID rejected", code(() => F.validatePlan(plan([{ type: "summary", fact_ids: ["В Шымкенте 500 школ"] }], sh.digest), sh)) === "not_an_id");
check("null outside data_gaps rejected", code(() => F.validatePlan(plan([{ type: "summary", fact_ids: [sid("capacity.school_places")] }], sh.digest), sh)) === "null_as_fact");
check("value inside data_gaps rejected", code(() => F.validatePlan(plan([{ type: "data_gaps", fact_ids: [sid("places.school")] }], sh.digest), sh)) === "value_in_gaps");
check("same ID in two sections rejected", code(() => F.validatePlan(plan([{ type: "summary", fact_ids: [sid("places.school")] }, { type: "risks", fact_ids: [sid("places.school")] }], sh.digest), sh)) === "duplicate_id");
check("plan without digest rejected", code(() => F.validatePlan({ sections: [{ type: "summary", fact_ids: [sid("places.school")] }] }, sh)) === "stale_catalog");

// 3. digest depends on values, units, coverage and missing_reason — same city, same filter
const oldPlan = F.StubSelector.select(F.catalogView(sh.catalog), sh.digest);
const variants = {
  value: (e) => { e.observations.find((o) => o.indicator_id === "overture_place_records.school.conf_ge_0_0").value += 1; },
  unit: (e) => { e.observations.find((o) => o.indicator_id === "segments_foot_access.unknown").unit = "records"; },
  coverage: (e) => { e.observations.find((o) => o.indicator_id === "overture_place_records.school.conf_ge_0_0").coverage.complete = false; },
  missing_reason: (e) => { e.observations.find((o) => o.indicator_id === "capacity.school_places").missing_reason = "not_collected"; },
  release: (e) => { e.release = "2026-10-21.0"; },
};
for (const [k, mut] of Object.entries(variants)) {
  const ev2 = clone(EV); mut(ev2.cities.shymkent);
  const b2 = F.buildCatalog(D, ev2, "shymkent", all);
  check(`digest changes when ${k} changes`, b2.digest !== sh.digest);
  const res = code(() => F.validatePlan(oldPlan, b2));
  check(`old answer rejected after ${k} update (same city)`, res === "stale_catalog" || res === "stale_scenario", res);
}
check("current plan accepted", code(() => F.validatePlan(oldPlan, sh)) === "accepted");

// 4. null vs 0; units/coverage/reason kept in output
const r = F.explain(D, EV, "astana", all, "ru");
const used = Object.fromEntries(r.facts_used.map((f) => [f.id.split("/")[2], f]));
check("capacity is null with reason, not 0", used["capacity.school_places"].value === null && used["capacity.school_places"].missing_reason === "not_in_source" && r.text.includes("Мощность школ: нет данных (неизвестно, нет в источнике)"));
check("city total is unknown, separate from the square", used["city.place_records_total"].value === null && used["city.place_records_total"].missing_reason === "not_collected");
const zeroObs = Object.values(EV.cities).flatMap((c) => c.observations).filter((o) => o.value === 0);
check("every 0 is reported_zero over a complete query result", zeroObs.length > 0 && zeroObs.every((o) => o.value_status === "reported_zero" && o.coverage.complete === true), JSON.stringify(zeroObs.map((o) => o.obs_id)));
check("unit kept in text (records / segments)", r.text.includes("8 записей") && /\d+ сегментов/.test(r.text));
check("facts_used keep unit/coverage/missing_reason", r.facts_used.every((f) => "unit" in f && "coverage_complete" in f && "missing_reason" in f));
const shy = F.explain(D, EV, "shymkent", all, "ru");
check("Shymkent QA facts: 14 colocated, 5 category doubts", shy.text.includes("С совпадающими координатами: 14 записей") && shy.text.includes("С сомнением в категории: 5 записей"));
console.log(fails ? `${fails} FAILED` : "all passed");
process.exit(fails ? 1 : 0);
