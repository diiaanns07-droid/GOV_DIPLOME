// K01 round 9 stage 1: K01 r8 fixtures + compatibility checks against the REAL BUILD plan.js/whatif.js (headless, no DOM).
//   node test_compat.cjs --app-root APP      exit 1 on any discrepancy; prints a minimal input for each
const fs = require("fs"), path = require("path");
const { loadBuild } = require("./build_adapter.cjs");
const ai = process.argv.indexOf("--app-root");
if (ai < 0) { console.error("usage: node test_compat.cjs --app-root APP"); process.exit(2); }
const B = loadBuild(process.argv[ai + 1]);
const R8 = path.join(__dirname, "..", "..", "round-8-results", "K01", "fixtures");
const POL = JSON.parse(fs.readFileSync(path.join(__dirname, "POLICY_r8_to_build.json"), "utf8"));
let pass = 0, fail = 0; const diffs = [];
const t = (name, fn) => { try { fn(); pass++; console.log("PASS", name); } catch (e) { fail++; console.log("FAIL", name, "—", e.message); diffs.push({ name, error: e.message, minimal: e.minimal }); } };
const eq = (a, b, m, minimal) => { if (JSON.stringify(a) !== JSON.stringify(b)) { const e = new Error(`${m || ""} got ${JSON.stringify(a).slice(0, 200)} want ${JSON.stringify(b).slice(0, 200)}`); e.minimal = minimal; throw e; } };
const verdict = (r) => (r.ok ? "valid:" + r.city : r.code);

// ---- 1. every r8 fixture under the BUILD contract ----
const EXP = JSON.parse(fs.readFileSync(path.join(R8, "EXPECTED.json"), "utf8")).fixtures;
for (const [n, e] of Object.entries(EXP)) {
  t(`r8 fixture ${n}`, () => {
    const want = POL.policy_overrides[n] ? POL.policy_overrides[n].build : e.valid ? "valid:" + JSON.parse(fs.readFileSync(path.join(R8, "synthetic", n), "utf8").replace(/^\ufeff/, "").replace(/"\\u0063ity_id"/, '"city_id"')).city_id : POL.code_map[e.code] || e.code;
    eq(verdict(B.importV2(new Uint8Array(fs.readFileSync(path.join(R8, "synthetic", n))))), want, "", `fixtures/synthetic/${n} (round-8 K01)`);
  });
}

// ---- 2. roundtrips ----
const base = (city) => B.importV2(new Uint8Array(fs.readFileSync(path.join(R8, "synthetic", (city === "shymkent" ? "shy" : "ast") + "_valid_clinic_constraints.json")))).scenario;
for (const city of ["shymkent", "astana"]) {
  t(`v2 roundtrip ${city}: export (with derived) → import gives the same scenario`, () => {
    const sc = base(city), txt = B.PL.exportPlanScenario(B.ctxFor(city), sc, B.F), r = B.importV2(txt);
    eq(r.ok, true); eq(r.scenario, sc);
    for (const bad of ["/home/", "/tmp/", "C:\\", "file:", "http"]) if (txt.includes(bad)) throw new Error("export contains " + bad);
  });
  t(`v2 ${city}: tampered derived → forged_derived; derived removed → accepted (derived optional)`, () => {
    const o = JSON.parse(B.PL.exportPlanScenario(B.ctxFor(city), base(city), B.F));
    o.derived_results.manual.metrics.weighted_sum_mm -= 1;
    eq(B.importV2(JSON.stringify(o)).code, "forged_derived", "", "export, then weighted_sum_mm -= 1");
    delete o.derived_results; eq(B.importV2(JSON.stringify(o)).ok, true);
  });
  t(`v1 ${city}: BUILD whatif export → v1 import ok, v2 import → wrong_version`, () => {
    const t1 = fs.readFileSync(path.join(R8, "v1", `${city}_v1_from_build_whatif.json`), "utf8");
    eq(B.importV1(t1).ok, true); eq(B.importV2(t1).code, "wrong_version");
  });
}

