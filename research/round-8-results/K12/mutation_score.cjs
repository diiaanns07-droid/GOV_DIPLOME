// K12 round 8, stage 3: mutation score of plan_fuzz.cjs. Runs the fuzzer once on the unmodified reference (must PASS)
// and once per injected bug from adapters/mutant_adapter.cjs (must FAIL = "killed"). Each run is a child process with
// a wall-clock limit, so a mutant that freezes is reported, not hung on.
//   node mutation_score.cjs --app-root <dir> [--cases 200] [--seed 12] [--only a,b] [--repro-dir repro/mutants] [--out r.json]
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");
const { spawnSync } = require("child_process");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const HERE = __dirname;
const APP = path.resolve(opt("--app-root", ""));
const CASES = opt("--cases", "200"), SEED = opt("--seed", "12");
const REPRO = path.resolve(opt("--repro-dir", path.join(HERE, "repro", "mutants")));
const OUT = opt("--out");
const { MUTANTS } = require("./adapters/mutant_adapter.cjs");
const only = opt("--only", null);
const names = only ? only.split(",") : Object.keys(MUTANTS);

function fuzz(adapter, mutant, reproDir) {
  const tmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "k12ms_")), "r.json");
  const t0 = Date.now();
  const r = spawnSync(process.execPath, [path.join(HERE, "plan_fuzz.cjs"), "--app-root", APP, "--adapter", adapter, "--seed", SEED,
    "--cases", CASES, "--max-ms", "60000", "--repro-dir", reproDir, "--out", tmp],
    { encoding: "utf8", timeout: 180000, env: { ...process.env, K12_MUTANT: mutant || "" } });
  const ms = Date.now() - t0;
  let rep = null;
  try { rep = JSON.parse(fs.readFileSync(tmp, "utf8")); } catch (e) { /* no report */ }
  fs.rmSync(path.dirname(tmp), { recursive: true, force: true });
  return { status: r.status, error: r.error ? r.error.code : null, stderr: (r.stderr || "").slice(0, 300), ms, rep };
}

const rows = [];
const ctl = fuzz(path.join(HERE, "adapters", "reference_v2_adapter.cjs"), "", fs.mkdtempSync(path.join(os.tmpdir(), "k12ctl_")));
const control = { verdict: ctl.rep ? ctl.rep.summary.verdict : "ERROR", failures: ctl.rep ? ctl.rep.summary.failures : null, ms: ctl.ms };
console.log(`control (reference, no bug): ${control.verdict} in ${ctl.ms} ms`);
for (const name of names) {
  const r = fuzz(path.join(HERE, "adapters", "mutant_adapter.cjs"), name, path.join(REPRO, name));
  let verdict, detail = {};
  if (!r.rep) { verdict = "ERROR"; detail.error = r.error || r.stderr; }
  else {
    const f = r.rep.failures;
    verdict = r.rep.summary.verdict === "FAIL" ? "KILLED" : "SURVIVED";
    const kinds = r.rep.summary.failures_by_property || {};
    const shr = f.filter((x) => x.minimal).sort((a, b) => (a.minimal.points + a.minimal.candidates) - (b.minimal.points + b.minimal.candidates))[0];
    detail = { failures: r.rep.summary.failures, caught_by: kinds, first: f[0] ? `${f[0].kind}/${f[0].property} ${f[0].case}: ${f[0].message}`.slice(0, 200) : null,
               smallest_repro: shr ? { file: shr.repro, points: shr.minimal.points, candidates: shr.minimal.candidates, shrink_steps: shr.shrink_steps } : null,
               limits: r.rep.summary.limits };
  }
  rows.push({ mutant: name, bug: MUTANTS[name].bug, verdict, ms: r.ms, ...detail });
  console.log(`${verdict.padEnd(8)} ${name.padEnd(24)} ${String(r.ms).padStart(6)} ms  ${detail.first || detail.error || ""}`);
}
const killed = rows.filter((r) => r.verdict === "KILLED").length;
const summary = { seed: Number(SEED), cases: Number(CASES), control: control.verdict, mutants: rows.length, killed,
  survived: rows.filter((r) => r.verdict === "SURVIVED").map((r) => r.mutant), errors: rows.filter((r) => r.verdict === "ERROR").map((r) => r.mutant),
  verdict: control.verdict === "PASS" && killed === rows.length ? "PASS" : "FAIL" };
console.log(JSON.stringify(summary));
if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, control, mutants: rows }, null, 1) + "\n");
process.exit(summary.verdict === "PASS" ? 0 : 1);
