// K01 round 9 stage 2: city-resilience-v1 contract module against fixtures, on top of the REAL BUILD plan.js.
//   node test_resilience_contract.cjs --app-root APP      (exit 1 on any defect)
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const { loadBuild } = require("./build_adapter.cjs");
const B = loadBuild(process.argv[process.argv.indexOf("--app-root") + 1]);
const RC = require("./resilience_contract.js")(B.PL, B.X);
const FX = path.join(__dirname, "fixtures");
let pass = 0, fail = 0;
const t = (n, fn) => { try { fn(); pass++; console.log("PASS", n); } catch (e) { fail++; console.log("FAIL", n, "—", e.message); } };
const eq = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m || ""} got ${JSON.stringify(a).slice(0, 220)} want ${JSON.stringify(b).slice(0, 220)}`); };
const imp = (txt) => { try { const r = RC.importResilience(txt, B.ctxFor, B.F); return { ok: true, env: r.envelope, city: r.ctx.city_id }; } catch (e) { if (e && e.code) return { ok: false, code: e.code }; throw e; } };
const rd = (n) => B.browserText(new Uint8Array(fs.readFileSync(path.join(FX, "resilience", n))));
t("RESILIENCE_MANIFEST sha256", () => {
  for (const f of JSON.parse(fs.readFileSync(path.join(FX, "RESILIENCE_MANIFEST.json"), "utf8")).files) {
    const b = fs.readFileSync(path.join(FX, f.path)); eq([b.length, crypto.createHash("sha256").update(b).digest("hex")], [f.bytes, f.sha256], f.path);
  }
});
const EXP = JSON.parse(fs.readFileSync(path.join(FX, "RESILIENCE_EXPECTED.json"), "utf8")).fixtures;
for (const [n, e] of Object.entries(EXP)) t(`fixture ${n} → ${e.valid ? "valid" : e.code}`, () => { const r = imp(rd(n)); eq(r.ok ? "valid:" + r.city : r.code, e.valid ? "valid:" + e.city : e.code); });
t("JSON Schema file: strict envelope/case, base excluded, 1..7 cases, plan derived forbidden", () => {
  const s = JSON.parse(fs.readFileSync(path.join(__dirname, "resilience_v1.schema.json"), "utf8"));
  eq([s.additionalProperties, s.$defs.case.additionalProperties, s.properties.cases.minItems, s.properties.cases.maxItems, s.$defs.case.properties.label.maxLength],
    [false, false, 1, 7, 120]); eq(s.$defs.case.properties.id.allOf[1], { not: { const: "base" } });
});
t("export = input only, roundtrip identical, no derived, no paths; exclusions sorted, cases sorted", () => {
  for (const n of ["shy_valid_two_cases.json", "ast_valid_seven_cases_dup_sets.json"]) {
    const r = imp(rd(n)), txt = RC.exportResilience(r.env, B.ctxFor(r.city)), back = imp(txt);
    eq(back.env, r.env); if (/derived|\/home\/|\/tmp\/|C:\\\\/.test(txt)) throw new Error("export contains derived/path");
    eq(r.env.cases.map((c) => c.id), r.env.cases.map((c) => c.id).slice().sort());
    for (const c of r.env.cases) eq(c.disabled_source_ids, c.disabled_source_ids.slice().sort());
  }
});
t("digests: order of cases/exclusions irrelevant; label/exclusion/plan change → new problem digest; selected only in scenario digest", () => {
  const o = JSON.parse(rd("shy_valid_two_cases.json")), env = imp(JSON.stringify(o)).env;
  const d = (x) => { const v = imp(JSON.stringify(x)).env; return [RC.resilienceProblemDigest(v, B.F), RC.resilienceScenarioDigest(v, B.F), RC.exclusionsDigest(v, B.F)]; };
  const d0 = d(o);
  const perm = JSON.parse(JSON.stringify(o)); perm.cases.reverse(); perm.cases[0].disabled_source_ids.reverse(); perm.plan.control_points.reverse();
  eq(d(perm), d0, "permutation");
  const lab = JSON.parse(JSON.stringify(o)); lab.cases[0].label += "!"; const dl = d(lab);
  if (dl[0] === d0[0] || dl[2] !== d0[2]) throw new Error("label must change problem digest, not exclusions digest");
  const ex = JSON.parse(JSON.stringify(o)); ex.cases[1].disabled_source_ids.push(ex.cases[0].disabled_source_ids[0]); const de = d(ex);
  if (de[0] === d0[0] || de[2] === d0[2]) throw new Error("exclusion change must change both");
  const bud = JSON.parse(JSON.stringify(o)); bud.plan.budget += 1; if (d(bud)[0] === d0[0]) throw new Error("plan change ignored");
  const sel = JSON.parse(JSON.stringify(o)); sel.plan.selected_ids = []; const ds = d(sel);
  if (ds[0] !== d0[0] || ds[1] === d0[1]) throw new Error("selected_ids must only change scenario digest");
  if (!d0.every((x) => /^sha256:[0-9a-f]{64}$/.test(x))) throw new Error("format");
  eq(env.plan.source_snapshot, B.ctxFor("shymkent").source_snapshot, "snapshot from plan, not replaced");
});
t("computationCases adds base first; file never contains base; duplicate exclusion sets kept as separate cases", () => {
  const env = imp(rd("shy_valid_seven_cases_dup_sets.json")).env, cc = RC.computationCases(env);
  eq(cc.length, 8); eq([cc[0].id, cc[0].disabled_source_ids], ["base", []]);
});
t("refusal does not mutate input object or BUILD context", () => {
  const o = JSON.parse(rd("shy_invalid_candidate_as_source.json")), before = JSON.stringify(o), ctx = B.ctxFor("shymkent"), cs = JSON.stringify(ctx);
  let code; try { RC.validateResilience(o, ctx); } catch (e) { code = e.code; } eq(code, "candidate_id_as_source"); eq(JSON.stringify(o), before); eq(JSON.stringify(ctx), cs);
});
console.log(`\n${pass} passed, ${fail} failed, 0 skipped`);
process.exitCode = fail ? 1 : 0;
