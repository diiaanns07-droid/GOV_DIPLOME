"""K08 R5: самопроверка check_demo_attribution.py на мутациях проходящей сборки.

Берёт извлечённую копию prototypes/city-evidence, на которой checker даёт 0 FAIL
(например, сборку с применённым proposal/attribution_demo.patch), копирует её во временную папку
и по одному портит признаки. Каждая мутация должна дать ожидаемый FAIL. Исходная папка не меняется.

Usage: python test_checker.py --app-root <passing prototypes/city-evidence>
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_demo_attribution.py"


def run(root):
    out = Path(tempfile.mkstemp(suffix=".json")[1])
    p = subprocess.run([sys.executable, str(CHECKER), "--app-root", str(root), "--json", str(out)], capture_output=True, text=True)
    rep = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    return p.returncode, {(r["id"], r["status"]) for r in rep["results"]}, rep


def mutate_data(root, fn):
    p = root / "web" / "data.js"
    txt = p.read_text(encoding="utf-8")
    m = re.search(r"(window\.CITY_EVIDENCE\s*=\s*)(\{.*\})(\s*;?\s*)$", txt, re.S)
    d = json.loads(m.group(2))
    fn(d)
    p.write_text(txt[:m.start(2)] + json.dumps(d, ensure_ascii=False) + m.group(3), encoding="utf-8")


MUTATIONS = {
    "license_text_byte_changed": (lambda r: (r / "web/LICENSES/CDLA-Permissive-2.0.txt").write_bytes(
        (r / "web/LICENSES/CDLA-Permissive-2.0.txt").read_bytes() + b"x"), ("A2", "FAIL")),
    "license_text_missing": (lambda r: (r / "web/LICENSES/Apache-2.0.txt").unlink(), ("A2", "FAIL")),
    "attribution_file_missing": (lambda r: (r / "web/ATTRIBUTION.md").unlink(), ("A3", "FAIL")),
    "segment_dataset_dropped": (lambda r: mutate_data(r, lambda d: [s.pop("dataset", None) for c in d["cities"].values() for s in c["segments"]]),
                                ("A6", "FAIL")),
    "road_card_hardcoded_osm": (lambda r: (r / "web/app.js").write_text(
        (r / "web/app.js").read_text(encoding="utf-8") + '\n// "Дорога (OSM через Overture)"\n', encoding="utf-8"), ("A7", "FAIL")),
    "input_byte_changed": (lambda r: (r / "inputs/k10/README.md").write_bytes((r / "inputs/k10/README.md").read_bytes() + b" "), ("A8", "FAIL")),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    a = ap.parse_args()
    src = Path(a.app_root)
    code, got, rep = run(src)
    if code != 0:
        print("исходная сборка не проходит checker (нужна сборка с 0 FAIL):", rep["summary"])
        return 2
    print("PASS control: исходная сборка — 0 FAIL")
    failed = 0
    for name, (fn, expect) in MUTATIONS.items():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "app"
            shutil.copytree(src, root)
            fn(root)
            code, got, _ = run(root)
            ok = code == 1 and expect in got
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'} {name}: ожидается {expect}, exit={code}")
    print(f"{len(MUTATIONS) - failed}/{len(MUTATIONS)} мутаций обнаружены")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
