"""K09 round-7: самопроверка эталона whatif_ref.py и сверка с haversine из app.js (c58a3b2) через node.

Запуск: python3 selftest_ref.py   (из папки scripts). Пишет ../results/selftest.json
"""
import json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from whatif_ref import BASE_SHA, R_EARTH, Slice, compute, git_bytes, haversine_m

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sl = Slice.from_git(repo=str(REPO))
tasks = json.loads((HERE.parent / "tasks/whatif_tasks.json").read_text(encoding="utf-8"))["tasks"]
res = {"checks": []}


def check(name, ok, detail=""):
    res["checks"].append({"name": name, "pass": bool(ok), "detail": detail})


# формула
check("zero_distance_identical_points", haversine_m(69.6, 42.3, 69.6, 42.3) == 0.0)
check("one_degree_latitude_m", abs(haversine_m(0, 0, 0, 1) - 2 * math.pi * R_EARTH / 360) < 1e-6, f"{haversine_m(0, 0, 0, 1):.6f}")
check("symmetry", haversine_m(69.6, 42.3, 69.61, 42.31) == haversine_m(69.61, 42.31, 69.6, 42.3))
check("antipodal_clamp_finite", math.isfinite(haversine_m(0, 0, 180, 0)), f"{haversine_m(0, 0, 180, 0):.3f} ≈ πR={math.pi * R_EARTH:.3f}")
# инварианты ожидаемых исходов
inv_ok, inv_bad = 0, []
for t in tasks:
    for r in t["expected"]:
        for x in r["rows"]:
            b, a, d, dp = x["before_m"], x["after_m"], x["delta_m"], x["distance_to_proposed_m"]
            conds = [b is None or a <= b + 1e-12, d is None or d >= 0, (b is None or d is None) or abs((b - a) - d) < 1e-9,
                     dp is None or b is None or a == min(b, dp)]
            if all(conds): inv_ok += 1
            else: inv_bad.append(f"{t['id']}:{x['control_point_id']}")
check("after<=before, delta>=0, delta=before-after, after=min(before,dp)", not inv_bad, f"rows ok={inv_ok}, bad={inv_bad}")
# детерминизм: повторный расчёт совпадает
again = [compute(sl, s) for t in tasks for s in t.get("steps", [])]
orig = [r for t in tasks for r in t["expected"]]
check("deterministic_recompute", again == orig)
# ничья не влияет на длину: перестановка порядка записей
city, cat = "shymkent", "outpatient_clinic"
w4 = next(t for t in tasks if t["id"] == "K09-W4")
rev = Slice(git_bytes(BASE_SHA, "prototypes/city-evidence/web/data.js", str(REPO)), git_bytes(BASE_SHA, "prototypes/city-evidence/web/evidence.js", str(REPO)))
rev.data["cities"][city]["places"].reverse()
check("tie_order_independent", compute(rev, w4["steps"][0]) == w4["expected"][0])
# сверка с app.js haversine (node), если node доступен
node = shutil.which("node")
if node:
    js = git_bytes(BASE_SHA, "prototypes/city-evidence/web/app.js", str(REPO)).decode("utf-8")
    start = js.index("function haversine(")
    end = js.index("\n  }", start) + 4
    fn = js[start:end]
    pairs = []
    for t in tasks:
        for s in t.get("steps", []):
            for c in s["control_points"]:
                for p in sl.candidates(s["city_id"], s["category"]):
                    pairs.append([c["lon"], c["lat"], p["lon"], p["lat"]])
    with tempfile.TemporaryDirectory() as td:
        Path(td, "p.json").write_text(json.dumps(pairs))
        Path(td, "h.js").write_text(fn + "\nconst P=require('./p.json');console.log(JSON.stringify(P.map(q=>haversine(q[0],q[1],q[2],q[3]))));\n")
        out = json.loads(subprocess.run([node, "h.js"], cwd=td, capture_output=True, text=True, check=True).stdout)
    diffs = [abs(o - haversine_m(*q)) for o, q in zip(out, pairs)]
    check("app.js_haversine_matches_reference_in_bbox", max(diffs) <= 1e-6, f"pairs={len(pairs)}, max_abs_diff_m={max(diffs):.3e}")
    check("app.js_haversine_has_clamp_per_spec", "Math.min" in fn or "clamp" in fn.lower(),
          "app.js:79 haversine не зажимает a в [0,1]; внутри bbox на результат не влияет (см. предыдущую проверку)")
else:
    check("app.js_haversine_matches_reference_in_bbox", False, "SKIP: node не найден")
res["node"] = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip() if node else None
res["python"] = sys.version.split()[0]
(HERE.parent / "results/selftest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for c in res["checks"]:
    print("PASS" if c["pass"] else "FAIL", c["name"], c["detail"])
