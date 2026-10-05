// Runs the independent round-7 v1 fixtures (K01 @ 42e68ef, K11 @ aa9ce4f; byte copies in ../review_inputs, see MANIFEST.json)
// through THIS build's web/whatif.js importScenario. Our own adapter; no code from those packages is executed.
// The only adaptation: each package used its own source_snapshot convention, so its per-city snapshot STRING is replaced
// by the build's real v1 snapshot of the same city (by value, so "foreign snapshot" fixtures stay foreign).
// Usage: node research/round-8-results/BUILD/adapters/r7_independent_fixtures.cjs [out.json]
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.resolve(__dirname, "../../../.."), WEB = path.join(ROOT, "prototypes/city-evidence/web"), IN = path.resolve(__dirname, "../review_inputs");
const ctx = {}; vm.createContext(ctx); ctx.window = ctx;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(WEB, f), "utf8"), ctx);
const F = require(path.join(WEB, "facts.js")), X = require(path.join(WEB, "whatif.js")), D = ctx.CITY_EVIDENCE;
const real = { shymkent: X.sourceSnapshot(D, "shymkent", F), astana: X.sourceSnapshot(D, "astana", F) };
const k11m = JSON.parse(fs.readFileSync(path.join(IN, "K11/MANIFEST.json"), "utf8"));
const map = { "cw1-63d46116f7293e67b2b0ca63e217b9ec": real.shymkent, "cw1-94f62073b48178da3d5dedfbe8e944c4": real.astana,
  [k11m.cities.shymkent.source_snapshot]: real.shymkent, [k11m.cities.astana.source_snapshot]: real.astana };
const adapt = (buf) => { let t = buf.toString("utf8"); for (const [a, b] of Object.entries(map)) t = t.split(a).join(b); return t; };
const run = (buf) => { try { X.importScenario(adapt(buf), D, F); return "accept"; } catch (e) { return e.code || "error"; } };
const rows = [];
const k01e = JSON.parse(fs.readFileSync(path.join(IN, "K01/EXPECTED.json"), "utf8"));
for (const [file, e] of Object.entries(k01e)) {
  if (file === "note") continue;
  const got = run(fs.readFileSync(path.join(IN, "K01", file)));
  rows.push({ slot: "K01", file, expected: e.valid ? "accept" : "reject:" + (e.code || e.code_one_of.join("|")), got, agree: e.valid === (got === "accept") });
}
for (const f of k11m.files) {
  const got = run(fs.readFileSync(path.join(IN, "K11", f.file)));
  rows.push({ slot: "K11", file: f.file, expected: f.expected === "accept" ? "accept" : "reject:" + f.expected, got, agree: (f.expected === "accept") === (got === "accept"), note: f.note });
}
const out = { build_web: "prototypes/city-evidence/web (whatif.js)", adaptation: "snapshot strings replaced by value with the build's real v1 snapshot", agree: rows.filter((r) => r.agree).length, total: rows.length, rows };
for (const r of rows) console.log(`${r.agree ? "AGREE   " : "DIFFERS "} ${r.slot} ${r.file}: expected ${r.expected}, build ${r.got}`);
console.log(`${out.agree}/${out.total} agree`);
if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(out, null, 1) + "\n");
