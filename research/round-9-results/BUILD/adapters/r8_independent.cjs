// Runs independent r8 oracle outputs through THIS build's web/plan.js (our own adapter; no code from those packages runs):
//   K06 @ 58cf899 fixtures/gold_cases.json — 96 gold problems (synthetic + real records with synthetic inputs)
//   K10 @ c8df74b packs/*.json — 37 packs on the real slices + synthetic packs, with expected optimum / Pareto / sensitivity /
//                                manual-plan rows, and invalid-input files (accept / reject).
// Byte copies with sha256: ../review_inputs/MANIFEST.json.
// Adaptation (documented): contexts are built with plan.makeContext from the package's own records/bbox; a non-BUILD
// source_snapshot string (synthetic or another convention) is replaced by the context's snapshot. Real K10 packs use the
// BUILD convention and are run unchanged against the build's data.js. Math is compared, not internal digests.
// Usage (from the repository root): node research/round-9-results/BUILD/adapters/r8_independent.cjs [out.json] [app_root]
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.resolve(__dirname, "../../../..");
const APP = path.resolve(process.argv[3] || path.join(ROOT, "prototypes/city-evidence")), WEB = path.join(APP, "web");
const IN = path.resolve(__dirname, "../review_inputs");
const c0 = {}; vm.createContext(c0); c0.window = c0;
for (const f of ["data.js", "evidence.js"]) vm.runInContext(fs.readFileSync(path.join(WEB, f), "utf8"), c0);
const F = require(path.join(WEB, "facts.js")), PL = require(path.join(WEB, "plan.js")), D = c0.CITY_EVIDENCE;
const J = JSON.stringify, rows = [];
const add = (src, name, ok, detail, note) => rows.push({ src, name, status: ok === null ? "INFO" : ok ? "PASS" : "FAIL", detail: ok ? undefined : detail, note });

function synthCtx(city, bbox, records) {
  const data = { cities: { [city]: { bbox, release: "independent-fixture", files: {}, places: records.map((r) => ({ id: r.id, group: r.group, lon: r.lon, lat: r.lat, name: r.name || null })) } } };
  return PL.makeContext(data, city, F);
}
const M = ["unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost"];
const objOf = (o) => o && { ids: (o.selected_ids || o.ids).slice().sort(), ...Object.fromEntries(M.map((k) => [k, o[k] !== undefined ? o[k] : o.metrics && o.metrics[k]])) };
const ours = (o) => o && { ids: o.ids.slice().sort(), ...Object.fromEntries(M.map((k) => [k, o[k]])) };
const pareto = (p) => (p || []).map((x) => [x.cost, x.weighted_sum_mm, (x.selected_ids || x.ids).slice().sort()]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);

// ---------- K06 gold ----------
const gold = JSON.parse(fs.readFileSync(path.join(IN, "K06/fixtures/gold_cases.json"), "utf8"));
for (const c of gold.cases) {
  try {
    const ctx = synthCtx(c.context.city_id, c.context.bbox, c.context.records);
    const sc = PL.validatePlanScenario({ ...c.scenario, source_snapshot: ctx.source_snapshot }, ctx);
    const r = PL.optimizePlans(ctx, sc, { F }), g = c.gold;
    let ok = r.status === g.status, why = [];
    if (!ok) why.push(`status ${r.status} ≠ ${g.status}`);
    if (g.status === "optimal") {
      if (r.feasible_count !== g.feasible_count) { ok = false; why.push(`feasible ${r.feasible_count} ≠ ${g.feasible_count}`); }
      for (const k of ["mean", "minimax", "coverage"]) if (J(ours(r.objectives[k])) !== J(objOf(g.objectives[k]))) { ok = false; why.push(`${k}: ${J(ours(r.objectives[k]))} ≠ ${J(objOf(g.objectives[k]))}`); }
      if (J(pareto(r.pareto)) !== J(pareto(g.pareto))) { ok = false; why.push("pareto differs"); }
    }
    add("K06", c.case, ok, why.join("; "));
  } catch (e) { add("K06", c.case, false, `threw ${e.code || e.message}`); }
}

