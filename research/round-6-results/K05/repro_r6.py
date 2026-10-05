#!/usr/bin/env python3
"""Минимальное воспроизведение трёх FAIL на контракте сборки (через её tools/contract.py).

  python repro_r6.py --app-root <checkout 064ed25>/prototypes/city-evidence
"""
import argparse
import copy
import importlib.util
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--app-root", type=Path, required=True)
app = ap.parse_args().app_root.resolve()
spec = importlib.util.spec_from_file_location("build_contract", app / "tools/contract.py")
K = importlib.util.module_from_spec(spec)
spec.loader.exec_module(K)

# Реальная запись сборки как шаблон: первая reported-запись Шымкента из web/evidence.js.
t = (app / "web/evidence.js").read_text(encoding="utf-8")
ev = K.loads_strict(t[t.index("{"):t.rstrip().rindex(";")])
o = copy.deepcopy(next(x for x in ev["cities"]["shymkent"]["observations"]
                       if x["unit"] == "records" and x["value_status"] == "reported"))
print("шаблон:", o["obs_id"], o["unit"], o["value"])

# 1) COUNT_DOMAIN: −3 записей принимается (правило только для unit == "count")
print("1) records=-3:", K.validate(dict(o, value=-3), ev["as_of"])[0] or "ошибок нет (принято)")
print("   count=-3  :", K.validate(dict(o, value=-3, unit="count"), ev["as_of"])[0])

# 2) expected_units через v1.2
try:
    K.C4.aggregate_sum([o], expected_units=[o["geo_unit_id"], o["geo_unit_id"] + "_other"])
except TypeError as e:
    print("2) expected_units:", e)

# 3) две непересекающиеся bbox одного города → BOUNDARY_MIX
b = copy.deepcopy(o)
b.update(obs_id=o["obs_id"] + "/other_square", geo_unit_id="kz.shymkent.k10sq_r1_c1",
         boundary_version="k10_r3_square:r1_c1@000000000000")
b["spatial_unit"]["bbox"] = [69.31, 42.12, 69.33, 42.14]
try:
    print("3)", K.C4.aggregate_sum([o, b]))
except ValueError as e:
    print("3)", e)
