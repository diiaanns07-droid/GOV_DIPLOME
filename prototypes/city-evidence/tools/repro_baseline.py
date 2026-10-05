"""Reproduce round-4 defects on the BUILD 0bf27de contract (inputs/k05_root = k05-obs-v1.1, unpatched).

Baseline only: documents what the OLD build accepted. Writes research/round-5-results/BUILD/baseline_repro.json.
The new build is tested separately in tests/test_contract.py.
"""
import copy
import json
import math
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "inputs" / "k05_root" / "round-3-results" / "K05"))
import k05r3_contract as OLD  # noqa: E402


def old_obs():
    t = (APP / "web" / "evidence.js").read_text(encoding="utf-8")
    if "window.CITY_OBS" not in t:
        raise SystemExit("web/evidence.js is not the round-4 format")
    ev = json.loads(t[t.index("{"):t.rstrip().rindex(";")])
    return next(o for o in ev["cities"]["shymkent"]["observations"] if o["indicator_id"] == "places.school")


def main(base=None):
    base = base or old_obs()
    out = []
    for label, val in (("NaN", math.nan), ("+Infinity", math.inf), ("-Infinity", -math.inf)):
        o = copy.deepcopy(base)
        o["value"] = val
        errs, warns = OLD.validate(o, as_of="2026-10-05")
        out.append({"case": f"value={label}", "old_errors": errs, "accepted_by_old": not errs})
    out.append({"case": "json.loads('NaN')", "old_result": repr(json.loads('{"v": NaN}')["v"])})
    out.append({"case": "json.loads('1e999')", "old_result": repr(json.loads('{"v": 1e999}')["v"])})
    out.append({"case": "duplicate key", "old_result": json.loads('{"value_status": "reported", "value_status": "missing"}')})
    out.append({"case": "json.dumps(NaN) default", "old_result": json.dumps({"v": math.nan})})
    return out


if __name__ == "__main__":
    res = main()
    p = APP.parents[1] / "research" / "round-5-results" / "BUILD" / "baseline_repro.json"
    p.write_text(json.dumps({"build": "0bf27de (round 4)", "contract": "k05-obs-v1.1 unpatched", "cases": res},
                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    for r in res:
        print(r)