// ---------- K10 packs ----------
const pdir = path.join(IN, "K10/packs");
for (const f of fs.readdirSync(pdir).filter((x) => x.endsWith(".json") && x !== "INDEX.json").sort()) {
  const p = JSON.parse(fs.readFileSync(path.join(pdir, f), "utf8"));
  let ctx;
  if (p.kind === "synthetic") ctx = synthCtx(p.city_id, p.synthetic_slice.bbox, p.synthetic_slice.records);
  else ctx = PL.makeContext(D, p.city_id, F);
  const fixSnap = (o) => (p.kind === "synthetic" ? { ...o, source_snapshot: ctx.source_snapshot } : o);
  if (p.kind !== "synthetic") add("K10", `${p.pack_id}: source_snapshot convention = BUILD`, p.scenario.source_snapshot === ctx.source_snapshot, `${p.scenario.source_snapshot} ≠ ${ctx.source_snapshot}`);
  if (p.invalid_cases) {
    for (const ic of p.invalid_cases) {
      let text = ic.raw;
      if (ic.pad_to_bytes) text = text + " ".repeat(Math.max(0, ic.pad_to_bytes - Buffer.byteLength(text)));
      let got;
      try { PL.importPlanScenario(text, (city) => PL.makeContext(D, city, F), F); got = "accepted"; } catch (e) { got = e.code || "error"; }
      const rejected = got !== "accepted";
      const POLICY = { derived_results_forged: ["forged_derived", "intentional policy difference: BUILD rejects derived_results that differ from recomputation (K12 r8 P1; CORE_SPEC allows both)"],
        html_in_ids: ["bad_id", "intentional policy difference: BUILD IDs are letters/digits of any script + _ . - in NFC (r7/r8 rule kept in r9 CORE_SPEC); markup in IDs is refused, other strings are shown as text"] };
      const intentional = POLICY[ic.case_id] && got === POLICY[ic.case_id][0];
      add("K10", `${p.pack_id}/${ic.case_id}`, intentional ? null : rejected === ic.expected.rejected, `expected rejected=${ic.expected.rejected} (${ic.expected.code || "-"}), build ${got}`,
        intentional ? POLICY[ic.case_id][1] : `build code ${got}`);
    }
    continue;
  }
  try {
    const sc = PL.validatePlanScenario(fixSnap(p.scenario), ctx);
    const r = PL.optimizePlans(ctx, sc, { F }), e = p.expected.optimize;
    let ok = r.status === e.status && (e.status !== "optimal" || r.feasible_count === e.feasible_count), why = ok ? [] : [`status/feasible ${r.status}/${r.feasible_count} ≠ ${e.status}/${e.feasible_count}`];
    if (e.status === "optimal") {
      for (const k of ["mean", "minimax", "coverage"]) if (J(ours(r.objectives[k])) !== J(objOf(e.objectives[k]))) { ok = false; why.push(`${k}`); }
      if (J(pareto(r.pareto)) !== J(pareto(e.pareto))) { ok = false; why.push("pareto"); }
    }
    add("K10", `${p.pack_id}: optimize`, ok, why.join("; "));
    if (e.sensitivity) {
      const s = PL.sensitivity(ctx, sc, { F });
      const a = s.map((x) => [x.budget, x.status, x.objectives && ["mean", "minimax", "coverage"].map((k) => ours(x.objectives[k]))]);
      // K10 writes {mean:null,...} for an infeasible budget, BUILD writes objectives:null — same meaning, normalised here
      const b = e.sensitivity.map((x) => [x.budget, x.status, x.objectives && x.status === "optimal" ? ["mean", "minimax", "coverage"].map((k) => objOf(x.objectives[k])) : null]);
      add("K10", `${p.pack_id}: sensitivity`, J(a) === J(b), `${J(a).slice(0, 200)} ≠ ${J(b).slice(0, 200)}`);
    }
    for (const [ref, plan] of Object.entries(p.expected.plans || {})) {
      const ids = plan.metrics.selected_ids, ev = PL.evaluatePlan(ctx, sc, ids);
      const byId = Object.fromEntries(ev.rows.map((x) => [x.id, x]));
      const rowsOk = plan.rows.every((x) => { const y = byId[x.control_point_id]; return y && y.before_mm === x.before_mm && y.after_mm === x.after_mm && y.delta_mm === x.delta_mm
        && J(y.nearest_after) === J(x.nearest_after) && J(y.nearest_before) === J(x.nearest_before); });
      const m = ev.metrics, em = plan.metrics;
      const mOk = M.every((k) => m[k] === em[k]) && ev.feasibility.feasible === plan.feasibility.feasible;
      add("K10", `${p.pack_id}: plan ${ref}`, rowsOk && mOk, J({ m: Object.fromEntries(M.map((k) => [k, m[k]])), em: Object.fromEntries(M.map((k) => [k, em[k]])) }));
    }
  } catch (e) { add("K10", p.pack_id, false, `threw ${e.code || e.message}`); }
}
const sum = (src) => ({ pass: rows.filter((r) => r.src === src && r.status === "PASS").length, fail: rows.filter((r) => r.src === src && r.status === "FAIL").length,
  info: rows.filter((r) => r.src === src && r.status === "INFO").length });
const out = { app_root: path.relative(ROOT, APP), plan_js: "web/plan.js", summary: { K06: sum("K06"), K10: sum("K10") }, rows };
for (const r of rows) if (r.status !== "PASS") console.log(`${r.status} ${r.src} ${r.name}${r.detail ? " — " + String(r.detail).slice(0, 300) : ""}${r.note && r.status === "INFO" ? " — " + r.note : ""}`);
console.log(JSON.stringify(out.summary));
if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(out, null, 1) + "\n");
process.exit(rows.some((r) => r.status === "FAIL") ? 1 : 0);
