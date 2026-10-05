// K01 round 8 stage 2: import/export/roundtrip, atomic PlanStore, v1 untouched, v1→v2 migration without invented costs.
//   node test_state.cjs --app-root APP     (APP = extracted prototypes/city-evidence; v1 checks use the BUILD's own web/whatif.js)
const fs = require("fs"), path = require("path"), crypto = require("crypto"), cp = require("child_process");
const P = require("./planv2.js");
const FX = path.join(__dirname, "fixtures");
const ai = process.argv.indexOf("--app-root"), APP = ai > 0 ? process.argv[ai + 1] : null;
const sha256hex = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
let pass = 0, fail = 0, skip = 0;
const t = (name, fn) => { try { if (fn() === "SKIP") { skip++; console.log("SKIP", name); } else { pass++; console.log("PASS", name); } }
  catch (e) { fail++; console.log("FAIL", name, "—", e.message); } };
const eq = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m || ""} ${JSON.stringify(a).slice(0, 300)} != ${JSON.stringify(b).slice(0, 300)}`); };
const throwsCode = (fn, code) => { try { fn(); } catch (e) { if (e instanceof P.PlanV2Error && e.code === code) return; throw new Error(`expected ${code}, got ${e.code || e.message}`); } throw new Error(`expected ${code}, accepted`); };
const ctxFile = (c) => { const x = JSON.parse(fs.readFileSync(path.join(FX, "real", `context_${c}.json`), "utf8")); return { city_id: c, bbox: x.bbox, source_snapshot: x.source_snapshot, sha256hex }; };
const CTX = { shymkent: ctxFile("shymkent"), astana: ctxFile("astana") };
const read = (n) => fs.readFileSync(path.join(FX, "synthetic", n));
const valid = (n, c) => P.importPlan(new Uint8Array(read(n)), CTX[c]).scenario;

// ---------- export / import roundtrip ----------
for (const [n, c] of [["shy_valid_basic.json", "shymkent"], ["ast_valid_limits.json", "astana"], ["ast_valid_empty_candidates.json", "astana"]]) {
  t(`roundtrip ${n}: export → import gives the same scenario and digests`, () => {
    const sc = valid(n, c);
    const txt = P.exportPlan(sc, CTX[c], (s) => ({ evaluated_by: "test-stub (not an optimizer)", selected: s.selected_ids }));
    const back = P.importPlan(txt, CTX[c]);
    eq(back.scenario, sc); eq(back.notes.length, 1, "derived dropped note");
    eq(P.scenarioDigest(back.scenario, CTX[c]), P.scenarioDigest(sc, CTX[c]));
    for (const bad of ["/home/", "/tmp/", "C:\\", "file:", "http:", "https:"]) if (txt.includes(bad)) throw new Error("export contains " + bad);
    const o = JSON.parse(txt);
    eq(Object.keys(o).slice(0, 12), ["schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
      "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"], "input fields first");
    eq(o.derived_results.kind, "derived");
  });
}
t("export without derive has no derived_results; JS export → Python oracle import is identical", () => {
  const sc = valid("shy_valid_clinic_constraints.json", "shymkent");
  const txt = P.exportPlan(sc, CTX.shymkent);
  if (txt.includes("derived_results")) throw new Error("unexpected derived_results");
  const tmp = fs.mkdtempSync(path.join(require("os").tmpdir(), "k01r8-"));
  try {
    fs.writeFileSync(path.join(tmp, "x.json"), txt);
    const ctxPath = path.join(FX, "real", "context_shymkent.json");
    const code = `import json,sys;sys.path.insert(0,${JSON.stringify(__dirname)});import planv2_ref as R
