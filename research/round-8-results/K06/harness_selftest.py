"""Self-test of the JS comparison path (needs Node): export problems -> run_candidate_node.cjs -> compare_candidate.
  python3 harness_selftest.py [--problems fixtures/gold_cases.json]
Uses two TEST-ONLY modules written to a temp dir (neither is an implementation of city-plan-v2):
  * wrong stub  -> every case must FAIL and the comparator must exit 1;
  * echo module returning precomputed oracle answers (keyed by context+scenario) -> every case PASS, exit 0.
"""
import argparse, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plan_oracle as O

STUB = 'exports.optimizePlans = (c, s) => { if (s.candidates.length > 8) throw new Error("stub"); return {status: "optimal", objectives: {}, pareto: [], feasible_count: 0}; };\n'
ECHO = '''const T = require("./echo_table.json");
const canon = (o) => Array.isArray(o) ? "[" + o.map(canon).join(", ") + "]" : o && typeof o === "object" ? "{" + Object.keys(o).sort().map((k) => JSON.stringify(k) + ": " + canon(o[k])).join(", ") + "}" : JSON.stringify(o);
exports.optimizePlans = (c, s) => { const r = T[canon([c, s])]; if (!r) throw new Error("no echo"); return JSON.parse(JSON.stringify(r)); };
'''


def js_numbers(o):
    if isinstance(o, float) and o.is_integer():
        return int(o)
    if isinstance(o, dict):
        return {k: js_numbers(v) for k, v in o.items()}
    if isinstance(o, list):
        return [js_numbers(x) for x in o]
    return o


def run(cmd):
    return subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--problems", default=os.path.join(HERE, "fixtures", "gold_cases.json"))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        probs = os.path.join(d, "problems.json")
        assert run([sys.executable, "compare_candidate.py", "--problems", a.problems, "--export", probs]).returncode == 0
        cases = json.load(open(probs))["cases"]
        open(os.path.join(d, "stub.js"), "w").write(STUB)
        open(os.path.join(d, "echo.js"), "w").write(ECHO)
        json.dump({json.dumps(js_numbers([v["context"], v["scenario"]]), sort_keys=True): O.optimize(v["context"], v["scenario"])
                   for v in cases.values()}, open(os.path.join(d, "echo_table.json"), "w"))
        out = {}
        for name in ("stub", "echo"):
            res = os.path.join(d, name + "_out.json")
            r = run(["node", "run_candidate_node.cjs", os.path.join(d, name + ".js"), probs, res, name])
            assert r.returncode == 0, r.stderr
            cmp_ = run([sys.executable, "compare_candidate.py", "--problems", a.problems, "--candidate-json", res])
            out[name] = {"exit": cmp_.returncode, "summary": cmp_.stdout.strip().splitlines()[-1]}
    ok = out["stub"]["exit"] == 1 and "PASS" not in out["stub"]["summary"] and out["echo"]["exit"] == 0 and "FAIL" not in out["echo"]["summary"]
    print(json.dumps(dict(out, verdict="PASS" if ok else "FAIL"), indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
