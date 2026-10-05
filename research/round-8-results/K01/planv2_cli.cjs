#!/usr/bin/env node
// city-plan-v2 CLI (K01 round 8). Context from an extracted prototype (--app-root) or a context file (--context).
//   node planv2_cli.cjs context  --app-root APP --city shymkent|astana
//   node planv2_cli.cjs validate FILE --city C (--app-root APP | --context ctx.json)   # exit 0 valid, 1 rejected, 2 usage
//   node planv2_cli.cjs digest   FILE --city C (--app-root APP | --context ctx.json)
//   node planv2_cli.cjs export   FILE --city C (--app-root APP | --context ctx.json) [--out OUT.json]   # canonical re-export, derived dropped
//   node planv2_cli.cjs migrate  V1.json --city C --app-root APP --budget N [--cost N] [--out OUT.json]  # explicit costs only
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const P = require("./planv2.js");
const argv = process.argv.slice(2);
const opt = (k) => { const i = argv.indexOf("--" + k); return i >= 0 ? argv[i + 1] : undefined; };
const cmd = argv[0], file = argv[1] && !argv[1].startsWith("--") ? argv[1] : null;
const sha256hex = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
const out = (o, code = 0) => { process.stdout.write(JSON.stringify(o, null, 1) + "\n"); process.exit(code); };
const usage = () => { process.stderr.write(fs.readFileSync(__filename, "utf8").split("\n").slice(1, 7).join("\n") + "\n"); process.exit(2); };
if (!cmd || !opt("city")) usage();
let ctx, app = null;
if (opt("app-root")) {
  const { loadApp } = require("./load_app.cjs"); app = loadApp(opt("app-root"));
  ctx = P.contextFromData(app.data, opt("city"), app.F);
} else if (opt("context")) {
  const c = JSON.parse(fs.readFileSync(opt("context"), "utf8"));
  if (c.city_id !== opt("city")) out({ valid: false, code: "foreign_city", detail: "context file is for " + c.city_id }, 1);
  ctx = { city_id: c.city_id, bbox: c.bbox, source_snapshot: c.source_snapshot, sha256hex };
} else usage();
if (cmd === "context") out({ city_id: ctx.city_id, bbox: ctx.bbox, source_snapshot: ctx.source_snapshot, metric_version: P.METRIC_VERSION });
if (!file) usage();
const write = (txt) => { if (opt("out")) { fs.writeFileSync(opt("out"), txt); out({ written: path.basename(opt("out")), bytes: Buffer.byteLength(txt) }); } process.stdout.write(txt); process.exit(0); };
try {
  if (cmd === "migrate") {
    if (!app) usage();
    const X = require(path.join(path.resolve(opt("app-root")), "web", "whatif.js"));
    const v1 = X.importScenario(fs.readFileSync(file, "utf8"), app.data, app.F).scenario;
    const num = (k) => (opt(k) === undefined ? undefined : Number(opt(k)));
    write(P.exportPlan(P.migrateV1(v1, { budget: num("budget"), cost: num("cost") }, ctx), ctx));
  }
  const r = P.importPlan(new Uint8Array(fs.readFileSync(file)), ctx);
  if (cmd === "validate") out({ valid: true, notes: r.notes, control_points: r.scenario.control_points.length, candidates: r.scenario.candidates.length });
  if (cmd === "digest") out({ valid: true, problem_digest: P.problemDigest(r.scenario, ctx), scenario_digest: P.scenarioDigest(r.scenario, ctx), metric_version: P.METRIC_VERSION });
  if (cmd === "export") write(P.exportPlan(r.scenario, ctx));
  usage();
} catch (e) {
  if (e instanceof P.PlanV2Error || (e && e.code && e.detail)) out({ valid: false, code: e.code, detail: e.detail }, 1);
  throw e;
}
