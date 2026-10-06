// K03 r9: headless-прогон resilience_cases.js (без DOM) на контексте НАСТОЯЩЕГО plan.js сборки.
//   node cases_runner.cjs <request.json> [<resilience_cases.js>]
// request = {app_root, cases: [{id, op, city, category, ...}]}; печатает {results: [{id, ok, result | error:{code, path}}], integrity}.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
const req = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const RC = require(path.resolve(process.argv[3] || path.join(__dirname, "resilience_cases.js")));
const W = path.join(req.app_root, "web");
const fileSha = (f) => crypto.createHash("sha256").update(fs.readFileSync(path.join(W, f))).digest("hex");
const before = { data: fileSha("data.js"), evidence: fileSha("evidence.js") };
const box = {}; vm.createContext(box); box.window = box;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), box, { filename: f });
globalThis.CITY_OBS = box.CITY_OBS;
const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js"));
const D = box.CITY_EVIDENCE, EV = box.CITY_OBS;
const dataJson = JSON.stringify(D), evJson = JSON.stringify(EV);
const index = RC.sourceIndex(D);
const ctxs = new Map(), cats = new Map();
const ctxOf = (city) => { if (!ctxs.has(city)) ctxs.set(city, PL.makeContext(D, city, F)); return ctxs.get(city); };
const catOf = (city, cat) => { const k = city + "|" + cat; if (!cats.has(k)) cats.set(k, RC.sourceCatalog(D, EV, ctxOf(city), cat, F)); return cats.get(k); };
const plain = (v) => JSON.parse(JSON.stringify(v));
const deepFrozen = (o) => !o || typeof o !== "object" || (Object.isFrozen(o) && Object.values(o).every(deepFrozen));
const mutationBlocked = (o) => { try { (function () { "use strict"; o.records ? o.records[0].lon = 0 : o.cases[0].label = "x"; })(); return false; } catch (e) { return e instanceof TypeError; } };

const out = [];
for (const c of req.cases) {
  try {
    const cat = c.category ? catOf(c.city, c.category) : null;
    const o = { ...(c.opts || {}), index };
    if (c.candidate_ids) o.candidateIds = c.candidate_ids;
    let result;
    switch (c.op) {
      case "catalog": result = { catalog: plain(cat), frozen: deepFrozen(cat), mutation_blocked: mutationBlocked(cat) }; break;
      case "groups": result = RC.colocatedGroups(EV, cat); break;
      case "single": result = RC.singleCase(cat, c.source_id, o); break;
      case "group": result = RC.groupCase(cat, c.source_ids, o); break;
      case "colocated": result = RC.colocatedCase(EV, cat, c.index, o); break;
      case "validate": result = RC.validateCases(cat, c.cases, { index, candidateIds: c.candidate_ids }); break;
      case "envelope": result = RC.checkEnvelopeShape(c.envelope) && "ok"; break;
      case "digest": result = RC.exclusionDigest(cat, RC.validateCases(cat, c.cases, { index }).cases, F); break;
      case "manifest": {
        const m = RC.exclusionManifest(cat, RC.validateCases(cat, c.cases, { index, candidateIds: c.candidate_ids }), F, c.build || null);
        result = { manifest: plain(m), frozen: deepFrozen(m), mutation_blocked: mutationBlocked(m) };
        break;
      }
      case "view": {
        const ctx = ctxOf(c.city), v = RC.caseView(ctx, c.disabled);
        result = { source_snapshot: v.source_snapshot, ctx_snapshot: ctx.source_snapshot, place_ids: v.places.map((p) => p.id),
          ctx_place_count: ctx.places.length, frozen: Object.isFrozen(v) && Object.isFrozen(v.places) };
        break;
      }
      case "probe": {  // вызов каждой функции, создающей случаи, БЕЗ явного выбора: случай не должен появиться
        const tries = { singleCase: () => RC.singleCase(cat, undefined, { id: "p", index }), groupCase: () => RC.groupCase(cat, undefined, { id: "p", index }),
          colocatedCase: () => RC.colocatedCase(EV, cat, undefined, { id: "p", index }), validateCases: () => RC.validateCases(cat, undefined, { index }),
          colocatedGroups: () => RC.colocatedGroups(EV, cat), sourceCatalog: () => RC.sourceCatalog(D, EV, ctxOf(c.city), c.category, F) };
        result = Object.fromEntries(Object.entries(tries).map(([fn, f]) => { try { const r = plain(f()); return [fn, { created: /"disabled_source_ids":\["/.test(JSON.stringify(r)), status: r && r.status || null }]; }
          catch (e) { if (!(e instanceof RC.CaseError)) throw e; return [fn, { created: false, error: e.code }]; } }));
        result.exported = Object.keys(RC).filter((k) => typeof RC[k] === "function").sort();
        break;
      }
      default: throw new Error("unknown op " + c.op);
    }
    out.push({ id: c.id, ok: true, result: plain(result) });
  } catch (e) {
    if (!(e instanceof RC.CaseError)) { out.push({ id: c.id, ok: false, crash: String(e && e.stack || e).slice(0, 400) }); continue; }
    out.push({ id: c.id, ok: false, error: { code: e.code, path: e.path } });
  }
}
const integrity = { file_unchanged: fileSha("data.js") === before.data && fileSha("evidence.js") === before.evidence,
  loaded_unchanged: JSON.stringify(D) === dataJson && JSON.stringify(EV) === evJson,
  snapshots: Object.fromEntries([...ctxs].map(([city, ctx]) => [city, { ctx: ctx.source_snapshot, recomputed: PL.sourceSnapshot(D, city, F) }])) };
process.stdout.write(JSON.stringify({ results: out, integrity }));
