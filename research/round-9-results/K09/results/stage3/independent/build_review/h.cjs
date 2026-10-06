// harness: load module like product tests do
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = "/tmp/claude-0/-home-user-GOV-DIPLOME/e220e412-94a1-5250-b65e-0d50545b9515/scratchpad/k09_build_33cc635/prototypes/city-evidence/web";
const c0 = {}; vm.createContext(c0); c0.window = c0;
vm.runInContext(fs.readFileSync(path.join(W, "data.js"), "utf8"), c0, { filename: "data.js" });
const F = require(path.join(W, "facts.js")), X = require(path.join(W, "whatif.js")), PL = require(path.join(W, "plan.js")), RS = require(path.join(W, "resilience.js"));
const D = c0.CITY_EVIDENCE;
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || ("THROW:" + e.constructor.name + ":" + e.message); } };
const ctxs = { shymkent: PL.makeContext(D, "shymkent", F), astana: PL.makeContext(D, "astana", F) };
// build a valid envelope in a city/category
function mkEnv(city, cat, nCand, nPts, opts = {}) {
  const ctx = ctxs[city], [w, s, e, n] = ctx.bbox.length === 4 ? ctx.bbox : [ctx.bbox[0][0], ctx.bbox[0][1], ctx.bbox[1][0], ctx.bbox[1][1]];
  let seed = opts.seed || 1; const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  const lon = () => w + (e - w) * (0.05 + 0.9 * rnd()), lat = () => s + (n - s) * (0.05 + 0.9 * rnd());
  const control_points = Array.from({ length: nPts }, (_, k) => ({ id: "P" + k, lon: lon(), lat: lat(), weight: 1 + Math.floor(rnd() * (opts.wmax || 5)) }));
  const candidates = Array.from({ length: nCand }, (_, k) => ({ id: "C" + k, lon: lon(), lat: lat(), category: cat, kind: "hypothetical", cost: 1 + Math.floor(rnd() * (opts.cmax || 10)) }));
  const src = ctx.places.filter((p) => p.group === cat).map((p) => p.id);
  const cases = (opts.cases || [[0, 1], [2], [3, 4, 5]]).map((ix, k) => ({ id: "k" + k, label: "case " + k, disabled_source_ids: ix.map((i) => src[i % src.length]).filter((v, i, a) => a.indexOf(v) === i) }));
  return { schema_version: RS.SCHEMA, plan: { schema_version: PL.SCHEMA, city_id: city, source_snapshot: ctx.source_snapshot, category: cat, control_points, candidates,
    budget: opts.budget ?? 20, max_selected: opts.max ?? 3, coverage_radius_m: 500, required_ids: opts.req || [], excluded_ids: opts.exc || [], selected_ids: opts.sel || [] }, cases };
}
module.exports = { F, X, PL, RS, D, code, ctxs, mkEnv, J: JSON.stringify };
