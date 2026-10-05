"""K08: разложение разницы «сумма км по районам − км в городе» из K10-E03.

Читает выгрузки K10 (<raw>/<city>_division_area.jsonl, <city>_segment.jsonl; sha256 сверяется
с provenance/raw_extracts.sha256 K10) и модуль check_districts.py из K10 @ e91898d (путь — 2-й аргумент).
Ничего не пишет, кроме stdout. Для каждого road-сегмента, пересекающего полигон города:
  district_sum = Σ km(g ∩ D_i)                      # как в network_by_district.py
  city_km      = km(g ∩ city)
  shared       = Σ_{i<j} km(g ∩ D_i ∩ D_j)           # линии на общих границах районов
  outside      = Σ_i km((g ∩ D_i) − city)            # части районов вне полигона города
  uncovered    = km(g ∩ (city − ∪D_i))               # дороги в части города без района
Тождество: district_sum ≈ city_km − uncovered + shared + outside (до погрешности геометрии).
Usage: python e03_overcount_diagnostic.py <raw_dir> <k10_scripts_dir>
"""
import json
import sys
from collections import Counter
from itertools import combinations

raw, k10 = sys.argv[1], sys.argv[2]
sys.path.insert(0, k10)
import shapely  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402
from check_districts import load  # noqa: E402
from network_by_district import km  # noqa: E402

out = {"experiment_id": "K08-E03-diagnostic", "results": []}
for city in ("shymkent", "astana"):
    region, districts, extra = load(raw, city)
    city_g = shapely.from_wkt(region[0]["geometry"])
    units = districts + extra
    ug = [shapely.from_wkt(u["geometry"]) for u in units]
    names = [u["names"]["primary"] for u in units]
    uncovered_area = city_g.difference(shapely.union_all(ug))
    tree = STRtree(ug)
    t = Counter()
    shared_pairs = Counter()
    shared_cls = Counter()
    for line in open(f"{raw}/{city}_segment.jsonl", encoding="utf-8"):
        s = json.loads(line)
        if s.get("subtype") != "road":
            continue
        g = shapely.from_wkt(s["geometry"])
        if not city_g.intersects(g):
            continue
        t["city_km"] += km(g.intersection(city_g))
        idx = [i for i in tree.query(g) if not g.intersection(ug[i]).is_empty]
        for i in idx:
            part = g.intersection(ug[i])
            t["district_sum"] += km(part)
            t["outside"] += km(part.difference(city_g))
        for i, j in combinations(idx, 2):
            sh = g.intersection(ug[i]).intersection(ug[j])
            if not sh.is_empty:
                L = km(sh)
                if L > 0:
                    t["shared"] += L
                    shared_pairs[tuple(sorted((names[i], names[j])))] += L
                    shared_cls[s.get("class") or "(none)"] += L
        if not uncovered_area.is_empty and g.intersects(uncovered_area):
            t["uncovered"] += km(g.intersection(uncovered_area))
    r = {k: round(v, 3) for k, v in t.items()}
    r["district_sum_minus_city_km"] = round(t["district_sum"] - t["city_km"], 3)
    r["identity_residual_km"] = round(t["district_sum"] - (t["city_km"] - t["uncovered"] + t["shared"] + t["outside"]), 3)
    r["shared_by_pair_km"] = {f"{a} | {b}": round(v, 3) for (a, b), v in shared_pairs.most_common()}
    r["shared_by_class_km"] = {k: round(v, 3) for k, v in shared_cls.most_common(8)}
    r["uncovered_area_km2_note"] = "площадь см. K10-E01 city_area_not_covered_km2"
    out["results"].append({"city": city, **r})
print(json.dumps(out, ensure_ascii=False, indent=1))