// ---- 3. foreign snapshot / other city with explicit ctx ----
t("foreign snapshot: Astana snapshot in a Shymkent file → foreign_snapshot", () => {
  const o = base("shymkent"); o.source_snapshot = B.ctxFor("astana").source_snapshot;
  eq(B.importV2(JSON.stringify(o)).code, "foreign_snapshot", "", "shy scenario with astana source_snapshot");
});
t("foreign snapshot: metric/version change → foreign_snapshot (snapshot binds metric)", () => {
  const o = base("shymkent"); o.source_snapshot = "sha256:" + "0".repeat(64); eq(B.importV2(JSON.stringify(o)).code, "foreign_snapshot");
});
t("validatePlanScenario with the other city's ctx → other_city", () => {
  let code = null; try { B.PL.validatePlanScenario(base("shymkent"), B.ctxFor("astana")); } catch (e) { code = e.code; } eq(code, "other_city");
});

// ---- 4. UTF-8 / NFC IDs (BUILD policy: letters of any script, digits, _ . -, NFC, 1..64 code points) ----
const withId = (id) => { const o = base("shymkent"); o.control_points[0].id = id; return JSON.stringify(o); };
const idCases = [
  ["Cyrillic", "тчк-01", true], ["Kazakh letters", "нүкте_Әң.1", true], ["64 Cyrillic code points (128 bytes)", "ж".repeat(64), true],
  ["65 code points", "ж".repeat(65), false], ["NFD й (и + U+0306)", "и\u0306-1", false], ["NFC й", "\u0439-1", true],
  ["zero-width space", "cp\u200b1", false], ["emoji", "cp😀", false], ["lone surrogate (escaped)", null, false], ["space", "cp 1", false],
  ["slash/URL", "https://x", false], ["leading underscore", "_cp", true], ["empty", "", false], ["Arabic-Indic digits", "cp٣", true],
];
for (const [name, id, ok] of idCases) {
  t(`ID ${name} → ${ok ? "accepted" : "bad_id"}`, () => {
    const txt = id === null ? withId("cpX").replace('"cpX"', '"cp\\ud800"') : withId(id);
    const r = B.importV2(txt);
    eq(ok ? r.ok : r.code, ok ? true : "bad_id", "", `control_points[0].id = ${JSON.stringify(id)}`);
    if (ok) eq(r.scenario.control_points.some((p) => p.id === id), true);
  });
}
t("BOM-prefixed UTF-8 file accepted", () => { eq(B.importV2("\ufeff" + JSON.stringify(base("astana"))).ok, true); });
t("size: exactly 256 KiB (UTF-8 bytes incl. 2-byte Cyrillic ID) accepted, +1 byte → too_large", () => {
  const o = base("shymkent"); o.control_points[0].id = "ж".repeat(64);
  const s = JSON.stringify(o), pad = 256 * 1024 - Buffer.byteLength(s);
  const exact = s.slice(0, -1) + " ".repeat(pad) + "}";
  eq(Buffer.byteLength(exact), 262144);
  eq(B.importV2(exact).ok, true, "exact 256 KiB");
  eq(B.importV2(s.slice(0, -1) + " ".repeat(pad + 1) + "}").code, "too_large", "", "262145-byte file with a 64×'ж' ID");
});
// ---- 5. atomicity at the API level: failure returns nothing, contexts are frozen, input is not mutated ----
t("refusal leaves context and input untouched", () => {
  const ctx = B.ctxFor("shymkent"), snap = JSON.stringify(ctx);
  const o = base("shymkent"); o.budget = -5; const before = JSON.stringify(o);
  let code = null; try { B.PL.validatePlanScenario(o, ctx); } catch (e) { code = e.code; }
  eq(code, "bad_budget"); eq(JSON.stringify(o), before); eq(JSON.stringify(ctx), snap); eq(Object.isFrozen(ctx.places[0]), true);
});

console.log(`\n${pass} passed, ${fail} failed, 0 skipped`);
fs.writeFileSync(path.join(__dirname, "runs", "compat_diffs.json"), JSON.stringify(diffs, null, 1) + "\n");
process.exitCode = fail ? 1 : 0;
