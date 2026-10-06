// K12 r9 regression checks for web/resilience.js, resilience-ui.js label rule and the exported plan.js internals (findings on 33cc635/e1cbc3f). Headless, no DOM.
// Usage: node tests/resilience_k12_guard.cjs
const fs = require("fs"), path = require("path"), vm = require("vm");
const W = path.join(__dirname, "..", "web");
const ctx0 = {}; vm.createContext(ctx0); ctx0.window = ctx0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(W, f), "utf8"), ctx0, { filename: f });
const F = require(path.join(W, "facts.js")), PL = require(path.join(W, "plan.js")), RS = require(path.join(W, "resilience.js"));
let fails = 0;
const check = (name, ok, detail) => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(detail).slice(0, 300) : "")); };
const code = (fn) => { try { fn(); return "accepted"; } catch (e) { return e.code || `untyped ${e.name}`; } };
const J = JSON.stringify;

// synthetic equator slice (same idea as the hand fixtures of tests/plan.cjs): two school records
const EQ = [{ id: "A", group: "school", lon: 0.0, lat: 0.0 }, { id: "B", group: "school", lon: 0.02, lat: 0.0 }];
const ctx = PL.makeContext({ cities: { "synthetic-eq": { bbox: [-0.1, -0.1, 0.1, 0.1], release: "synthetic", files: {}, places: EQ } } }, "synthetic-eq", F);
const A = "ﬀ", B = "\u{1D538}";   // ﬀ (U+FB00) and 𝔸 (U+1D538): letters, NFC; UTF-16 order puts 𝔸 first
const plan = (cands, extra = {}) => ({ schema_version: PL.SCHEMA, city_id: "synthetic-eq", source_snapshot: ctx.source_snapshot, category: "school",
  control_points: [{ id: "P1", lon: 0.0, lat: 0.001, weight: 1 }], candidates: cands, budget: 5, max_selected: 1, coverage_radius_m: 500,
  required_ids: [], excluded_ids: [], selected_ids: [], ...extra });
const cand = (id, lon = 0.0005, lat = 0.0005) => ({ id, lon, lat, category: "school", kind: "hypothetical", cost: 5 });
const env = (p, cases) => ({ schema_version: RS.SCHEMA, plan: p, cases });
const tie = plan([cand(A), cand(B)]);
const tieEnv = env(tie, [{ id: `${A}1`, label: "без всех записей ﬀ", disabled_source_ids: ["A", "B"] }, { id: `${B}1`, label: "без всех записей 𝔸", disabled_source_ids: ["A", "B"] }]);

check("evaluateResilience(ctx, env, null): typed bad_shape, not TypeError", code(() => RS.evaluateResilience(ctx, tieEnv, null)) === "bad_shape");
check("evaluateResilience(ctx, env, \"c1\"): typed refusal", code(() => RS.evaluateResilience(ctx, tieEnv, A)) !== "accepted" && !code(() => RS.evaluateResilience(ctx, tieEnv, A)).startsWith("untyped"));
const many = plan(Array.from({ length: 20 }, (_, k) => cand(`c${k}`, 0.0001 * k, 0.0005)), { max_selected: 5, budget: 100 });
check("PL.internal.createSearch with 20 unvalidated candidates: too_many_candidates before enumeration",
  code(() => PL.internal.createSearch(ctx, many, { F })) === "too_many_candidates");
const lab = (label) => code(() => RS.validateResilience(env(tie, [{ id: "k1", label, disabled_source_ids: ["A"] }]), ctx));
check("label with U+202E (bidi override): bad_label", lab("abc‮dcba") === "bad_label");
check("label with U+2066 (bidi isolate): bad_label", lab("abc⁦x") === "bad_label");
check("label with a lone high surrogate: bad_label", lab("x\uD800y") === "bad_label");
check("label with a lone low surrogate: bad_label", lab("x\uDC00y") === "bad_label");
check("label with emoji (valid surrogate pair), Kazakh and HTML text: accepted", lab("😀 Мектеп «жабық» <b>&</b>") === "accepted");
// one label rule for the module and the editor (resilience-ui.js setLabel uses RS.isLabel)
check("RS.isLabel exported; same verdicts as validateResilience (U+2028, U+202E, lone surrogate refused; emoji/Kazakh/HTML text accepted)",
  typeof RS.isLabel === "function" && ["a\u2028b", "abc\u202Edcba", "x\uD800y", "   ", "Ж".repeat(121)].every((v) => RS.isLabel(v) === false && lab(v) === "bad_label")
    && ["😀 Мектеп «жабық» <b>&</b>", "Ж".repeat(100) + "😀".repeat(20)].every((v) => RS.isLabel(v) === true && lab(v) === "accepted"));
// JS order at an exact tie (documents the convention the oracles must follow; see tests/test_id_order.py)
check("v2 mean at an exact tie picks 𝔸 (UTF-16 order, JS string comparison)", J(PL.optimizePlans(ctx, tie, { F }).objectives.mean.ids) === J([B]));
const r = RS.optimizeResilience(ctx, tieEnv, { F });
check("resilience nominal/robust at an exact tie pick 𝔸; worst_case_ids in UTF-16 order",
  J([r.nominal.selected_ids, r.robust.selected_ids]) === J([[B], [B]]) && J(r.robust.worst_case_ids) === J(["base", `${B}1`, `${A}1`].filter((x) => r.robust.worst_case_ids.includes(x))), J(r.robust.worst_case_ids));

console.log(fails ? `${fails} FAILED` : "all K12 r9 resilience guard checks passed");
process.exit(fails ? 1 : 0);
