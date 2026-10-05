"""K09 round-7: сверка экспорта сценария из интерфейса BUILD с эталоном K09.

Экспорт считается недоверенным: сценарий проверяется и пересчитывается эталоном, затем сравниваются
значения экспорта по каждой контрольной точке. Имена полей результата в экспорте BUILD ещё не определены,
поэтому принимаются варианты: results|rows|comparison -> [{control_point_id|id, before|before_m, after|after_m,
delta|delta_m, nearest_before_id?, nearest_after_id?}]. Допуск: --tol-m (по умолчанию 0.5 м, т.е. округление до метра).

Запуск: python3 compare_export.py <export.json> [--tol-m 0.5]
        python3 compare_export.py --controls   (положительный и отрицательный контроль на задачах K09)
"""
import argparse, copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from whatif_ref import Slice, compute

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ALIASES = {"before": ("before_m", "before"), "after": ("after_m", "after"), "delta": ("delta_m", "delta")}


def pick(row, names):
    for n in names:
        if n in row:
            return row[n]
    return "MISSING"


def compare(sl, export, tol):
    scen = {k: export.get(k) for k in ("schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object")}
    ref = compute(sl, scen, expected_snapshot=None)   # отпечаток сборки не обязан совпадать с K09; данные — закреплённый срез K09
    if ref["status"] != "ok":
        return {"verdict": "REJECT_EXPECTED", "reference": ref}
    rows = export.get("results") or export.get("rows") or export.get("comparison")
    if not isinstance(rows, list):
        return {"verdict": "NO_RESULTS_IN_EXPORT"}
    by_id = {r.get("control_point_id", r.get("id")): r for r in rows}
    issues = []
    for x in ref["rows"]:
        r = by_id.get(x["control_point_id"])
        if r is None:
            issues.append(f"{x['control_point_id']}: missing in export"); continue
        for k, names in ALIASES.items():
            got, exp = pick(r, names), x[f"{k}_m"]
            if got == "MISSING":
                issues.append(f"{x['control_point_id']}.{k}: missing")
            elif exp is None or got is None:
                if exp is not got and not (exp is None and got is None):
                    issues.append(f"{x['control_point_id']}.{k}: expected {exp}, got {got}")
            elif abs(float(got) - exp) > tol:
                issues.append(f"{x['control_point_id']}.{k}: expected {exp:.3f}, got {got} (|Δ|>{tol})")
        for k in ("nearest_before_id", "nearest_after_id"):
            if k in r and r[k] != x[k]:
                issues.append(f"{x['control_point_id']}.{k}: expected {x[k]}, got {r[k]}")
    return {"verdict": "PASS" if not issues else "FAIL", "issues": issues}


def controls(sl):
    tasks = json.loads((HERE.parent / "tasks/whatif_tasks.json").read_text(encoding="utf-8"))["tasks"]
    out = []
    for t in tasks:
        for s, r in zip(t.get("steps", []), t["expected"]):
            good = {**s, "results": [{"control_point_id": x["control_point_id"], "before": None if x["before_m"] is None else round(x["before_m"]),
                                      "after": None if x["after_m"] is None else round(x["after_m"]),
                                      "delta": None if x["delta_m"] is None else round(x["delta_m"])} for x in r["rows"]]}
            bad = copy.deepcopy(good)
            bad["results"][0]["after"] = (bad["results"][0]["after"] or 0) + 25          # искажение на 25 м
            out.append({"task": t["id"], "positive": compare(sl, good, 0.5)["verdict"], "negative": compare(sl, bad, 0.5)["verdict"]})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("export", nargs="?")
    ap.add_argument("--tol-m", type=float, default=0.5)
    ap.add_argument("--controls", action="store_true")
    a = ap.parse_args()
    sl = Slice.from_git(repo=str(REPO))
    if a.controls:
        res = controls(sl)
        (HERE.parent / "results/compare_controls.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False))
        print("all positive PASS:", all(x["positive"] == "PASS" for x in res), "| all negative FAIL:", all(x["negative"] == "FAIL" for x in res))
    else:
        print(json.dumps(compare(sl, json.loads(Path(a.export).read_text(encoding="utf-8")), a.tol_m), ensure_ascii=False, indent=1))
