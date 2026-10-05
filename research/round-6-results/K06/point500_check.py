"""K06 round 6: verify the rendered count 'N записей … в пределах 500 м по прямой' with the WGS84 oracle.
Usage: python3 point500_check.py --app-root <dir> | --url <url>  [--json out.json]. Exit 1 on FAIL.
Places within 0.5 % of 500 m are ambiguous (sphere vs ellipsoid) and reported, not counted as errors."""
import argparse, json, os, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo_oracle import vincenty_m
ap = argparse.ArgumentParser(); g = ap.add_mutually_exclusive_group(required=True)
g.add_argument("--app-root"); g.add_argument("--url"); ap.add_argument("--json"); a = ap.parse_args()
target = a.url or Path(a.app_root, "web", "index.html").resolve().as_uri()
env = dict(os.environ, NODE_PATH=os.environ.get("NODE_PATH") or subprocess.check_output(["npm", "root", "-g"], text=True).strip())
obs = json.loads(subprocess.check_output(["node", str(Path(__file__).with_name("point500_check.cjs")), target], env=env, text=True))
res = {"target": target, "checks": []}
for city, r in obs.items():
    if not r["status"]:
        res["checks"].append({"id": "P1_point_500m_count", "city": city, "status": "FAIL", "observed": {"error": "no status text"}}); continue
    shown = int(re.search(r"Точка выбрана: (\d+) записей", r["status"]).group(1))
    d = [vincenty_m(r["point"][0], r["point"][1], lon, lat) for lon, lat in r["places"]]
    lo, hi = sum(x <= 500 * 0.995 for x in d), sum(x <= 500 * 1.005 for x in d)
    ok = lo <= shown <= hi and "по прямой" in r["status"] and "Время пешком не рассчитывается" in r["status"]
    res["checks"].append({"id": "P1_point_500m_count", "city": city, "status": "PASS" if ok else "FAIL",
                          "observed": {"status_text": r["status"], "shown": shown, "oracle_count_range": [lo, hi],
                                       "point": [round(x, 6) for x in r["point"]], "visible_places": len(d)}})
for c in res["checks"]:
    print(c["status"], c["city"], json.dumps(c["observed"], ensure_ascii=False))
if a.json:
    Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
sys.exit(1 if any(c["status"] == "FAIL" for c in res["checks"]) else 0)
