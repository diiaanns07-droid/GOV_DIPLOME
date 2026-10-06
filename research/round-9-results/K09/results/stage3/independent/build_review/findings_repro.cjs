// Consolidated reproductions for the review of resilience.js @ 33cc635. Usage: /opt/node22/bin/node findings_repro.cjs
const { F, X, PL, RS, code, ctxs, mkEnv, J } = require("./h.cjs");
const sh = ctxs.shymkent, ctxFor = (c) => ctxs[c];
// F1a: candidate limit bypass via Proxy array (length 5 for the two limit checks, 18 for v2's map)
{ const e = mkEnv("shymkent", "school", 18, 6, { budget: 1000, max: 5 }); const arr = e.plan.candidates; let reads = 0;
  e.plan.candidates = new Proxy(arr, { get(t, p, r) { if (p === "length") return reads++ < 2 ? 5 : t.length; return Reflect.get(t, p, r); } });
  const r = RS.optimizeResilience(sh, e, { F }); console.log("F1a", r.status, "candidates", 18, "total_subsets", r.total_subsets); }
// F1b: case limit bypass via Proxy (length 1 for the two checks, 30 for map)
{ const e = mkEnv("shymkent", "school", 6, 5); const many = Array.from({ length: 30 }, (_, k) => ({ ...e.cases[0], id: "m" + k })); let reads = 0;
  e.cases = new Proxy(many, { get(t, p, r) { if (p === "length") return reads++ < 2 ? 1 : t.length; return Reflect.get(t, p, r); } });
  const r = RS.optimizeResilience(sh, e, { F }); console.log("F1b", r.status, "cases incl. base", r.cases.length); }
// F1c: exclusion list that is empty after the >=1 check
{ const e = mkEnv("shymkent", "school", 4, 3); let reads = 0;
  e.cases[0].disabled_source_ids = new Proxy([], { get(t, p, r) { if (p === "length") return reads++ < 2 ? 1 : t.length; return Reflect.get(t, p, r); } });
  console.log("F1c", J(RS.validateResilience(e, sh).cases[0].disabled_source_ids)); }
// F1d: getter on plan.candidates (5 for the resilience check, 16 for v2)
{ const e = mkEnv("shymkent", "school", 16, 6, { budget: 1000, max: 5 }); const all = e.plan.candidates, few = all.slice(0, 5); let n = 0;
  Object.defineProperty(e.plan, "candidates", { enumerable: true, get() { return n++ < 2 ? few : all; } });
  const r = RS.optimizeResilience(sh, e, { F }); console.log("F1d", r.status, "total_subsets", r.total_subsets); }
// F2: label with U+FFFD: own export cannot be re-imported
{ const e = mkEnv("shymkent", "school", 4, 3); e.cases[0].label = "a�b";
  const t = RS.exportResilience(sh, e); console.log("F2 validate", code(() => RS.validateResilience(e, sh)), "export→import", code(() => RS.importResilience(t, ctxFor)));
  const esc = t.replace("a�b", "a\\ufffdb"); const imp = RS.importResilience(esc, ctxFor); console.log("F2 import(\\ufffd)", "ok", "→ export→import", code(() => RS.importResilience(RS.exportResilience(imp.ctx, imp.envelope), ctxFor))); }
// F3: explanation/results not bound to the envelope
{ const A = RS.validateResilience(mkEnv("shymkent", "school", 6, 5, { seed: 3, cases: [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]] }), sh);
  const B = RS.validateResilience(mkEnv("shymkent", "school", 6, 5, { seed: 3, cases: [[0], [0]] }), sh);
  const rA = RS.optimizeResilience(sh, A, { F }), mB = RS.evaluateResilience(sh, B, []);
  console.log("F3 explain(B, manualB, resultA):", code(() => RS.explainResilience(B, mB, rA)), "| digest in evaluate output:", Object.keys(mB).some((k) => /digest/.test(k)), "| optimize w/o F digest:", RS.optimizeResilience(sh, B).resilience_problem_digest); }
// F4: evaluateResilience with non-array selectedIds -> untyped TypeError
console.log("F4", code(() => RS.evaluateResilience(sh, mkEnv("shymkent", "school", 4, 3), undefined)));
// F5: label rules: invisible-only and bidi-override labels accepted
for (const [n, l] of [["ZWSP only", "​"], ["RLO", "a‮b"], ["lone surrogate", "a\ud800b"]]) { const e = mkEnv("shymkent", "school", 4, 3); e.cases[0].label = l; console.log("F5", n, code(() => RS.validateResilience(e, sh))); }