sc,_=R.import_plan(open(${JSON.stringify(path.join(tmp, "x.json"))},"rb").read(),json.load(open(${JSON.stringify(ctxPath)})))
print(json.dumps(sc))`;
    const py = JSON.parse(cp.execFileSync("python3", ["-c", code], { encoding: "utf8" }));
    eq(py, sc, "Python import of JS export");
  } finally { fs.rmSync(tmp, { recursive: true }); }
});
t("export refuses an invalid scenario object (no partial file)", () => {
  const sc = valid("shy_valid_basic.json", "shymkent"); sc.budget = -1;
  throwsCode(() => P.exportPlan(sc, CTX.shymkent), "bad_budget");
});
t("validated copy is detached from the parsed input", () => {
  const raw = JSON.parse(read("shy_valid_basic.json")); const sc = P.validatePlanScenario(raw, CTX.shymkent);
  raw.control_points[0].weight = 99; raw.candidates.push({}); eq(sc.control_points[0].weight === 99, false); eq(sc.candidates.length, 4);
});

// ---------- atomic store ----------
t("PlanStore: every invalid fixture is rejected without changing the active scenario", () => {
  const st = new P.PlanStore(CTX.shymkent);
  if (!st.importText(read("shy_valid_basic.json").toString("utf8"))) throw new Error(st.message);
  const snap = JSON.stringify(st.active), req = st.request;
  const exp = JSON.parse(fs.readFileSync(path.join(FX, "EXPECTED.json"), "utf8")).fixtures;
  let n = 0;
  for (const [name, e] of Object.entries(exp)) {
    if (e.valid || e.context_city !== "shymkent") continue;
    if (st.importText(new Uint8Array(read(name)))) throw new Error("accepted " + name);
    eq(JSON.stringify(st.active), snap, name); eq(st.request, req, "request id unchanged");
    if (!/не изменён/.test(st.message)) throw new Error("no message"); n++;
  }
  if (n < 20) throw new Error("only " + n + " invalid fixtures exercised");
});
t("PlanStore.edit: invalid edit rolls back, valid edit applies", () => {
  const st = new P.PlanStore(CTX.shymkent); st.importText(read("shy_valid_basic.json").toString());
  const before = JSON.stringify(st.active);
  eq(st.edit((d) => { d.candidates[0].cost = 0; }), false); eq(JSON.stringify(st.active), before);
  eq(st.edit((d) => { d.control_points.push({ id: "cp-99", lon: 0, lat: 0, weight: 1 }); }), false, "outside bbox");
  eq(JSON.stringify(st.active), before);
  eq(st.edit((d) => { d.budget = 9000; }), true); eq(st.active.budget, 9000);
});
t("PlanStore: stale worker answer ignored, city/category switch resets and invalidates pending answer", () => {
  const st = new P.PlanStore(CTX.shymkent); st.importText(read("shy_valid_basic.json").toString());
  const job = st.startOptimization();
  eq(st.receive({ request_id: job.request_id - 1, problem_digest: job.problem_digest }), false, "old request id");
  eq(st.receive({ request_id: job.request_id, problem_digest: "pd1:" + "0".repeat(64) }), false, "foreign digest");
  const job2 = st.startOptimization(); st.edit((d) => { d.budget = 5000; });
  eq(st.receive({ request_id: job2.request_id, problem_digest: job2.problem_digest }), false, "scenario changed after request");
  const job3 = st.startOptimization();
  eq(st.receive({ request_id: job3.request_id, problem_digest: job3.problem_digest, ids: ["cand-01"] }), true);
  eq(st.applyProposal(["cand-01", "cand-02"]), true); eq(st.active.selected_ids, ["cand-01", "cand-02"]); eq(st.proposal, null);
  const job4 = st.startOptimization();
  st.switchCategory("outpatient_clinic"); eq(st.active, null);
  eq(st.receive({ request_id: job4.request_id, problem_digest: job4.problem_digest }), false, "after reset");
  st.importText(read("shy_valid_basic.json").toString()); st.switchContext(CTX.astana); eq(st.active, null);
  if (!/сброшены/.test(st.message)) throw new Error("no reset reason");
  eq(st.importText(read("shy_valid_basic.json").toString()), false, "Shymkent file in Astana context");
});

// ---------- v1 untouched + migration ----------
let X = null, D = null, F = null;
if (APP) { const { loadApp } = require("./load_app.cjs"); ({ data: D, F } = loadApp(APP)); X = require(path.join(path.resolve(APP), "web", "whatif.js")); }
const v1For = (city) => {
  const snap = X.sourceSnapshot(D, city, F), bb = D.cities[city].bbox, mid = (i) => [bb[0] + (bb[2] - bb[0]) * (0.3 + 0.2 * i), bb[1] + (bb[3] - bb[1]) * 0.5];
  return { schema_version: X.SCHEMA, city_id: city, source_snapshot: snap, category: "school",
    control_points: [0, 1].map((i) => ({ id: `p${i}`, lon: mid(i)[0], lat: mid(i)[1] })),
    proposed_object: { id: "proj1", lon: mid(2)[0], lat: mid(2)[1], category: "school", kind: "hypothetical" } };
};
t("v1 city-whatif-v1 still works in the BUILD's whatif.js; v2 import rejects it (separate modes)", () => {
  if (!X) return "SKIP";
  for (const city of ["shymkent", "astana"]) {
    const txt = X.exportScenario(v1For(city), D, F);
    const r = X.importScenario(txt, D, F); eq(r.scenario.schema_version, "city-whatif-v1");
    throwsCode(() => P.importPlan(txt, P.contextFromData(D, city, F)), "unknown_field");   // proposed_object is not a v2 field
    const committed = path.join(FX, "v1", `${city}_v1_from_build_whatif.json`);
    if (!fs.existsSync(committed) || fs.readFileSync(committed, "utf8") !== txt) throw new Error("fixtures/v1 differs from BUILD export: rerun make_v1_fixtures.cjs");
  }
});
t("migrateV1: refuses without explicit budget/cost, keeps user cost exactly, weights=1, validates against v2 context", () => {
  if (!X) return "SKIP";
  for (const city of ["shymkent", "astana"]) {
    const v1 = X.validateScenario(v1For(city), D, F), ctx = P.contextFromData(D, city, F);
    throwsCode(() => P.migrateV1(v1, {}, ctx), "cost_required");
    throwsCode(() => P.migrateV1(v1, { budget: 5000 }, ctx), "cost_required");
    throwsCode(() => P.migrateV1(v1, { budget: 5000, cost: 0 }, ctx), "bad_cost");
    const v2 = P.migrateV1(v1, { budget: 5000, cost: 4321 }, ctx);
    eq(v2.candidates.map((c) => [c.id, c.cost, c.kind]), [["proj1", 4321, "hypothetical"]]);
    eq(v2.control_points.map((p) => p.weight), [1, 1]); eq(v2.source_snapshot, ctx.source_snapshot);
    if (v2.source_snapshot === v1.source_snapshot) throw new Error("v2 must carry its own snapshot");
    const noProj = Object.assign({}, v1, { proposed_object: null });
    eq(P.migrateV1(noProj, { budget: 0 }, ctx).candidates, [], "no project: no cost needed, no candidate invented");
  }
});

console.log(`\n${pass} passed, ${fail} failed, ${skip} skipped`);
process.exitCode = fail ? 1 : 0;
