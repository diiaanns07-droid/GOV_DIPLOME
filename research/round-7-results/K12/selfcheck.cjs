// K12 round 7: checks the stress test itself — it must pass a correct importer and catch bad ones.
//   node selfcheck.cjs --app-root <prototypes/city-evidence copy>
"use strict";
const { spawnSync } = require("child_process"), fs = require("fs"), os = require("os"), path = require("path");
const i = process.argv.indexOf("--app-root");
if (i < 0) { console.error("usage: node selfcheck.cjs --app-root <dir>"); process.exit(2); }
const APP = process.argv[i + 1];
const run = (adapter) => {
  const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "k12r7_")), "r.json");
  const p = spawnSync(process.execPath, [path.join(__dirname, "whatif_import_stress.cjs"), "--app-root", APP,
    "--adapter", path.join(__dirname, "adapters", adapter), "--out", out], { encoding: "utf8" });
  const r = JSON.parse(fs.readFileSync(out, "utf8"));
  fs.rmSync(path.dirname(out), { recursive: true, force: true });
  return { exit: p.status, ...r };
};
let bad = 0;
const check = (name, ok, detail) => { if (!ok) bad++; console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : " — " + JSON.stringify(detail)}`); };

const ref = run("reference_adapter.cjs");
check("reference importer: all fixtures pass, exit 0", ref.exit === 0 && ref.summary.pass === ref.summary.total && !ref.summary.fail.length, ref.summary);
check("reference importer: export round-trip E01 present and passing", ref.results.some((r) => r.id === "E01" && r.status === "PASS"));
check("reference importer: no network attempts", ref.summary.network_attempts === 0, ref.summary.network_attempts);

const naive = run("naive_adapter.cjs");
const nf = new Set(naive.summary.fail);
check("naive importer: exit 1", naive.exit === 1, naive.exit);
for (const [id, why] of [["P03", "trusts imported results"], ["N04", "accepts 1e999"], ["N05", "duplicate key"], ["N08", "duplicate ID"],
                         ["N11", "foreign snapshot"], ["N24", "outside bbox"], ["N30", "11 points"], ["N32", "two projects"],
                         ["N34", "> 256 KiB"], ["N36", "HTML in ID"]])
  check(`naive importer caught: ${id} (${why})`, nf.has(id), naive.summary.fail);
check("naive importer caught: state mutation", naive.results.some((r) => (r.failed_checks || []).includes("passed_state_not_mutated")));

const fetching = run("fetching_adapter.cjs");
check("fetching importer: exactly N14 and N38 fail", JSON.stringify(fetching.summary.fail) === JSON.stringify(["N14", "N38"]), fetching.summary.fail);
check("fetching importer: failures are no_network", fetching.results.filter((r) => r.status === "FAIL").every((r) => r.failed_checks.includes("no_network")));
check("fetching importer: 2 attempts trapped, none reached", fetching.summary.network_attempts === 2, fetching.summary.network_attempts);

console.log(bad ? `selfcheck: ${bad} failed` : "selfcheck: all passed");
process.exit(bad ? 1 : 0);
