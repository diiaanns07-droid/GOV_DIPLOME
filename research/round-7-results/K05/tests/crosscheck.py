#!/usr/bin/env python3
"""Сверка whatif.js с независимым whatif_ref.py на реальных срезах сборки.

  python tests/crosscheck.py --app-root <checkout>/prototypes/city-evidence [--json OUT]
Запускает node tests/test_whatif.cjs --dump, затем пересчитывает те же сценарии в Python.
Требование: отпечатки совпадают строкой; id ближайших записей и источники совпадают; расстояния до 1e-6 м.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import whatif_ref as R  # noqa: E402


def load_window(path, var):
    t = path.read_text(encoding="utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")]) if f"window.{var}" in t else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    D = load_window(a.app_root / "web/data.js", "CITY_EVIDENCE")
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "dump.json"
        subprocess.run(["node", str(HERE / "test_whatif.cjs"), "--app-root", str(a.app_root), "--dump", str(dump)],
                       check=True, capture_output=True, text=True)
        js = json.loads(dump.read_text(encoding="utf-8"))
    problems, n_rows, max_diff = [], 0, 0.0
    for city, snaps in js["snapshots"].items():
        for cat, s in snaps.items():
            py = R.source_snapshot(city, D["cities"][city], cat)
            if py != s:
                problems.append(f"snapshot {city}/{cat}: js {s} != py {py}")
    for case in js["cases"]:
        s = case["scenario"]
        py_rows = R.compute(D["cities"][s["city_id"]], s)
        for jr, pr in zip(case["rows"], py_rows):
            n_rows += 1
            for k in ("point_id", "before_id", "after_source"):
                if jr[k] != pr[k]:
                    problems.append(f"{s['city_id']}/{s['category']}/{jr['point_id']} {k}: {jr[k]} != {pr[k]}")
            for k in ("before_m", "after_m", "delta_m"):
                if (jr[k] is None) != (pr[k] is None):
                    problems.append(f"{jr['point_id']} {k} null mismatch")
                elif jr[k] is not None:
                    d = abs(jr[k] - pr[k])
                    max_diff = max(max_diff, d)
                    if d > 1e-6:
                        problems.append(f"{jr['point_id']} {k}: {jr[k]} vs {pr[k]}")
    out = {"cases": len(js["cases"]), "rows": n_rows, "max_abs_diff_m": max_diff, "problems": problems,
           "snapshots": js["snapshots"], "ok": not problems}
    print(json.dumps({k: v for k, v in out.items() if k != "snapshots"}, ensure_ascii=False, indent=1))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
