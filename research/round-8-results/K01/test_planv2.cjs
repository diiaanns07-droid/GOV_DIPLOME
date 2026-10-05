// K01 round 8: headless Node tests for planv2.js (no DOM). Cross-checks every fixture against the Python oracle.
//   node test_planv2.cjs [--app-root APP]      (APP = extracted prototypes/city-evidence; enables real-context checks)
const fs = require("fs"), path = require("path"), crypto = require("crypto"), cp = require("child_process");
const P = require("./planv2.js");
const HERE = __dirname, FX = path.join(HERE, "fixtures");
const ai = process.argv.indexOf("--app-root"), APP = ai > 0 ? process.argv[ai + 1] : null;
const sha256hex = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
let pass = 0, fail = 0, skip = 0;
const t = (name, fn) => { try { const r = fn(); if (r === "SKIP") { skip++; console.log("SKIP", name); } else { pass++; console.log("PASS", name); } }
  catch (e) { fail++; console.log("FAIL", name, "—", e.message); } };
const eq = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m || ""} ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const throwsCode = (fn, code) => { try { fn(); } catch (e) { if (e instanceof P.PlanV2Error && e.code === code) return; throw new Error(`expected ${code}, got ${e.code || e.message}`); } throw new Error(`expected ${code}, accepted`); };

const EXP = JSON.parse(fs.readFileSync(path.join(FX, "EXPECTED.json"), "utf8"));
const ctxFile = (c) => { const x = JSON.parse(fs.readFileSync(path.join(FX, "real", `context_${c}.json`), "utf8")); return { city_id: c, bbox: x.bbox, source_snapshot: x.source_snapshot, sha256hex }; };
const CTX = { shymkent: ctxFile("shymkent"), astana: ctxFile("astana") };
const read = (n) => new Uint8Array(fs.readFileSync(path.join(FX, "synthetic", n)));

// --- manifest of fixtures ---
t("fixtures MANIFEST sha256", () => {
  const m = JSON.parse(fs.readFileSync(path.join(FX, "MANIFEST.json"), "utf8"));
  for (const f of m.files) { const b = fs.readFileSync(path.join(FX, f.path)); eq([b.length, crypto.createHash("sha256").update(b).digest("hex")], [f.bytes, f.sha256], f.path); }
});

// --- real context equals the prototype's slice ---
t("real contexts == contextFromData(app data.js, facts.js)", () => {
  if (!APP) return "SKIP";
  const { loadApp } = require("./load_app.cjs");
  const { data, F } = loadApp(APP);
  for (const c of ["shymkent", "astana"]) { const x = P.contextFromData(data, c, F); eq([x.source_snapshot, x.bbox], [CTX[c].source_snapshot, CTX[c].bbox], c); }
  eq(F.sha256hex("abc"), sha256hex("abc"), "facts.sha256hex");
});

// --- every fixture: JS verdict == EXPECTED == Python oracle, digests JS == Python ---
const py = JSON.parse(cp.execFileSync("python3", [path.join(HERE, "planv2_ref.py"), "batch", FX], { encoding: "utf8" }));
for (const [name, e] of Object.entries(EXP.fixtures)) {
  t(`fixture ${name}`, () => {
    let got;
    try { const r = P.importPlan(read(name), CTX[e.context_city]); got = { valid: true, notes: r.notes.length, problem_digest: P.problemDigest(r.scenario, CTX[e.context_city]), scenario_digest: P.scenarioDigest(r.scenario, CTX[e.context_city]) }; }
    catch (err) { if (!(err instanceof P.PlanV2Error)) throw err; got = { valid: false, code: err.code }; }
    eq([got.valid, got.code], [e.valid, e.code], "vs EXPECTED");
    eq(got, py[name], "JS vs Python");
  });
}
console.log(`\n${pass} passed, ${fail} failed, ${skip} skipped`);
if (require.main === module) process.exitCode = fail ? 1 : 0;
module.exports = { t, eq, throwsCode, CTX, read, P, sha256hex, counts: () => ({ pass, fail, skip }) };
