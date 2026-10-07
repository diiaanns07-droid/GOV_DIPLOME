"""AST-A08 — сценарий S3 на РЕАЛЬНОЙ геометрии: доп. датчики против «дыр» мониторинга.

Входы: OSM-полигоны 6 районов (STUPITS @834a25f, ODbL) + координаты 6 постов Казгидромета из списка
AirData (~2022, лицензии нет). Вес — ПЛОЩАДЬ (население недоступно: GHSL/WorldPop закрыты из среды).
Площадной вес переоценивает пустые земли; результат — нижняя планка методики, а не план размещения.

Запуск: python3 AST_A08_sensor_gap_real_geometry.py /home/claude
"""
import json, os, sys
import numpy as np
import pandas as pd
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from shapely import contains_xy
from pyproj import Transformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eco_priority_core import greedy_max_cover

R = sys.argv[1] if len(sys.argv) > 1 else "."
to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32642", always_xy=True).transform
to_ll = Transformer.from_crs("EPSG:32642", "EPSG:4326", always_xy=True).transform
gj = json.load(open(f"{R}/stupits/data/astana_districts.geojson"))
city = transform(to_utm, unary_union([shape(f["geometry"]) for f in gj["features"]]))
s = pd.read_excel(f"{R}/gh/DinaAssylbekova_AirData_Shymkent/sensors.xlsx")
p = s[s.city == "Нур-Султан"]
pxy = np.array([to_utm(x, y) for x, y in zip(p.lng, p.lat)]); ids = p.sId.tolist()

minx, miny, maxx, maxy = city.bounds
gx, gy = np.meshgrid(np.arange(minx + 125, maxx, 250), np.arange(miny + 125, maxy, 250))
ins = contains_xy(city, gx, gy); X, Y = gx[ins], gy[ins]
cgx, cgy = np.meshgrid(np.arange(minx + 500, maxx, 1000), np.arange(miny + 500, maxy, 1000))
cm = contains_xy(city, cgx, cgy); CX, CY = cgx[cm], cgy[cm]
dC = np.hypot(X[:, None] - CX, Y[:, None] - CY) <= 2000                  # клетки × кандидаты


def run(active_ids, n_new=5):
    a = pxy[[i for i, k in enumerate(ids) if k in active_ids]]
    base = (np.hypot(X[:, None] - a[:, 0], Y[:, None] - a[:, 1]) <= 2000).any(1)
    f = lambda sel: float((base | dC[:, sel].any(1)).mean()) if sel else float(base.mean())
    sel = greedy_max_cover(n_new, len(CX), f)
    return {"posts_used": active_ids, "share_area_within_2km_now": round(f([]), 3),
            "share_area_within_2km_plus5": round(f(sel), 3),
            "new_sites_latlon": [[round(v, 4) for v in to_ll(CX[j], CY[j])[::-1]] for j in sel]}


out = {"kind": "derived_real_geometry_area_weighted", "city_cells_250m": int(ins.sum()), "candidates_1km": int(cm.sum()),
       "all_6_posts": run(ids), "excluding_qc_flagged_k9": run([k for k in ids if k != "k9"])}
print(json.dumps(out, ensure_ascii=False, indent=1))
