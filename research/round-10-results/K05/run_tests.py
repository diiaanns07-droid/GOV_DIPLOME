"""K05 r10: apply patch/plan_matrix.patch + module to a TEMP copy of the BUILD and run all checks.
  python3 run_tests.py --app-root <dir containing web/govtech and tests/govtech of the BUILD>  [--keep <dir>]
Example: git archive d2ff344c5ec9b9a729ea59df50ec81f981e619de web/govtech tests/govtech | tar -x -C /tmp/d2
The given directory is never modified."""
import argparse, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "ref"))
import school_compare_ref as R


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app-root", required=True); ap.add_argument("--keep")
    a = ap.parse_args()
    d = a.keep or tempfile.mkdtemp(prefix="k05r10_")
    if a.keep and os.path.exists(d):
        shutil.rmtree(d)
    for sub in ("web/govtech", "tests/govtech"):
        shutil.copytree(os.path.join(a.app_root, sub), os.path.join(d, sub))
    r = subprocess.run(["patch", "-p1", "--forward", "-i", os.path.join(HERE, "patch", "plan_matrix.patch")], cwd=d, capture_output=True, text=True)
    print("patch:", r.returncode, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip())
    if r.returncode:
        return 1
    shutil.copy(os.path.join(HERE, "module", "school-compare.js"), os.path.join(d, "web", "govtech", "school-compare.js"))
    hand = os.path.join(HERE, "fixtures", "hand_cases.json")
    doc = json.load(open(hand, encoding="utf-8"))
    dump = {}
    for h in doc["cases"]:
        plans, n = R.compare(h["case"], h["matrix"])
        dump[h["case"]["case_id"]] = {"plans": plans, "evaluated_sets": n}
    rp = os.path.join(d, "ref_dump.json"); json.dump(dump, open(rp, "w"))
    res = {}
    t = subprocess.run(["node", os.path.join(HERE, "tests", "test_school_compare.cjs"), os.path.join(d, "web", "govtech"), hand, rp], capture_output=True, text=True)
    print(t.stdout.strip()); res["school_compare"] = t.returncode
    for name in ("plan", "resilience", "whatif"):
        t = subprocess.run(["node", os.path.join(d, "tests", "govtech", name + ".cjs")], capture_output=True, text=True)
        last = (t.stdout.strip().splitlines() or ["(no output)"])[-1]
        print(f"BUILD test {name}.cjs on patched copy:", t.returncode, last); res[name] = t.returncode
    if not a.keep:
        shutil.rmtree(d)
    return 0 if all(v == 0 for v in res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
