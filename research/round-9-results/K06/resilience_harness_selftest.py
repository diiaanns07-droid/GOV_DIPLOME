"""Self-test of the resilience JS comparison path (needs Node), with TEST-ONLY modules (not implementations):
echo of K06 reference answers -> all PASS; echo with a broken robust choice / worst list -> FAIL; missing module -> NOT_RUN.
  python3 resilience_harness_selftest.py"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import resilience_oracle as R

ECHO = '''const T = require("./table.json");
const canon = (o) => Array.isArray(o) ? "[" + o.map(canon).join(", ") + "]" : o && typeof o === "object" ? "{" + Object.keys(o).sort().map((k) => JSON.stringify(k) + ": " + canon(o[k])).join(", ") + "}" : JSON.stringify(o);
exports.optimizeResilience = (c, e) => { const r = T[canon([c.records, e])]; if (!r) throw new Error("no echo"); return JSON.parse(JSON.stringify(r)); };
'''


def jsn(o):
    if isinstance(o, float) and o.is_integer():
        return int(o)
    if isinstance(o, dict):
        return {k: jsn(v) for k, v in o.items()}
    if isinstance(o, list):
        return [jsn(x) for x in o]
    return o


def run(*cmd):
    return subprocess.run(list(cmd), cwd=HERE, capture_output=True, text=True)


fix = os.path.join(HERE, "fixtures", "resilience_gold.json")
doc = json.load(open(fix, encoding="utf-8"))
out = {}
with tempfile.TemporaryDirectory() as d:
    probs = os.path.join(d, "p.json")
    assert run(sys.executable, "compare_resilience_js.py", "--fixture", fix, "--export", probs).returncode == 0
    table = {json.dumps(jsn([c["context"]["records"], c["envelope"]]), sort_keys=True, ensure_ascii=False): R.optimize_resilience(c["context"], c["envelope"])
             for c in doc["cases"]}
    broken = json.loads(json.dumps(table))
    for v in broken.values():
        if v["status"] == "optimal" and len(v["robust"]["worst_case_ids"]) > 1:
            v["robust"]["worst_case_ids"] = v["robust"]["worst_case_ids"][:1]; break
    for v in broken.values():
        if v["status"] == "optimal" and v["robust"]["selected_ids"] != v["nominal"]["selected_ids"]:
            v["robust"]["selected_ids"] = v["nominal"]["selected_ids"]; break
    for name, tab in (("echo", table), ("broken", broken)):
        os.makedirs(os.path.join(d, name)); json.dump(tab, open(os.path.join(d, name, "table.json"), "w", encoding="utf-8"), ensure_ascii=False)
        open(os.path.join(d, name, "resilience.js"), "w").write(ECHO)
        o = os.path.join(d, name + ".json")
        assert run("node", "run_resilience_js.cjs", os.path.join(d, name, "resilience.js"), probs, o, name).returncode == 0
        r = run(sys.executable, "compare_resilience_js.py", "--fixture", fix, "--candidate-json", o)
        out[name] = {"exit": r.returncode, "summary": r.stdout.strip().splitlines()[-1]}
    o = os.path.join(d, "none.json")
    run("node", "run_resilience_js.cjs", os.path.join(d, "no_such_app"), probs, o, "none")
    r = run(sys.executable, "compare_resilience_js.py", "--fixture", fix, "--candidate-json", o)
    out["missing_module"] = {"exit": r.returncode, "summary": r.stdout.strip().splitlines()[-1]}
ok = (out["echo"]["exit"] == 0 and out["broken"]["exit"] == 1 and "'FAIL': 2" in out["broken"]["summary"]
      and out["missing_module"]["exit"] == 2 and "NOT_RUN" in out["missing_module"]["summary"])
print(json.dumps(dict(out, verdict="PASS" if ok else "FAIL"), ensure_ascii=False, indent=1))
sys.exit(0 if ok else 1)
