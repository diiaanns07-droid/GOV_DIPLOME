"""AST-A11: изолированная проверка границ Астаны на кэше OSM из репозитория STUPITS.
Вход: data/astana_districts.geojson и data/geo_sources/astana_districts_overpass.json
(OSM base 2026-09-22T08:45:51Z, ODbL). Результат — контекст OSM, НЕ юридические границы.
Запуск: python AST_A11_boundary_check.py <путь к корню репозитория STUPITS>
"""
import json, sys
import pyproj, shapely
from shapely.geometry import shape, LineString
from shapely.ops import unary_union, transform, polygonize, linemerge

root = sys.argv[1]
g = json.load(open(f"{root}/data/astana_districts.geojson", encoding="utf-8"))
ov = json.load(open(f"{root}/data/geo_sources/astana_districts_overpass.json", encoding="utf-8"))
city = unary_union([shape(f["geometry"]) for f in g["features"]])
c = city.centroid
fwd = pyproj.Transformer.from_crs("EPSG:4326", f"+proj=laea +lat_0={c.y} +lon_0={c.x} +units=m", always_xy=True).transform
cityP = transform(fwd, city)
print(f"shapely {shapely.__version__}, pyproj {pyproj.__version__}; osm_base {ov['osm3s']['timestamp_osm_base']}")
print(f"Astana (union of 6 OSM districts): parts={len(getattr(cityP,'geoms',[cityP]))}, area_km2={cityP.area/1e6:.1f}")
distP = {f["properties"]["name"]: transform(fwd, shape(f["geometry"])) for f in g["features"]}
parts = sorted(getattr(cityP, 'geoms', [cityP]), key=lambda x: -x.area)
for p in parts:
    owner = [n for n, d in distP.items() if d.intersection(p).area > 0.5 * p.area]
    print(f"  part area_km2={p.area/1e6:.3f} district={owner}")

def ring_union(el, role):
    lines = [LineString([(pt["lon"], pt["lat"]) for pt in m["geometry"]])
             for m in el["members"] if m["type"] == "way" and m.get("role") == role and m.get("geometry")]
    polys = list(polygonize(linemerge(lines))) if lines else []
    return unary_union(polys) if polys else None

def rel_polygon(el):
    outer, inner = ring_union(el, "outer"), ring_union(el, "inner")
    if outer is None:
        return None, 0
    n_inner = sum(1 for m in el["members"] if m.get("role") == "inner")
    return (outer.difference(inner) if inner is not None else outer), n_inner

for el in ov["elements"]:
    t = el.get("tags", {})
    if el["type"] != "relation" or el["id"] in {int(f["properties"]["osm_id"]) for f in g["features"]}:
        continue
    poly, n_inner = rel_polygon(el)
    if poly is None:
        print(f"rel {el['id']} {t.get('name:ru')}: polygon not assembled"); continue
    P = transform(fwd, poly)
    inter = P.intersection(cityP).area / 1e6
    shared = P.boundary.intersection(cityP.buffer(5).boundary.buffer(10)).length / 1000  # допуск 5–10 м
    touch_km = P.buffer(5).intersection(cityP.boundary).length / 1000
    print(f"rel {el['id']} {t.get('name:ru')} | addr:region={t.get('addr:region')} admin_level={t.get('admin_level')} "
          f"| inner_members={n_inner} | area_km2={P.area/1e6:.1f} | overlap_with_astana_km2={inter:.3f} | astana_boundary_within_5m_km={touch_km:.1f}")
